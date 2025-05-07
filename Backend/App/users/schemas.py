from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any

class SessionBase(BaseModel):
    """مدل پایه جلسه"""
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None

class SessionCreate(SessionBase):
    """مدل ایجاد جلسه جدید"""
    pass

class SessionData(SessionBase):
    """مدل کامل داده‌های جلسه"""
    session_id: str
    created_at: datetime
    last_activity: datetime
    expires_at: datetime
    is_active: bool = True
    data: Optional[str] = None
    
    class Config:
        orm_mode = True
        from_attributes = True

class SessionUpdate(BaseModel):
    """مدل به‌روزرسانی جلسه"""
    data: Optional[str] = None
    is_active: Optional[bool] = None

class SessionResponse(BaseModel):
    """مدل پاسخ برای ایجاد جلسه"""
    session_id: str
    message: str
    expires_at: datetime 