from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, JSON
from sqlalchemy.sql import func
from App.database import Base

class Property(Base):
    """
    مدل املاک برای ذخیره‌سازی داده‌های املاک دریافتی از API
    
    این مدل ساختار جدول properties در دیتابیس را تعریف می‌کند که برای 
    ذخیره‌سازی داده‌های املاک دریافتی از API خارجی استفاده می‌شود.
    
    Attributes:
        id (int): شناسه اصلی و کلید اولیه در دیتابیس
        property_id (str): شناسه منحصر به فرد ملک در API خارجی
        title (str): عنوان ملک
        description (str): توضیحات ملک
        price (float): قیمت ملک
        property_type (str): نوع ملک (مسکونی، تجاری و غیره)
        city (str): شهر محل ملک
        address (str): آدرس کامل ملک
        latitude (float): عرض جغرافیایی محل ملک
        longitude (float): طول جغرافیایی محل ملک
        bedrooms (int): تعداد اتاق خواب
        bathrooms (int): تعداد سرویس بهداشتی
        area (float): مساحت ملک
        images (JSON): لیست تصاویر ملک به صورت JSON
        created_at (datetime): زمان ایجاد رکورد در دیتابیس
        updated_at (datetime): زمان آخرین به‌روزرسانی رکورد
        fetched_at (datetime): زمان دریافت داده از API
        raw_data (JSON): داده‌های خام دریافتی از API به صورت JSON
    """
    __tablename__ = "properties"
    
    # شناسه اصلی
    id = Column(Integer, primary_key=True, index=True)
    
    # شناسه منحصر به فرد املاک در API
    property_id = Column(String, unique=True, index=True)
    
    # اطلاعات اصلی ملک
    title = Column(String, nullable=True)
    description = Column(String, nullable=True)
    price = Column(Float, nullable=True)
    property_type = Column(String, nullable=True)
    
    # اطلاعات مکانی
    city = Column(String, nullable=True)
    address = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    
    # مشخصات
    bedrooms = Column(Integer, nullable=True)
    bathrooms = Column(Integer, nullable=True)
    area = Column(Float, nullable=True)
    
    # تصاویر به صورت JSON
    images = Column(JSON, nullable=True)
    
    # فیلدهای زمانی
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    fetched_at = Column(DateTime, default=func.now(), nullable=False)
    
    # فیلد اضافی برای ذخیره تمام داده‌های دریافتی
    raw_data = Column(JSON, nullable=True)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs) 