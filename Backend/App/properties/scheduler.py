import asyncio
import logging
import threading
import time
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any, List

from App.database import SessionLocal
from App.properties.service import update_properties_from_api
from App.properties.service import update_filtered_properties_from_api, enrich_filtered_properties_from_api


# تنظیم لاگر
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# فاصله زمانی بین به‌روزرسانی‌ها (24 ساعت به ثانیه)
UPDATE_INTERVAL_SECONDS = 24 * 60 * 60

# متغیرهای نگهدارنده وضعیت زمانبندی
execution_history: List[Dict[str, Any]] = []
max_history_items = 10
scheduler_thread: Optional[threading.Thread] = None
is_running = False
last_run_time: Optional[datetime] = None
next_run_time: Optional[datetime] = None

# async def scheduled_task():
#     """
#     وظیفه زمانبندی شده برای به‌روزرسانی خودکار داده‌ها.
    
#     این تابع در هر بار اجرای زمانبند فراخوانی می‌شود و وظیفه به‌روزرسانی
#     داده‌ها از API و ذخیره‌سازی آنها در دیتابیس را انجام می‌دهد.
    
#     همچنین تاریخچه اجرا را ثبت کرده و زمان اجرای بعدی را تنظیم می‌کند.
#     """
#     global last_run_time, next_run_time, execution_history
    
#     logger.info("شروع وظیفه زمانبندی شده به‌روزرسانی داده‌ها")
    
#     try:
#         # ایجاد جلسه دیتابیس
#         db = SessionLocal()
#         try:
#             # به‌روزرسانی داده‌ها
#             last_run_time = datetime.now()
#             result = await update_properties_from_api(db)
            
#             # به‌روزرسانی تاریخچه
#             execution_history.append({
#                 "timestamp": last_run_time.isoformat(),
#                 "success": result["success"],
#                 "message": result["message"],
#                 "duration_seconds": result["duration_seconds"],
#                 "items_count": result["items_count"]
#             })
            
#             # محدود کردن تعداد آیتم‌های تاریخچه
#             if len(execution_history) > max_history_items:
#                 execution_history = execution_history[-max_history_items:]
            
#             # تنظیم زمان اجرای بعدی
#             next_run_time = last_run_time + timedelta(seconds=UPDATE_INTERVAL_SECONDS)
#             logger.info(f"به‌روزرسانی بعدی در {next_run_time} انجام خواهد شد")
            
#         finally:
#             db.close()
    
#     except Exception as e:
#         logger.error(f"خطا در اجرای وظیفه زمانبندی شده: {str(e)}")

async def scheduled_task():
    """
    وظیفه زمانبندی شده برای به‌روزرسانی خودکار داده‌ها.
    """
    global last_run_time, next_run_time, execution_history

    logger.info("شروع وظیفه زمانبندی شده به‌روزرسانی داده‌ها")

    try:
        db = SessionLocal()
        try:
            last_run_time = datetime.now()

            # ▶️ به‌روزرسانی دیتای اصلی
            result_main = await update_properties_from_api(db)

            # ▶️ به‌روزرسانی دیتای فیلتر شده
            result_filtered = await update_filtered_properties_from_api(db)

            # ▶️ تکمیل داده‌های اضافی برای فیلتر شده‌ها
            await enrich_filtered_properties_from_api(db)

            # ذخیره در تاریخچه
            execution_history.append({
                "timestamp": last_run_time.isoformat(),
                "success": result_main["success"] and result_filtered["success"],
                "message": f"اصلی: {result_main['message']} | فیلتر: {result_filtered['message']}",
                "duration_seconds": result_main["duration_seconds"] + result_filtered["duration_seconds"],
                "items_count": result_main["items_count"] + result_filtered["items_count"]
            })

            if len(execution_history) > max_history_items:
                execution_history = execution_history[-max_history_items:]

            next_run_time = last_run_time + timedelta(seconds=UPDATE_INTERVAL_SECONDS)
            logger.info(f"✅ به‌روزرسانی بعدی در {next_run_time} انجام خواهد شد")

        finally:
            db.close()

    except Exception as e:
        logger.error(f"❌ خطا در اجرای وظیفه زمانبندی شده: {str(e)}")

