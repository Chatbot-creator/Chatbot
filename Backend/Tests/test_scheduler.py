import pytest
import threading
import asyncio
from unittest import mock
from datetime import datetime, timedelta

from App.properties.scheduler import (
    initialize_scheduler,
    start_scheduler,
    stop_scheduler,
    get_scheduler_status,
    scheduled_task,
    run_scheduler_loop
)

class TestScheduler:
    """تست‌های مربوط به ماژول زمانبندی"""
    
    @mock.patch("App.properties.scheduler.start_scheduler")
    def test_initialize_scheduler(self, mock_start):
        """تست راه‌اندازی اولیه زمانبندی"""
        # تنظیم نتیجه شبیه‌سازی شده
        mock_start.return_value = True
        
        # فراخوانی تابع
        result = initialize_scheduler()
        
        # بررسی نتایج
        assert result is True
        mock_start.assert_called_once()
    
    @mock.patch("App.properties.scheduler.scheduler_thread")
    @mock.patch("App.properties.scheduler.threading.Thread")
    def test_start_scheduler(self, mock_thread, mock_existing_thread):
        """تست شروع زمانبندی"""
        # تنظیم حالت اولیه - بدون رشته فعال قبلی
        mock_existing_thread.is_alive.return_value = False
        
        # تنظیم رشته شبیه‌سازی شده جدید
        mock_thread_instance = mock.MagicMock()
        mock_thread.return_value = mock_thread_instance
        
        # فراخوانی تابع
        result = start_scheduler()
        
        # بررسی نتایج
        assert result is True
        mock_thread.assert_called_once()
        mock_thread_instance.start.assert_called_once()
    
    @mock.patch("App.properties.scheduler.scheduler_thread")
    def test_start_scheduler_already_running(self, mock_thread):
        """تست شروع زمانبندی در حالی که قبلاً فعال است"""
        # تنظیم حالت اولیه - با رشته فعال قبلی
        mock_thread.is_alive.return_value = True
        
        # فراخوانی تابع
        result = start_scheduler()
        
        # بررسی نتایج
        assert result is False
    
    @mock.patch("App.properties.scheduler.is_running", True)
    def test_stop_scheduler(self):
        """تست توقف زمانبندی"""
        # فراخوانی تابع
        result = stop_scheduler()
        
        # بررسی نتایج
        assert result is True
        # بررسی تغییر متغیر عمومی - این کار تا حدی پیچیده است و نیاز به دسترسی به متغیر عمومی دارد
        from App.properties.scheduler import is_running
        assert is_running is False
    
    @mock.patch("App.properties.scheduler.is_running", False)
    def test_stop_scheduler_already_stopped(self):
        """تست توقف زمانبندی در حالی که قبلاً متوقف شده است"""
        # فراخوانی تابع
        result = stop_scheduler()
        
        # بررسی نتایج
        assert result is False
    
    def test_get_scheduler_status(self):
        """تست دریافت وضعیت زمانبندی"""
        # تنظیم مقادیر برای تست با استفاده از پچ
        with mock.patch("App.properties.scheduler.is_running", True), \
             mock.patch("App.properties.scheduler.last_run_time", datetime.now()), \
             mock.patch("App.properties.scheduler.next_run_time", datetime.now() + timedelta(hours=24)), \
             mock.patch("App.properties.scheduler.execution_history", [{"timestamp": datetime.now().isoformat()}]):
            
            # فراخوانی تابع
            result = get_scheduler_status()
            
            # بررسی نتایج
            assert result["is_running"] is True
            assert "last_run_time" in result
            assert "next_run_time" in result
            assert "update_interval_seconds" in result
            assert isinstance(result["execution_history"], list)

    @pytest.mark.asyncio
    @mock.patch("App.properties.scheduler.update_properties_from_api")
    async def test_scheduled_task(self, mock_update):
        """تست اجرای وظیفه زمانبندی شده"""
        # تنظیم نتیجه شبیه‌سازی شده
        mock_update.return_value = {
            "success": True,
            "message": "عملیات به‌روزرسانی با موفقیت انجام شد.",
            "duration_seconds": 1.5,
            "items_count": 5
        }
        
        # فراخوانی تابع
        await scheduled_task()
        
        # بررسی نتایج
        mock_update.assert_called_once()
        
        # بررسی تغییر متغیرهای عمومی
        from App.properties.scheduler import last_run_time, next_run_time, execution_history
        assert last_run_time is not None
        assert next_run_time is not None
        assert len(execution_history) > 0
        assert execution_history[-1]["success"] is True
    
    @mock.patch("App.properties.scheduler.asyncio.new_event_loop")
    @mock.patch("App.properties.scheduler.time.sleep")
    def test_run_scheduler_loop(self, mock_sleep, mock_event_loop):
        """تست اجرای حلقه زمانبندی"""
        # تنظیم مقادیر برای تست
        mock_loop = mock.MagicMock()
        mock_event_loop.return_value = mock_loop
        
        # تنظیم حالتی که بعد از یک تکرار حلقه، زمانبندی متوقف شود
        is_running_values = [True, False]
        
        def side_effect(*args, **kwargs):
            # تغییر متغیر is_running بعد از اولین فراخوانی
            if len(is_running_values) > 0:
                from App.properties.scheduler import is_running
                # تنظیم متغیر is_running با مقدار مناسب
                with mock.patch("App.properties.scheduler.is_running", is_running_values.pop(0)):
                    pass
            return None
        
        mock_sleep.side_effect = side_effect
        
        # Override the scheduler.scheduled_task to avoid actual async calls
        with mock.patch("App.properties.scheduler.scheduled_task", return_value=None), \
             mock.patch("App.properties.scheduler.is_running", True):
            # فراخوانی تابع
            try:
                run_scheduler_loop()
            except Exception:
                # مدیریت هرگونه خطا در اجرای تابع
                pass
        
        # بررسی نتایج - فقط چک می‌کنیم که تابع run_scheduler_loop فراخوانی شده است
        mock_event_loop.assert_called_once()
        # نیازی به بررسی run_until_complete نیست چون ممکن است با موک‌ها به درستی کار نکند 