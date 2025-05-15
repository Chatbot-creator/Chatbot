from fastapi import FastAPI, UploadFile, File, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import os
import json
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from openai import AsyncOpenAI

from App.database import engine, Base, SessionLocal, get_db
from App.routers import router as app_router
from App.properties.models import Property
from App.properties.routes import convert_to_original_format
from App.properties.scheduler import initialize_scheduler, stop_scheduler
from App.chatbot.chatbot_code import real_estate_chatbot
from App.chatbot.chatbot_code import ChatRequest
from App.chatbot.crud import (
    get_chat_session, create_chat_session,
    create_voice_message, delete_old_voice_messages
)
from openai import AsyncOpenAI

# بارگذاری env
load_dotenv("config.env")

# تنظیم OpenAI client
api_key = os.getenv("OPENAI_API_KEY")
client = AsyncOpenAI(api_key=api_key)

# در dev فقط:
is_dev_env = os.getenv("ENV", "development") == "development"
if is_dev_env:
    Base.metadata.create_all(bind=engine)

# کش در حافظه
property_cache = {}
scheduler = BackgroundScheduler()

# کش دیتای املاک از دیتابیس
def fetch_all_properties_from_db():
    db = SessionLocal()
    try:
        all_properties = db.query(Property).all()
        properties = []
        districts = {}

        for prop in all_properties:
            formatted = convert_to_original_format(prop)
            properties.append(formatted)

            district = formatted.get("district")
            if isinstance(district, dict):
                name = district.get("name", "").strip()
                district_id = district.get("id")
                if name and district_id and name not in districts:
                    districts[name] = district_id

        return {
            "properties": properties,
            "districts": districts
        }

    finally:
        db.close()

def fetch_and_cache_properties():
    result = fetch_all_properties_from_db()
    property_cache["all"] = result
    print(f"🕓 Property cache updated at {datetime.now()}")
    print(f"✅ {len(result['properties'])} ملک کش شد.")
    print(f"✅ {len(result['districts'])} منطقه شناسایی شد.")

def start_scheduler():
    scheduler.add_job(fetch_and_cache_properties, "interval", hours=24)
    scheduler.start()
    print("📅 Property scheduler every 24h started.")

# ✅ چرخه عمر برنامه
@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_scheduler()           # 📅 برای API اصلی
    fetch_and_cache_properties()     # 🏘 برای املاک
    start_scheduler()                # ⏱ برای املاک
    # fetch_chatbot_cache()            # 🤖 کش چت‌بات
    # start_chatbot_scheduler()        # 🤖 زمانبند چت‌بات
    yield
    stop_scheduler()

# ✅ ساخت اپلیکیشن
app = FastAPI(
    title="Trunest API",
    description="Backend API for property management",
    version="1.0.0",
    openapi_version="3.0.2",
    lifespan=lifespan
)

# ✅ CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ روت اصلی
@app.get("/")
async def root():
    return {"message": "به API املاک خوش آمدید. برای مشاهده مستندات به /docs بروید."}

# ✅ روت کش‌شده
@app.get("/all-properties")
def get_cached_properties():
    data = property_cache.get("all")
    if data is None:
        return JSONResponse(content={"detail": "No data cached yet."}, status_code=404)
    return {
        "properties": data["properties"],
        "districts": data["districts"],
        "property_count": len(data["properties"]),
        "district_count": len(data["districts"])
    }


# ✅ مسیر API برای چت‌بات - پشتیبانی از متن و صوت
@app.post("/chatbot")
async def unified_chatbot(
    message: str = None,
    file: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    """
    Unified endpoint for handling both text and voice messages.
    
    Args:
        message: Text message from user (optional)
        file: Voice message file (optional)
        db: Database session
    """
    # ✅ حالت: پیام متنی
    if message is not None and file is None:
        user_message = message.strip()
        if not user_message:
            welcome_message = """
                <div style="text-align: right; direction: rtl; background-color: #e6f7ff; padding: 12px; border-radius: 10px; border: 1px solid #b3d8ff;">
                    <p style="margin-top: 0; font-weight: bold; font-size: 16px;">👋 به چت‌بات مشاور املاک <span style="color: #000000;">شرکت ترونست</span> خوش آمدید!</p>
                    <p style="margin: 6px 0;">من اینجا هستم تا به شما در پیدا کردن <b>بهترین املاک در دبی</b> کمک کنم. 🏡✨</p>
                    <hr style="border-top: 1px solid #ccc;">
                    <p style="margin-bottom: 0;"><b>چطور می‌توانم کمکتان کنم؟</b></p>
                </div>
            """
            return {"response": welcome_message}
        bot_response = await real_estate_chatbot(user_message)
        return {"response": bot_response}

    # ✅ حالت: فایل صوتی
    elif file is not None:
        try:
            print("📥 دریافت فایل صوتی:", file.filename)

            # دریافت یا ایجاد جلسه چت
            db_session = get_chat_session(db, "voice_user")  # TODO: implement proper user session management
            if not db_session:
                db_session = create_chat_session(db, "voice_user")            # خواندن محتوای فایل
            content = await file.read()
            
            # ✅ ذخیره فایل صوتی در دیتابیس
            voice_message = create_voice_message(
                db=db,
                session_id=db_session.id,
                file_data=content,
                original_filename=file.filename
            )

            # ✅ تبدیل صوت به متن با Whisper
            try:
                # ذخیره موقت فایل
                temp_file_path = f"temp_voice_{file.filename}"
                with open(temp_file_path, "wb") as temp_file:
                    temp_file.write(content)
                
                # ارسال فایل به Whisper
                with open(temp_file_path, "rb") as audio_file:
                    transcript = await client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file
                    )
                    
                # حذف فایل موقت
                import os
                os.remove(temp_file_path)
                
                # به‌روزرسانی متن استخراج شده در دیتابیس
                voice_message.transcribed_text = transcript.text
                db.commit()
                
                print("📝 متن استخراج‌شده:", transcript.text)
                
                # پردازش متن استخراج شده توسط چت‌بات
                bot_response = await real_estate_chatbot(transcript.text)
                return {"response": bot_response}

            except Exception as e:
                print("❌ خطا در تبدیل صوت:", e)
                return {"error": "خطا در تبدیل صوت به متن"}

        except Exception as e:
            print("❌ خطا در پردازش فایل صوتی:", e)
            return {"error": "خطا در پردازش فایل صوتی"}

    # ❌ هیچ ورودی معتبری نیامده
    return {"error": "نه پیام متنی و نه فایل صوتی ارسال شده است"}


# ✅ اتصال روت‌ها
app.include_router(app_router, prefix="/api")

# ✅ اجرای برنامه
if __name__ == "__main__":
    import uvicorn
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run("main:app", host=host, port=port, reload=is_dev_env)