def run_scheduler_loop():
    """
    حلقه اصلی زمانبندی که وظیفه را در فواصل مشخص اجرا می‌کند.
    
    این تابع به عنوان یک رشته جدا اجرا می‌شود و در فواصل زمانی مشخص شده،
    وظیفه به‌روزرسانی داده‌ها را فراخوانی می‌کند.
    
    حلقه تا زمانی که is_running برابر با True باشد به اجرای خود ادامه می‌دهد.
    """
    global is_running, next_run_time
    
    logger.info("حلقه زمانبندی شروع به کار کرد")
    is_running = True
    
    try:
        while is_running:
            # اجرای وظیفه زمانبندی شده
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(scheduled_task())
            loop.close()
            
            # انتظار تا زمان بعدی اجرا
            logger.info(f"انتظار برای {UPDATE_INTERVAL_SECONDS} ثانیه تا اجرای بعدی...")
            for _ in range(UPDATE_INTERVAL_SECONDS):
                if not is_running:
                    break
                time.sleep(1)
    
    except Exception as e:
        logger.error(f"خطا در حلقه زمانبندی: {str(e)}")
        is_running = False

def start_scheduler():
    """
    شروع زمانبندی در یک رشته جداگانه.
    
    این تابع یک رشته جدید برای اجرای زمانبند ایجاد می‌کند.
    اگر زمانبند قبلا در حال اجرا باشد، تابع False را برمی‌گرداند.
    
    Returns:
        bool: True اگر زمانبند با موفقیت شروع شده باشد، در غیر این صورت False
    """
    global scheduler_thread, is_running, next_run_time
    
    if scheduler_thread and scheduler_thread.is_alive():
        logger.warning("زمانبندی قبلاً در حال اجراست")
        return False
    
    # ایجاد و شروع رشته زمانبندی
    try:
        is_running = True
        next_run_time = datetime.now()
        scheduler_thread = threading.Thread(target=run_scheduler_loop, daemon=True)
        scheduler_thread.start()
        
        logger.info("زمانبندی با موفقیت شروع شد")
        return True
    except Exception as e:
        logger.error(f"خطا در شروع زمانبندی: {str(e)}")
        is_running = False
        return False

def stop_scheduler():
    """
    توقف زمانبندی.
    
    این تابع زمانبند را متوقف می‌کند با تغییر مقدار is_running به False.
    اگر زمانبند در حال اجرا نباشد، False را برمی‌گرداند.
    
    Returns:
        bool: True اگر درخواست توقف زمانبند با موفقیت انجام شده باشد، در غیر این صورت False
    """
    global is_running
    
    if not is_running:
        logger.warning("زمانبندی در حال حاضر متوقف است")
        return False
    
    is_running = False
    logger.info("درخواست توقف زمانبندی دریافت شد")
    return True

def get_scheduler_status():
    """
    دریافت وضعیت فعلی زمانبندی.
    
    این تابع اطلاعات وضعیت زمانبند شامل وضعیت اجرا، زمان اجرای آخر،
    زمان اجرای بعدی، فاصله زمانی به‌روزرسانی و تاریخچه اجرا را برمی‌گرداند.
    
    Returns:
        Dict[str, Any]: دیکشنری حاوی اطلاعات وضعیت زمانبند
    """
    global is_running, last_run_time, next_run_time, execution_history
    
    return {
        "is_running": is_running,
        "last_run_time": last_run_time.isoformat() if last_run_time else None,
        "next_run_time": next_run_time.isoformat() if next_run_time else None,
        "update_interval_seconds": UPDATE_INTERVAL_SECONDS,
        "execution_history": execution_history
    }

def initialize_scheduler():
    """
    راه‌اندازی خودکار زمانبندی در شروع برنامه.
    
    این تابع در شروع برنامه فراخوانی می‌شود و زمانبند را به طور خودکار شروع می‌کند.
    
    Returns:
        bool: نتیجه شروع زمانبند (True اگر با موفقیت شروع شده باشد)
    """
    logger.info("در حال راه‌اندازی خودکار زمانبندی...")
    return start_scheduler() 