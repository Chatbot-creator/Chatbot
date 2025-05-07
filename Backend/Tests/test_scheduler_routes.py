import pytest
from unittest import mock
from fastapi import status
from datetime import datetime

class TestSchedulerRoutes:
    """تست‌های مربوط به API زمانبند"""

    @mock.patch("App.properties.routes.get_scheduler_status")
    def test_get_scheduler_status(self, mock_status, client):
        """تست دریافت وضعیت فعلی زمانبندی"""
        # تنظیم داده‌های بازگشتی شبیه‌سازی شده
        mock_status.return_value = {
            "is_running": True,
            "last_run_time": datetime.now().isoformat(),
            "next_run_time": datetime.now().isoformat(),
            "update_interval_seconds": 86400,
            "execution_history": [
                {
                    "timestamp": datetime.now().isoformat(),
                    "success": True,
                    "message": "عملیات به‌روزرسانی با موفقیت انجام شد. 10 آیتم پردازش شده",
                    "duration_seconds": 2.5,
                    "items_count": 10
                }
            ]
        }
        
        # ارسال درخواست
        response = client.get("/api/properties/scheduler/status")
        
        # بررسی پاسخ
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "is_running" in data
        assert "last_run_time" in data
        assert "next_run_time" in data
        assert "update_interval_seconds" in data
        assert "execution_history" in data
        
        # بررسی فراخوانی تابع وضعیت
        assert mock_status.called
    
    @mock.patch("App.properties.routes.start_scheduler")
    def test_start_scheduler(self, mock_start, client):
        """تست شروع زمانبندی"""
        # تنظیم نتیجه شبیه‌سازی شده
        mock_start.return_value = True
        
        # ارسال درخواست
        response = client.post("/api/properties/scheduler/start")
        
        # بررسی پاسخ
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        
        # بررسی فراخوانی تابع شروع زمانبند
        assert mock_start.called
    
    @mock.patch("App.properties.routes.start_scheduler")
    def test_start_scheduler_already_running(self, mock_start, client):
        """تست شروع زمانبندی در حالیکه قبلاً در حال اجراست"""
        # تنظیم نتیجه شبیه‌سازی شده
        mock_start.return_value = False
        
        # ارسال درخواست
        response = client.post("/api/properties/scheduler/start")
        
        # بررسی پاسخ
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is False
        assert "message" in data
        assert "قبلاً در حال اجراست" in data["message"]
        
        # بررسی فراخوانی تابع شروع زمانبند
        assert mock_start.called
    
    @mock.patch("App.properties.routes.stop_scheduler")
    def test_stop_scheduler(self, mock_stop, client):
        """تست توقف زمانبندی"""
        # تنظیم نتیجه شبیه‌سازی شده
        mock_stop.return_value = True
        
        # ارسال درخواست
        response = client.post("/api/properties/scheduler/stop")
        
        # بررسی پاسخ
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert "با موفقیت متوقف شد" in data["message"]
        
        # بررسی فراخوانی تابع توقف زمانبند
        assert mock_stop.called
    
    @mock.patch("App.properties.routes.stop_scheduler")
    def test_stop_scheduler_already_stopped(self, mock_stop, client):
        """تست توقف زمانبندی در حالیکه قبلاً متوقف شده است"""
        # تنظیم نتیجه شبیه‌سازی شده
        mock_stop.return_value = False
        
        # ارسال درخواست
        response = client.post("/api/properties/scheduler/stop")
        
        # بررسی پاسخ
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is False
        assert "message" in data
        assert "در حال حاضر متوقف است" in data["message"]
        
        # بررسی فراخوانی تابع توقف زمانبند
        assert mock_stop.called 