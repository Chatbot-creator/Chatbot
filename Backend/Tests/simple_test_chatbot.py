"""
تست ساده و مستقل برای چت‌بات
"""

import unittest
from unittest.mock import patch, MagicMock

class TestChatbot(unittest.TestCase):
    """کلاس تست ساده برای چت‌بات"""
    
    @patch("builtins.print")
    def test_basic_print(self, mock_print):
        """یک تست ساده برای اطمینان از کارکرد unittest"""
        print("تست چت‌بات")
        mock_print.assert_called_with("تست چت‌بات")
    
    def test_basic_assertion(self):
        """تست ساده برای بررسی اسرشن‌ها"""
        self.assertEqual(1 + 1, 2, "عملیات جمع باید درست کار کند")
        self.assertTrue(True, "مقدار True باید True باشد")
        self.assertFalse(False, "مقدار False باید False باشد")
        
if __name__ == "__main__":
    unittest.main() 