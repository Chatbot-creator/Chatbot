import os
import pytest
import asyncio
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from typing import Dict, Generator, Any
from datetime import datetime
from unittest.mock import patch

from App.database import Base, get_db
from App.properties.models import Property
from main import app

# تنظیم دیتابیس تست
TEST_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session():
    """ایجاد یک نشست دیتابیس تست برای هر تست"""
    # ایجاد جداول دیتابیس
    Base.metadata.create_all(bind=engine)
    
    # ایجاد نشست
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        
    # پاکسازی دیتابیس بعد از هر تست
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def client(db_session):
    """ایجاد کلاینت تست برای FastAPI"""
    # تابع وابستگی برای استفاده از نشست تست
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    # Mock schedulers to prevent them from starting during tests
    with patch('App.properties.scheduler.start_scheduler', return_value=True), \
         patch('App.chatbot.cache.start_scheduler') as mock_chatbot_scheduler:
        
        # جایگزینی وابستگی دیتابیس با نشست تست
        app.dependency_overrides[get_db] = override_get_db
        
        # ایجاد کلاینت تست
        with TestClient(app) as test_client:
            yield test_client
        
        # حذف جایگزینی وابستگی بعد از تست
        app.dependency_overrides.clear()

@pytest.fixture(scope="function")
def test_property(db_session):
    """ایجاد یک ملک تست در دیتابیس"""
    property_data = {
        "property_id": "test123",
        "title": "ملک تست",
        "description": "توضیحات ملک تست",
        "price": 1000000.0,
        "property_type": "آپارتمان",
        "city": "تهران",
        "address": "خیابان تست، پلاک 1",
        "latitude": 35.7219,
        "longitude": 51.3347,
        "bedrooms": 2,
        "bathrooms": 1,
        "area": 85.5,
        "images": "[]",
        "raw_data": "{}",
        "fetched_at": datetime.now()
    }
    
    # ایجاد و ذخیره ملک در دیتابیس
    db_property = Property(**property_data)
    db_session.add(db_property)
    db_session.commit()
    db_session.refresh(db_property)
    
    return db_property

@pytest.fixture
def mock_api_response():
    """داده شبیه‌سازی شده برای پاسخ API"""
    return [
        {
            "id": "api123",
            "title": "ملک API",
            "description": "توضیحات ملک API",
            "price": 2000000,
            "type": "ویلایی",
            "city": {"id": 1, "name": "تهران"},
            "address": "آدرس API",
            "lat": 35.7219,
            "lng": 51.3347,
            "bedrooms": 3,
            "bathrooms": 2,
            "area": 150.0,
            "images": ["image1.jpg", "image2.jpg"]
        }
    ]

# برای تست‌های asyncio
@pytest.fixture
def event_loop():
    """ایجاد حلقه رویداد برای تست‌های asyncio"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close() 