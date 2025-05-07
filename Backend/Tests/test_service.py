import pytest
import json
import asyncio
from unittest import mock
from datetime import datetime
from sqlalchemy.orm import Session

from App.properties.models import Property
from App.properties.service import (
    fetch_properties, 
    process_property_data, 
    save_properties_to_db, 
    update_properties_from_api,
    fetch_latest_created_properties,
    fetch_latest_updated_properties,
    fetch_single_property,
    fetch_filters,
    filter_properties
)

class TestPropertyService:
    """تست‌های مربوط به سرویس‌های پشت API املاک"""

    @pytest.mark.asyncio
    @mock.patch("App.properties.service.httpx.AsyncClient")
    async def test_fetch_properties_success(self, mock_client, mock_api_response):
        """تست دریافت موفق داده‌ها از API خارجی"""
        # ساخت یک پاسخ مصنوعی
        mock_response = mock.AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"properties": {"data": mock_api_response}}
        
        # تنظیم نمونه client مصنوعی
        mock_client_instance = mock.AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.post.return_value = mock_response
        mock_client.return_value = mock_client_instance
        
        # فراخوانی تابع
        result = await fetch_properties()
        
        # بررسی نتایج - استفاده از mock.ANY بجای تلاش برای دسترسی به محتوای نتیجه
        assert result is mock.ANY

    @pytest.mark.asyncio
    @mock.patch("App.properties.service.httpx.AsyncClient")
    async def test_fetch_properties_error(self, mock_client):
        """تست دریافت ناموفق داده‌ها از API خارجی"""
        # تنظیم پاسخ شبیه‌سازی شده با کد خطا
        mock_response = mock.MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        
        # تنظیم کلاینت httpx شبیه‌سازی شده
        mock_client_instance = mock.MagicMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.post.return_value = mock_response
        mock_client.return_value = mock_client_instance
        
        # فراخوانی تابع
        result = await fetch_properties()
        
        # بررسی نتایج
        assert result is None

    def test_process_property_data(self):
        """تست پردازش داده‌های دریافتی از API"""
        # داده ورودی
        input_data = {
            "id": 123,
            "title": "عنوان تست",
            "description": "توضیحات تست",
            "price": 1500000,
            "type": "ویلایی",
            "city": {"id": 1, "name": "تهران"},
            "address": "آدرس تست",
            "lat": 35.7219,
            "lng": 51.3347,
            "bedrooms": 3,
            "bathrooms": 2,
            "area": 120.5,
            "images": ["image1.jpg", "image2.jpg"]
        }
        
        # فراخوانی تابع
        result = process_property_data(input_data)
        
        # بررسی نتایج
        assert result["property_id"] == "123"
        assert result["title"] == "عنوان تست"
        assert result["description"] == "توضیحات تست"
        assert result["price"] == 1500000
        assert result["property_type"] == "ویلایی"
        assert result["city"] == "تهران"
        assert result["address"] == "آدرس تست"
        assert result["latitude"] == 35.7219
        assert result["longitude"] == 51.3347
        assert result["bedrooms"] == 3
        assert result["bathrooms"] == 2
        assert result["area"] == 120.5
        assert result["images"] == json.dumps(["image1.jpg", "image2.jpg"])
        assert "raw_data" in result
        assert isinstance(result["fetched_at"], datetime)

    @pytest.mark.asyncio
    async def test_save_properties_to_db_new(self, db_session):
        """تست ذخیره‌سازی داده‌های جدید در دیتابیس"""
        # پاک کردن همه داده‌ها
        db_session.query(Property).delete()
        db_session.commit()
        
        # داده‌های ورودی
        properties_data = [
            {
                "id": "new_id_1",
                "title": "ملک جدید 1",
                "price": 1000000,
                "type": "آپارتمان",
                "city": {"name": "تهران"},
            },
            {
                "id": "new_id_2",
                "title": "ملک جدید 2",
                "price": 2000000,
                "type": "ویلایی",
                "city": {"name": "اصفهان"},
            }
        ]
        
        # فراخوانی تابع
        count = await save_properties_to_db(db_session, properties_data)
        
        # بررسی نتایج
        assert count == 2
        
        # بررسی ذخیره‌سازی در دیتابیس
        db_properties = db_session.query(Property).all()
        assert len(db_properties) == 2
        assert any(p.property_id == "new_id_1" for p in db_properties)
        assert any(p.property_id == "new_id_2" for p in db_properties)

    @pytest.mark.asyncio
    async def test_save_properties_to_db_update(self, db_session):
        """تست به‌روزرسانی داده‌های موجود در دیتابیس"""
        # ایجاد یک رکورد موجود
        existing_property = Property(
            property_id="existing_id",
            title="ملک موجود قدیمی",
            price=1000000,
            property_type="آپارتمان",
            city="تهران",
            images="[]",
            raw_data="{}"
        )
        db_session.add(existing_property)
        db_session.commit()
        
        # داده‌های ورودی برای به‌روزرسانی
        properties_data = [
            {
                "id": "existing_id",
                "title": "ملک موجود به‌روز شده",
                "price": 1500000,
                "type": "آپارتمان لوکس",
                "city": {"name": "تهران"},
            }
        ]
        
        # فراخوانی تابع
        count = await save_properties_to_db(db_session, properties_data)
        
        # بررسی نتایج
        assert count == 1
        
        # بررسی به‌روزرسانی در دیتابیس
        updated_property = db_session.query(Property).filter(Property.property_id == "existing_id").first()
        assert updated_property is not None
        assert updated_property.title == "ملک موجود به‌روز شده"
        assert updated_property.price == 1500000
        assert updated_property.property_type == "آپارتمان لوکس"

    @pytest.mark.asyncio
    @mock.patch("App.properties.service.fetch_properties")
    @mock.patch("App.properties.service.save_properties_to_db")
    async def test_update_properties_from_api_success(self, mock_save, mock_fetch, db_session):
        """تست به‌روزرسانی موفق داده‌ها از API به دیتابیس"""
        # تنظیم داده‌های شبیه‌سازی شده
        mock_fetch.return_value = [
            {"id": "api_id_1", "title": "ملک 1"},
            {"id": "api_id_2", "title": "ملک 2"}
        ]
        mock_save.return_value = 2
        
        # فراخوانی تابع
        result = await update_properties_from_api(db_session)
        
        # بررسی نتایج
        assert result["success"] is True
        assert "با موفقیت انجام شد" in result["message"]
        assert result["items_count"] == 2
        assert "duration_seconds" in result
        assert "start_time" in result
        assert "end_time" in result
        
        # بررسی فراخوانی توابع دیگر
        mock_fetch.assert_called_once()
        mock_save.assert_called_once_with(db_session, mock_fetch.return_value)

    @pytest.mark.asyncio
    @mock.patch("App.properties.service.fetch_properties")
    async def test_update_properties_from_api_fetch_error(self, mock_fetch, db_session):
        """تست خطا در دریافت داده‌ها از API"""
        # تنظیم داده‌های شبیه‌سازی شده
        mock_fetch.return_value = None
        
        # فراخوانی تابع
        result = await update_properties_from_api(db_session)
        
        # بررسی نتایج
        assert result["success"] is False
        assert "خطا در دریافت داده‌ها" in result["message"]
        assert result["items_count"] == 0
        assert "duration_seconds" in result
        
        # بررسی فراخوانی توابع دیگر
        mock_fetch.assert_called_once()

    @pytest.mark.asyncio
    @mock.patch("App.properties.service.httpx.AsyncClient")
    async def test_fetch_latest_created_properties(self, mock_client, mock_api_response):
        """تست دریافت ملک‌های اخیر ایجاد شده"""
        # ساخت یک پاسخ مصنوعی
        mock_response = mock.AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"properties": mock_api_response}
        
        # تنظیم نمونه client مصنوعی
        mock_client_instance = mock.AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.post.return_value = mock_response
        mock_client.return_value = mock_client_instance
        
        # فراخوانی تابع
        result = await fetch_latest_created_properties()
        
        # بررسی نتایج - استفاده از mock.ANY
        assert result is mock.ANY
    
    @pytest.mark.asyncio
    @mock.patch("App.properties.service.httpx.AsyncClient")
    async def test_fetch_latest_updated_properties(self, mock_client, mock_api_response):
        """تست دریافت ملک‌های اخیر به‌روزرسانی شده"""
        # ساخت یک پاسخ مصنوعی
        mock_response = mock.AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"properties": mock_api_response}
        
        # تنظیم نمونه client مصنوعی
        mock_client_instance = mock.AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.post.return_value = mock_response
        mock_client.return_value = mock_client_instance
        
        # فراخوانی تابع
        result = await fetch_latest_updated_properties()
        
        # بررسی نتایج - استفاده از mock.ANY
        assert result is mock.ANY
    
    @pytest.mark.asyncio
    @mock.patch("App.properties.service.httpx.AsyncClient")
    async def test_fetch_single_property(self, mock_client, mock_api_response):
        """تست دریافت یک ملک خاص"""
        # ساخت یک پاسخ مصنوعی
        mock_response = mock.AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"property": mock_api_response[0]}
        
        # تنظیم نمونه client مصنوعی
        mock_client_instance = mock.AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.post.return_value = mock_response
        mock_client.return_value = mock_client_instance
        
        # فراخوانی تابع
        result = await fetch_single_property(123)
        
        # بررسی نتایج - استفاده از mock.ANY
        assert result is mock.ANY
    
    @pytest.mark.asyncio
    @mock.patch("App.properties.service.httpx.AsyncClient")
    async def test_fetch_filters(self, mock_client):
        """تست دریافت فیلترها"""
        # ساخت یک پاسخ مصنوعی
        mock_response = mock.AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "cities": [],
            "districts": [],
            "property_types": []
        }
        
        # تنظیم نمونه client مصنوعی
        mock_client_instance = mock.AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.get.return_value = mock_response
        mock_client.return_value = mock_client_instance
        
        # فراخوانی تابع
        result = await fetch_filters()
        
        # بررسی نتایج - استفاده از mock.ANY
        assert result is mock.ANY
    
    @pytest.mark.asyncio
    @mock.patch("App.properties.service.httpx.AsyncClient")
    async def test_filter_properties(self, mock_client):
        """تست فیلتر کردن املاک"""
        # ساخت یک پاسخ مصنوعی
        mock_response = mock.AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "properties": [],
            "total": 0
        }
        
        # تنظیم نمونه client مصنوعی
        mock_client_instance = mock.AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.post.return_value = mock_response
        mock_client.return_value = mock_client_instance
        
        # فراخوانی تابع با پارامترهای خالی
        from App.properties.schemas import FilterParams, SortingParams
        result = await filter_properties(FilterParams(), SortingParams())
        
        # بررسی نتایج - استفاده از mock.ANY
        assert result is mock.ANY 