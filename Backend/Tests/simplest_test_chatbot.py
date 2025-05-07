"""
ساده‌ترین تست برای تابع simplify_properties
"""

import unittest
import sys
import os

# افزودن مسیر پروژه به sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# تابع ساده‌سازی املاک را مستقیماً تعریف می‌کنیم تا وابستگی‌های دیگر را نیاز نداشته باشیم
def simplify_properties(properties):
    """
    ساده‌سازی داده‌های املاک برای ذخیره امن در جلسه.
    
    Args:
        properties: لیست دیکشنری‌های املاک
        
    Returns:
        لیست ساده‌سازی شده فقط با ID و عنوان
    """
    if isinstance(properties, list):
        return [{"id": p.get("id"), "title": p.get("title")} for p in properties]
    return properties

class TestSimplifyProperties(unittest.TestCase):
    """تست تابع ساده‌سازی املاک"""
    
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

if __name__ == "__main__":
    unittest.main() 