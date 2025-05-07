"""
تست مستقل برای چت‌بات
"""

import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# افزودن مسیر پروژه به sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from App.chatbot.cache import property_cache
from App.chatbot.property_manager import filter_properties
from App.chatbot.chatbot import simplify_properties

class TestChatbotUtils(unittest.TestCase):
    """تست‌های ابزارهای چت‌بات"""
    
    def test_simplify_properties(self):
        """تست تابع ساده‌سازی املاک"""
        # داده‌های تست
        test_data = [
            {"id": "123", "title": "ملک اول", "description": "توضیحات اضافی"},
            {"id": "456", "title": "ملک دوم", "price": 1000000}
        ]
        
        # اجرای تابع
        result = simplify_properties(test_data)
        
        # بررسی نتایج
        self.assertEqual(len(result), 2, "تعداد املاک باید حفظ شود")
        self.assertEqual(result[0]["id"], "123", "شناسه ملک اول باید حفظ شود")
        self.assertEqual(result[0]["title"], "ملک اول", "عنوان ملک اول باید حفظ شود")
        self.assertNotIn("description", result[0], "توضیحات باید حذف شده باشد")
        self.assertEqual(result[1]["id"], "456", "شناسه ملک دوم باید حفظ شود")
        self.assertEqual(result[1]["title"], "ملک دوم", "عنوان ملک دوم باید حفظ شود")
        self.assertNotIn("price", result[1], "قیمت باید حذف شده باشد")
    
    def test_simplify_properties_empty(self):
        """تست تابع ساده‌سازی با لیست خالی"""
        self.assertEqual(simplify_properties([]), [], "لیست خالی باید لیست خالی برگرداند")
    
    def test_simplify_properties_none(self):
        """تست تابع ساده‌سازی با ورودی None"""
        self.assertEqual(simplify_properties(None), None, "ورودی None باید None برگرداند")
    
    def test_simplify_properties_not_list(self):
        """تست تابع ساده‌سازی با ورودی غیر لیست"""
        data = {"not": "a list"}
        self.assertEqual(simplify_properties(data), data, "ورودی غیر لیست باید همان برگردانده شود")

    @patch("App.chatbot.property_manager.requests.post")
    def test_filter_properties(self, mock_post):
        """تست تابع فیلتر املاک"""
        # ساخت موک پاسخ
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "properties": [
                {
                    "id": "123",
                    "title": "آپارتمان لوکس",
                    "low_price": 1200000,
                    "district": {"id": "1", "name": "منطقه تست"},
                    "sales_status": {"name": "available"}
                },
                {
                    "id": "456",
                    "title": "ویلا",
                    "low_price": 3500000,
                    "district": {"id": "1", "name": "منطقه دیگر"},
                    "sales_status": {"name": "available"}
                },
                {
                    "id": "789",
                    "title": "ملک فروخته شده",
                    "low_price": 500000,
                    "district": {"id": "1", "name": "منطقه تست"},
                    "sales_status": {"name": "sold"}
                }
            ]
        }
        mock_post.return_value = mock_response
        
        # اجرای تابع با فیلتر قیمت
        filters = {"min_price": 1000000, "max_price": 2000000}
        result = filter_properties(filters)
        
        # بررسی نتایج
        self.assertEqual(len(result), 1, "باید فقط یک ملک با فیلتر قیمت پیدا شود")
        self.assertEqual(result[0]["id"], "123", "شناسه ملک باید 123 باشد")


if __name__ == "__main__":
    unittest.main() 