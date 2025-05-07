from App.database import engine
from sqlalchemy import inspect

def check_database_structure():
    """بررسی ساختار دیتابیس"""
    inspector = inspect(engine)
    
    # نمایش همه جداول
    tables = inspector.get_table_names()
    print(f"جداول موجود در دیتابیس: {tables}")
    
    # بررسی ساختار هر جدول
    for table in tables:
        columns = inspector.get_columns(table)
        print(f"\nساختار جدول {table}:")
        for column in columns:
            print(f"  - {column['name']} ({column['type']})")

if __name__ == "__main__":
    check_database_structure() 