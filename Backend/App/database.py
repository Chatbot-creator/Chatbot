import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import logging

# راه‌اندازی لاگر
logger = logging.getLogger(__name__)

# بارگذاری متغیرهای محیطی
load_dotenv("config.env")

# دریافت URL دیتابیس از متغیرهای محیطی
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    logger.warning("DATABASE_URL یافت نشد، از مقدار پیش‌فرض استفاده می‌شود")
    DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/Trunest"

try:
    # ایجاد موتور SQLAlchemy با تنظیمات بهینه
    engine = create_engine(
        DATABASE_URL,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
        echo=os.getenv("ENV") == "development"
    )
    
    # ایجاد کلاس‌های Session برای ارتباط با دیتابیس
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # کلاس پایه مدل‌ها
    Base = declarative_base()
    
    # تابع کمکی برای دریافت اتصال به دیتابیس
    def get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()
            
except Exception as e:
    logger.error(f"خطا در اتصال به دیتابیس: {str(e)}") 