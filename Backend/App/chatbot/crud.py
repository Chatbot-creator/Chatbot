"""
عملیات CRUD برای داده‌های چت‌بات
"""

from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import json

from .models import ChatSession, ChatMessage, PropertyPreference

# --- عملیات مربوط به جلسه‌های چت ---

def get_chat_session(db: Session, user_id: str) -> Optional[ChatSession]:
    """
    دریافت آخرین جلسه چت کاربر
    
    Args:
        db: نشست دیتابیس
        user_id: شناسه کاربر
        
    Returns:
        جلسه چت یا None اگر وجود نداشته باشد
    """
    return db.query(ChatSession).filter(ChatSession.user_id == user_id).order_by(
        ChatSession.created_at.desc()
    ).first()

def create_chat_session(db: Session, user_id: str, session_data: Dict = None) -> ChatSession:
    """
    ایجاد جلسه چت جدید
    
    Args:
        db: نشست دیتابیس
        user_id: شناسه کاربر
        session_data: داده‌های جلسه (اختیاری)
        
    Returns:
        جلسه چت ایجاد شده
    """
    db_session = ChatSession(user_id=user_id, session_data=session_data)
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    return db_session

def update_chat_session(db: Session, chat_session: ChatSession, session_data: Dict) -> ChatSession:
    """
    بروزرسانی داده‌های جلسه چت
    
    Args:
        db: نشست دیتابیس
        chat_session: جلسه چت
        session_data: داده‌های جلسه جدید
        
    Returns:
        جلسه چت بروزرسانی شده
    """
    chat_session.session_data = session_data
    db.commit()
    db.refresh(chat_session)
    return chat_session

# --- عملیات مربوط به پیام‌های چت ---

def get_chat_messages(db: Session, session_id: int, limit: int = 100) -> List[ChatMessage]:
    """
    دریافت پیام‌های یک جلسه چت
    
    Args:
        db: نشست دیتابیس
        session_id: شناسه جلسه
        limit: حداکثر تعداد پیام‌ها
        
    Returns:
        لیست پیام‌ها
    """
    return db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.created_at.asc()).limit(limit).all()

def create_chat_message(
    db: Session, 
    session_id: int, 
    message: str, 
    is_user: bool = True
) -> ChatMessage:
    """
    ایجاد پیام چت جدید
    
    Args:
        db: نشست دیتابیس
        session_id: شناسه جلسه
        message: متن پیام
        is_user: آیا پیام از طرف کاربر است
        
    Returns:
        پیام چت ایجاد شده
    """
    db_message = ChatMessage(
        session_id=session_id,
        message=message,
        is_user=is_user
    )
    db.add(db_message)
    db.commit()
    db.refresh(db_message)
    return db_message

# --- عملیات مربوط به ترجیحات املاک ---

def get_property_preference(db: Session, user_id: str) -> Optional[PropertyPreference]:
    """
    دریافت ترجیحات املاک کاربر
    
    Args:
        db: نشست دیتابیس
        user_id: شناسه کاربر
        
    Returns:
        ترجیحات املاک یا None اگر وجود نداشته باشد
    """
    return db.query(PropertyPreference).filter(
        PropertyPreference.user_id == user_id
    ).first()

def create_or_update_property_preference(
    db: Session, 
    user_id: str, 
    preferences: Dict[str, Any]
) -> PropertyPreference:
    """
    ایجاد یا بروزرسانی ترجیحات املاک
    
    Args:
        db: نشست دیتابیس
        user_id: شناسه کاربر
        preferences: ترجیحات جدید
        
    Returns:
        ترجیحات املاک ایجاد یا بروزرسانی شده
    """
    # بررسی وجود رکورد قبلی
    db_preference = get_property_preference(db, user_id)
    
    if db_preference:
        # بروزرسانی فیلدها
        for key, value in preferences.items():
            if hasattr(db_preference, key):
                setattr(db_preference, key, value)
        
        db.commit()
        db.refresh(db_preference)
        return db_preference
    else:
        # ایجاد رکورد جدید
        db_preference = PropertyPreference(user_id=user_id, **preferences)
        db.add(db_preference)
        db.commit()
        db.refresh(db_preference)
        return db_preference 