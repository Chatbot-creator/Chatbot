"""
تست‌های ماژول چت‌بات
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import json
import sys
import os

# افزودن مسیر پروژه به sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app

client = TestClient(app)

@pytest.fixture
def mock_openai_response():
    """ساخت یک پاسخ شبیه‌سازی شده از OpenAI"""
    
    class MockResponse:
        def __init__(self):
            self.choices = [MagicMock()]
            self.choices[0].message = MagicMock()
            self.choices[0].message.content = "این یک پاسخ آزمایشی از چت‌بات است."
    
    return MockResponse()

@pytest.fixture
def mock_property_data():
    """ساخت داده‌های شبیه‌سازی شده املاک"""
    
    return {
        "properties": [
            {
                "id": "123",
                "title": "آپارتمان لوکس در دبی مارینا",
                "low_price": 1200000,
                "district": {"id": "1", "name": "دبی مارینا"},
                "sales_status": {"id": "1", "name": "available"}
            },
            {
                "id": "456",
                "title": "ویلا در نخل جمیرا",
                "low_price": 3500000,
                "district": {"id": "2", "name": "نخل جمیرا"},
                "sales_status": {"id": "1", "name": "available"}
            }
        ],
        "districts": {
            "دبی مارینا": "1",
            "نخل جمیرا": "2"
        }
    }

@patch("App.chatbot.cache.property_cache")
@patch("App.chatbot.chatbot.client.chat.completions.create")
def test_chatbot_message(mock_openai, mock_cache, mock_openai_response, mock_property_data):
    """تست ارسال پیام به چت‌بات و دریافت پاسخ"""
    
    # تنظیم شبیه‌ساز‌ها
    mock_openai.return_value = mock_openai_response
    mock_cache.get.return_value = mock_property_data
    
    # ارسال پیام به چت‌بات
    response = client.post(
        "/api/chatbot/chat",
        json={"message": "ملک در دبی مارینا می‌خواهم"}
    )
    
    # بررسی وضعیت پاسخ
    assert response.status_code == 200
    
    # بررسی محتوای پاسخ
    data = response.json()
    assert "response" in data
    assert "user_id" in data
    assert "chat_history" in data
    
    # بررسی که پاسخ مورد انتظار دریافت شده باشد
    assert data["response"] == "این یک پاسخ آزمایشی از چت‌بات است."
    
    # بررسی تاریخچه چت
    assert len(data["chat_history"]) > 0
    assert "user" in data["chat_history"][0]
    assert "bot" in data["chat_history"][1]

@patch("App.chatbot.cache.property_cache")
def test_get_properties(mock_cache, mock_property_data):
    """تست دریافت لیست املاک از کش"""
    
    # تنظیم شبیه‌ساز
    mock_cache.get.return_value = mock_property_data
    
    # فراخوانی API
    response = client.get("/api/chatbot/properties")
    
    # بررسی وضعیت پاسخ
    assert response.status_code == 200
    
    # بررسی محتوای پاسخ
    data = response.json()
    assert "properties" in data
    assert "districts" in data
    assert "property_count" in data
    assert "district_count" in data
    
    # بررسی تعداد املاک و مناطق
    assert data["property_count"] == 2
    assert data["district_count"] == 2

@patch("App.chatbot.cache.property_cache")
def test_get_properties_empty_cache(mock_cache):
    """تست رفتار API در حالت خالی بودن کش"""
    
    # تنظیم شبیه‌ساز برای حالت خالی
    mock_cache.get.return_value = None
    
    # فراخوانی API
    response = client.get("/api/chatbot/properties")
    
    # بررسی وضعیت خطا
    assert response.status_code == 404
    assert response.json() == {"detail": "No data cached yet."} 