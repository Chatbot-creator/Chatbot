"""
ماژول اصلی اپلیکیشن Trunest
این ماژول برای مدیریت و سازماندهی کل API بک‌اند استفاده می‌شود
"""
import logging
import os
from dotenv import load_dotenv

# بارگذاری متغیرهای محیطی
load_dotenv("config.env")

# تنظیم لاگر
logging_level = logging.DEBUG if os.getenv("ENV") == "development" else logging.INFO

logging.basicConfig(
    level=logging_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# تنظیم سطح لاگینگ برای کتابخانه‌های خارجی
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("uvicorn").setLevel(logging.INFO)

# ساخت لاگر اپلیکیشن
app_logger = logging.getLogger("trunest")
app_logger.info("راه‌اندازی اپلیکیشن Trunest") 