from fastapi import APIRouter, HTTPException, status, Cookie, Request, Response, Depends
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.exc import SQLAlchemyError
from typing import List, Optional
from datetime import datetime, timedelta
import uuid

from App.database import get_db
from .models import Session
from .schemas import SessionCreate, SessionData, SessionResponse, SessionUpdate

router = APIRouter()

def get_session_from_db(
    session_id: str, 
    db: DBSession = Depends(get_db)
) -> Session:
    """دریافت جلسه از دیتابیس با شناسه"""
    db_session = db.query(Session).filter(Session.session_id == session_id).first()
    if not db_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"جلسه با شناسه {session_id} یافت نشد"
        )
    
    # بررسی انقضای جلسه
    if db_session.is_expired():
        db_session.is_active = False
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="جلسه منقضی شده است"
        )
    
    return db_session

def create_new_session_in_db(
    request: Request, 
    db: DBSession = Depends(get_db)
) -> Session:
    """ایجاد یک جلسه جدید در دیتابیس"""
    # اطلاعات اختیاری مرورگر کاربر
    user_agent = request.headers.get("user-agent") if request else None
    
    # تلاش برای دریافت IP کاربر
    ip_address = None
    if request:
        if "x-forwarded-for" in request.headers:
            ip_address = request.headers.get("x-forwarded-for").split(",")[0]
        elif "x-real-ip" in request.headers:
            ip_address = request.headers.get("x-real-ip")
        else:
            ip_address = request.client.host if request.client else None
    
    # ایجاد جلسه جدید
    db_session = Session(
        session_id=str(uuid.uuid4()),
        user_agent=user_agent,
        ip_address=ip_address,
        is_active=True
    )
    
    try:
        db.add(db_session)
        db.commit()
        db.refresh(db_session)
        return db_session
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"خطا در ایجاد جلسه: {str(e)}"
        )

def get_or_create_session_in_db(
    request: Request, 
    session_id: Optional[str] = Cookie(None), 
    db: DBSession = Depends(get_db)
) -> Session:
    """دریافت جلسه موجود یا ایجاد یک جلسه جدید در دیتابیس"""
    if session_id:
        # تلاش برای یافتن جلسه موجود
        db_session = db.query(Session).filter(Session.session_id == session_id).first()
        if db_session and db_session.is_active:
            # بررسی انقضای جلسه
            if db_session.is_expired():
                # جلسه منقضی شده، یک جلسه جدید ایجاد می‌کنیم
                return create_new_session_in_db(request, db)
            
            # به‌روزرسانی زمان آخرین فعالیت
            db_session.last_activity = datetime.now()
            db.commit()
            db.refresh(db_session)
            return db_session
    
    # جلسه‌ای وجود ندارد یا فعال نیست، یک جلسه جدید ایجاد می‌کنیم
    return create_new_session_in_db(request, db)

@router.post("/session", response_model=SessionResponse)
async def create_session(
    request: Request, 
    response: Response, 
    db: DBSession = Depends(get_db)
):
    """ایجاد یک جلسه جدید برای کاربر"""
    # ایجاد جلسه جدید
    db_session = create_new_session_in_db(request, db)
      # تنظیم کوکی
    response.set_cookie(
        key="session_id",
        value=db_session.session_id,
        httponly=True,
        secure=False,  # در محیط توسعه false باشد
        max_age=60 * 60 * 24 * 30,  # 30 روز
        expires=db_session.expires_at.strftime("%a, %d %b %Y %H:%M:%S GMT"),
        samesite="lax",  # حفاظت از حملات CSRF
        domain=None  # domain را None قرار می‌دهیم تا به صورت خودکار از درخواست گرفته شود
    )
    
    return SessionResponse(
        session_id=db_session.session_id,
        message="جلسه جدید با موفقیت ایجاد شد",
        expires_at=db_session.expires_at
    )

@router.get("/session", response_model=SessionData)
async def get_session(
    request: Request, 
    response: Response, 
    session_id: Optional[str] = Cookie(None), 
    db: DBSession = Depends(get_db)
):
    """دریافت یا ایجاد جلسه کاربر"""
    # دریافت یا ایجاد جلسه
    db_session = get_or_create_session_in_db(request, session_id, db)
    
    # اگر جلسه جدید ایجاد شده یا کوکی وجود نداشته باشد، کوکی جدید تنظیم می‌کنیم
    if not session_id or session_id != db_session.session_id:        response.set_cookie(
            key="session_id",
            value=db_session.session_id,
            httponly=True,
            secure=False,  # در محیط توسعه false باشد
            max_age=60 * 60 * 24 * 30,  # 30 روز
            expires=db_session.expires_at.strftime("%a, %d %b %Y %H:%M:%S GMT"),
            samesite="lax",  # حفاظت از حملات CSRF
            domain=None  # domain را None قرار می‌دهیم تا به صورت خودکار از درخواست گرفته شود
        )
    
    return SessionData.from_orm(db_session)

@router.put("/session", response_model=SessionData)
async def update_session(
    session_update: SessionUpdate,
    session_id: Optional[str] = Cookie(None),
    db: DBSession = Depends(get_db)
):
    """به‌روزرسانی داده‌های جلسه"""
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="جلسه‌ای یافت نشد"
        )
    
    # دریافت جلسه از دیتابیس
    db_session = get_session_from_db(session_id, db)
    
    # به‌روزرسانی فیلدهای ارسال شده
    update_data = session_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_session, key, value)
    
    # ذخیره تغییرات
    db.commit()
    db.refresh(db_session)
    
    return SessionData.from_orm(db_session)

@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    response: Response, 
    session_id: Optional[str] = Cookie(None),
    db: DBSession = Depends(get_db)
):
    """حذف جلسه کاربر"""
    if session_id:
        # یافتن جلسه در دیتابیس
        db_session = db.query(Session).filter(Session.session_id == session_id).first()
        if db_session:
            # غیرفعال کردن جلسه (حذف منطقی)
            db_session.is_active = False
            db.commit()
    
    # حذف کوکی
    response.delete_cookie(key="session_id")
    return None

@router.get("/sessions", response_model=List[SessionData])
async def get_all_sessions(
    active_only: bool = True,
    db: DBSession = Depends(get_db)
):
    """دریافت لیست تمام جلسات - فقط برای مقاصد آزمایشی"""
    query = db.query(Session)
    
    # اگر فقط جلسات فعال درخواست شده باشند
    if active_only:
        query = query.filter(Session.is_active == True)
    
    # اعمال محدودیت زمان انقضا
    query = query.filter(Session.expires_at > datetime.now())
    
    # دریافت و بازگرداندن نتایج
    return [SessionData.from_orm(session) for session in query.all()]

@router.get("/session/{session_id}", response_model=SessionData)
async def get_session_by_id(
    session_id: str,
    db: DBSession = Depends(get_db)
):
    """دریافت اطلاعات جلسه با شناسه"""
    db_session = get_session_from_db(session_id, db)
    return SessionData.from_orm(db_session)

@router.delete("/session/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session_by_id(
    session_id: str,
    db: DBSession = Depends(get_db)
):
    """حذف جلسه با شناسه - فقط برای مقاصد مدیریتی"""
    db_session = get_session_from_db(session_id, db)
    
    # غیرفعال کردن جلسه (حذف منطقی)
    db_session.is_active = False
    db.commit()
    
    return None 