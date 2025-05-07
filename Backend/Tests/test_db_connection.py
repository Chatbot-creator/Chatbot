import unittest
from sqlalchemy import text
from App.database import engine, SessionLocal

class TestDatabaseConnection(unittest.TestCase):
    """تست‌های ارتباط با دیتابیس"""
    
    def test_database_connection(self):
        """تست کردن اتصال به دیتابیس"""
        try:
            # ایجاد اتصال به دیتابیس
            with engine.connect() as connection:
                # اجرای یک کوئری ساده
                result = connection.execute(text("SELECT 1"))
                value = result.scalar()
                self.assertEqual(value, 1)
                print("اتصال به دیتابیس با موفقیت برقرار شد.")
        except Exception as e:
            self.fail(f"خطا در اتصال به دیتابیس: {str(e)}")
    
    def test_tables_exist(self):
        """بررسی وجود جداول اصلی در دیتابیس"""
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        # چاپ لیست جداول
        print(f"جداول موجود در دیتابیس: {tables}")
        
        # بررسی وجود جداول اصلی
        essential_tables = ['properties', 'sessions']
        for table in essential_tables:
            self.assertIn(table, tables, f"جدول {table} در دیتابیس وجود ندارد!")

    def test_session_crud(self):
        """تست عملیات CRUD روی جدول sessions"""
        from sqlalchemy.orm import Session
        
        # ایجاد یک رکورد تست
        with SessionLocal() as db:
            # بررسی امکان نوشتن در جدول
            try:
                # اجرای یک کوئری برای درج داده تست
                db.execute(
                    text("INSERT INTO sessions (session_id, user_agent, ip_address, created_at, last_activity, expires_at, is_active, data) VALUES (:session_id, :user_agent, :ip_address, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :is_active, :data)"),
                    {
                        "session_id": "test_session_123", 
                        "user_agent": "Test Agent", 
                        "ip_address": "127.0.0.1",
                        "is_active": True,
                        "data": "{}"
                    }
                )
                db.commit()
                print("رکورد تست با موفقیت در جدول sessions درج شد.")
                
                # خواندن رکورد تست
                result = db.execute(
                    text("SELECT session_id, user_agent FROM sessions WHERE session_id = :session_id"),
                    {"session_id": "test_session_123"}
                ).fetchone()
                
                self.assertIsNotNone(result, "رکورد تست یافت نشد!")
                self.assertEqual(result[0], "test_session_123")
                self.assertEqual(result[1], "Test Agent")
                print("رکورد تست با موفقیت خوانده شد.")
                
                # پاک کردن رکورد تست
                db.execute(
                    text("DELETE FROM sessions WHERE session_id = :session_id"),
                    {"session_id": "test_session_123"}
                )
                db.commit()
                print("رکورد تست با موفقیت حذف شد.")
                
            except Exception as e:
                db.rollback()
                self.fail(f"خطا در عملیات CRUD: {str(e)}")

if __name__ == '__main__':
    unittest.main() 