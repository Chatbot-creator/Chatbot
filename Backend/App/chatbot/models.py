"""
مدل‌های دیتابیس برای چت‌بات
"""

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON, LargeBinary
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from App.database import Base

class ChatSession(Base):
    """مدل جلسه چت"""
    
    __tablename__ = "chat_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    session_data = Column(JSON, nullable=True)  # داده‌های جلسه به صورت JSON
    
    # رابطه با پیام‌ها
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")
    voice_messages = relationship("VoiceMessage", back_populates="session", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<ChatSession(id={self.id}, user_id={self.user_id})>"

class ChatMessage(Base):
    """مدل پیام‌های چت"""
    
    __tablename__ = "chat_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False)
    is_user = Column(Boolean, default=True)  # True اگر پیام از کاربر باشد، False اگر از بات باشد
    message = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # رابطه با جلسه
    session = relationship("ChatSession", back_populates="messages")
    
    def __repr__(self):
        return f"<ChatMessage(id={self.id}, is_user={self.is_user})>"

class VoiceMessage(Base):
    """مدل پیام‌های صوتی"""
    
    __tablename__ = "voice_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False)
    file_data = Column(LargeBinary)  # فایل صوتی به صورت باینری
    original_filename = Column(String)
    transcribed_text = Column(Text, nullable=True)  # متن استخراج شده از صوت
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # رابطه با جلسه چت
    session = relationship("ChatSession", back_populates="voice_messages")
    
    def __repr__(self):
        return f"<VoiceMessage(id={self.id}, filename={self.original_filename})>"

class PropertyPreference(Base):
    """مدل ترجیحات املاک کاربر"""
    
    __tablename__ = "property_preferences"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False)
    district = Column(String, nullable=True)
    min_price = Column(Integer, nullable=True)
    max_price = Column(Integer, nullable=True)
    bedrooms = Column(Integer, nullable=True)
    bathrooms = Column(Integer, nullable=True)
    property_type = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self):
        return f"<PropertyPreference(id={self.id}, user_id={self.user_id})>"