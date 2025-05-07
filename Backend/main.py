from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
from dotenv import load_dotenv
from contextlib import asynccontextmanager

from App.routers import router as app_router
from App.database import engine, Base
from App.properties.scheduler import initialize_scheduler, stop_scheduler
from App.chatbot.cache import fetch_and_cache_properties, start_scheduler as start_chatbot_scheduler

# بارگذاری متغیرهای محیطی
load_dotenv("config.env")

# در محیط تولید از Alembic برای مهاجرت استفاده کنید
is_dev_env = os.getenv("ENV", "development") == "development"
if is_dev_env:
    Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """مدیریت چرخه حیات برنامه"""
    # اجرای کدها در زمان راه‌اندازی برنامه
    initialize_scheduler()
    # Initialize chatbot cache and scheduler
    fetch_and_cache_properties()
    start_chatbot_scheduler()
    yield
    # اجرای کدها در زمان خاتمه برنامه
    stop_scheduler()

app = FastAPI(
    title="Trunest API",
    description="Backend API for property management with FastAPI",
    version="1.0.0",
    openapi_version="3.0.2",
    lifespan=lifespan
)

# CORS middleware setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers from app modules
app.include_router(app_router, prefix="/api")

@app.get("/")
async def root():
    """صفحه اصلی API"""
    return {"message": "به API املاک خوش آمدید. برای مشاهده مستندات API به /docs مراجعه کنید."}

if __name__ == "__main__":
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    
    uvicorn.run("main:app", host=host, port=port, reload=is_dev_env)