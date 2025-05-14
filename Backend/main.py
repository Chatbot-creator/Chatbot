
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, ORJSONResponse
from fastapi.openapi.utils import get_openapi
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import os, uuid
from typing import Optional
import json
from dotenv import load_dotenv
from fastapi import UploadFile, File, Form, Request
import aiofiles
import openai

from App.database import engine, Base, SessionLocal
from App.routers import router as app_router
from App.properties.models import Property
from App.properties.routes import convert_to_original_format
from App.properties.scheduler import initialize_scheduler, stop_scheduler
from App.chatbot.chatbot_code import real_estate_chatbot
from App.chatbot.chatbot_code import ChatRequest

# بارگذاری env
load_dotenv("config.env")
is_dev_env = os.getenv("ENV", "development") == "development"

# فقط در حالت توسعه دیتابیس بساز
if is_dev_env:
    Base.metadata.create_all(bind=engine)

# کش املاک
property_cache = {}
scheduler = BackgroundScheduler()

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
    initialize_scheduler()
    fetch_and_cache_properties()
    start_scheduler()
    yield
    stop_scheduler()

# ✅ ساخت اپلیکیشن
app = FastAPI(
    title="Trunest API",
    description="Backend API for property management",
    version="1.0.0",
    openapi_version="3.0.2",
    docs_url="/docs" if is_dev_env else None,  # فقط در dev
    redoc_url=None,
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# ✅ فعال‌سازی GZIP برای همه‌ی responseها
app.add_middleware(GZipMiddleware, minimum_size=1000)

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

from openai import OpenAI
client = OpenAI()
@app.post("/chatbot")
async def unified_chatbot(message: str = Form(None), file: UploadFile = File(None)):
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
        print("📥 دریافت فایل صوتی:", file.filename)

        # ذخیره موقت فایل
        temp_path = f"temp_{file.filename}"
        try:
            async with aiofiles.open(temp_path, 'wb') as out_file:
                content = await file.read()
                await out_file.write(content)
            print("📁 فایل ذخیره شد:", temp_path)
        except Exception as e:
            print("❌ خطا در ذخیره فایل:", e)
            return {"error": "خطا در ذخیره فایل صوتی"}

        # تبدیل صوت به متن با Whisper
        try:
            with open(temp_path, "rb") as audio_file:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file
                )
            print("📝 متن استخراج‌شده:", transcript.text)
        except Exception as e:
            print("❌ خطا در تبدیل صوت:", e)
            return {"error": "خطا در تبدیل صوت به متن"}

        try:
            os.remove(temp_path)
            print("🧹 فایل حذف شد.")
        except Exception as e:
            print("⚠️ خطا در حذف فایل:", e)

        user_text = transcript.text
        try:
            bot_response = await real_estate_chatbot(user_text)
            print("🤖 پاسخ بات:", bot_response)
        except Exception as e:
            print("❌ خطا در چت‌بات:", e)
            return {"error": "خطا در پردازش چت‌بات"}

        return {
            # "user_text": user_text,
            "response": bot_response
        }

    # ❌ هیچ ورودی معتبری نیامده
    return {"error": "نه پیام متنی و نه فایل صوتی ارسال شده است"}


# ✅ اتصال تمام روت‌های پروژه
app.include_router(app_router, prefix="/api")

# ✅ کش کردن openapi.json برای سرعت لود /docs
cached_openapi_schema = None

@app.get("/openapi.json", include_in_schema=False)
async def custom_openapi():
    global cached_openapi_schema
    if cached_openapi_schema is None:
        cached_openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
    return ORJSONResponse(content=cached_openapi_schema)

# ✅ اجرای پروژه با uvicorn
if __name__ == "__main__":
    import uvicorn
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run("main:app", host=host, port=port, reload=is_dev_env)
