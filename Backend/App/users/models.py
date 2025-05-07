from sqlalchemy import Column, String, DateTime, Boolean
from sqlalchemy.sql import func
from datetime import datetime, timedelta
from uuid import uuid4
import os

from App.database import Base

# دریافت مدت انقضای جلسه از متغیرهای محیطی
SESSION_EXPIRY_DAYS = int(os.getenv("SESSION_EXPIRY_DAYS", "30"))

class Session(Base):
    """مدل جلسه برای ذخیره‌سازی در دیتابیس"""
    __tablename__ = "sessions"
    
    # شناسه جلسه به عنوان کلید اصلی
    session_id = Column(String, primary_key=True, index=True, default=lambda: str(uuid4()))
    
    # اطلاعات مرورگر و آدرس IP
    user_agent = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    
    # زمان‌های مرتبط با جلسه
    created_at = Column(DateTime, default=func.now(), nullable=False)
    last_activity = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    
    # داده‌های بیشتر به صورت اختیاری
    is_active = Column(Boolean, default=True, nullable=False)
    data = Column(String, nullable=True)  # می‌تواند برای ذخیره داده‌های اضافی به صورت JSON استفاده شود
    
    def __init__(self, **kwargs):
        # اگر expires_at در kwargs نباشد، به صورت خودکار تنظیم می‌شود
        if "expires_at" not in kwargs:
            kwargs["expires_at"] = datetime.now() + timedelta(days=SESSION_EXPIRY_DAYS)
        super().__init__(**kwargs)
    
    def is_expired(self) -> bool:
        """بررسی انقضای جلسه"""
        return self.expires_at < datetime.now()
    
    def update_expiry(self) -> None:
        """به‌روزرسانی زمان انقضای جلسه"""
        self.expires_at = datetime.now() + timedelta(days=SESSION_EXPIRY_DAYS)
        self.last_activity = datetime.now() 