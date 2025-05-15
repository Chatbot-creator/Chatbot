from sqlalchemy import cast, String, Float, JSON, Integer, desc, asc, or_, func, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import json
import logging
import os
import httpx
from dotenv import load_dotenv

from App.properties.models import Property
from App.properties.schemas import FilterParams, SortingParams

# تنظیم لاگر
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# بارگذاری متغیرهای محیطی
load_dotenv("config.env")

# کلید و آدرس API
API_KEY = os.getenv("ESTATY_API_KEY", "")
API_URL = "https://panel.estaty.app/api/v1/getProperties"
API_LATEST_CREATED_URL = "https://panel.estaty.app/api/v1/latestCreatedProperties"
API_LATEST_UPDATED_URL = "https://panel.estaty.app/api/v1/latestUpdatedProperties"
API_GET_PROPERTY_URL = "https://panel.estaty.app/api/v1/getProperty"
API_GET_FILTERS_URL = "https://panel.estaty.app/api/v1/getFilters"
API_FILTER_URL = "https://panel.estaty.app/api/v1/filter"

async def fetch_properties(page: int = 1) -> Optional[List[Dict[str, Any]]]:
    headers = {
        "App-key": API_KEY,
        "Content-Type": "application/json"
    }

    try:
        logger.info(f"📦 دریافت صفحه {page} از املاک")
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(API_URL, headers=headers, json={"page": page})

            if response.status_code == 200:
                data = response.json()
                if "properties" in data and "data" in data["properties"]:
                    return data["properties"]["data"]
                elif "data" in data:
                    return data["data"]
    except Exception as e:
        logger.error(f"خطا در دریافت داده‌ها از API: {str(e)}")
    return None

def process_property_data(property_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    پردازش داده‌های خام دریافتی از API و تبدیل به فرمت مناسب برای ذخیره‌سازی.
    
    این تابع داده‌های خام را تبدیل به ساختار متناسب با مدل Property می‌کند و 
    همچنین فیلدهای پیچیده مانند دیکشنری‌ها را به رشته‌های JSON تبدیل می‌کند.
    
    Args:
        property_data (Dict[str, Any]): داده‌های خام دریافتی از API
        
    Returns:
        Dict[str, Any]: داده‌های پردازش شده آماده برای ذخیره در دیتابیس
    """
    # شناسه ملک
    property_id = str(property_data.get("id", ""))
    
    # تبدیل تصاویر به JSON
    images_data = property_data.get("images", [])
    images_json = json.dumps(images_data) if isinstance(images_data, (list, dict)) else json.dumps([])
    
    # تبدیل کل داده‌های خام به JSON
    raw_data_json = json.dumps(property_data) if isinstance(property_data, dict) else json.dumps({})
    
    # استخراج نام شهر
    city_data = property_data.get("city", {})
    city_name = city_data.get("name", "") if isinstance(city_data, dict) else str(city_data) if city_data else ""
    
    # ساخت دیکشنری داده‌های پردازش شده
    processed_data = {
        "property_id": property_id,
        "title": property_data.get("title", ""),
        "description": property_data.get("description", ""),
        "price": float(property_data.get("price", 0)) if property_data.get("price") else 0.0,
        "property_type": property_data.get("type", ""),
        "city": city_name,
        "address": property_data.get("address", ""),
        "latitude": float(property_data.get("lat", 0)) if property_data.get("lat") else None,
        "longitude": float(property_data.get("lng", 0)) if property_data.get("lng") else None,
        "bedrooms": int(property_data.get("bedrooms", 0)) if property_data.get("bedrooms") else None,
        "bathrooms": int(property_data.get("bathrooms", 0)) if property_data.get("bathrooms") else None,
        "area": float(property_data.get("area", 0)) if property_data.get("area") else None,
        "images": images_json,
        "raw_data": raw_data_json,
        "fetched_at": datetime.now()
    }
    
    return processed_data


async def save_properties_to_db(db: Session, fetch_function) -> int:
    from sqlalchemy.exc import IntegrityError
    total_saved = 0
    page = 1

    while True:
        properties_data = await fetch_function(page=page)
        if not properties_data:
            break

        new_items = 0
        updated_items = 0
        batch_size = 100

        for prop_data in properties_data:
            try:
                processed_data = process_property_data(prop_data)
                property_id = processed_data["property_id"]
                existing_property = db.query(Property).filter(Property.property_id == property_id).first()

                if existing_property:
                    for key, value in processed_data.items():
                        if key != "property_id":
                            setattr(existing_property, key, value)
                    updated_items += 1
                else:
                    new_property = Property(**processed_data)
                    db.add(new_property)
                    new_items += 1

                if (new_items + updated_items) % batch_size == 0:
                    db.commit()
            except IntegrityError as e:
                logger.error(f"❌ خطای یکپارچگی ملک {property_id}: {str(e)}")
                db.rollback()
            except Exception as e:
                logger.error(f"❌ خطا در ذخیره ملک: {str(e)}")
                db.rollback()

        db.commit()
        logger.info(f"✅ صفحه {page} ذخیره شد | جدید: {new_items} | آپدیت: {updated_items}")
        total_saved += new_items + updated_items

        if len(properties_data) < 12:
            break

        page += 1

    logger.info(f"🏁 مجموعاً {total_saved} ملک ذخیره شد.")
    return total_saved


async def update_properties_from_api(db: Session) -> Dict[str, Any]:
    from App.properties.service import save_properties_to_db
    start_time = datetime.now()
    logger.info(f"🚀 شروع به‌روزرسانی اطلاعات املاک در {start_time}")

    try:
        items_count = await save_properties_to_db(db, fetch_properties)  # <-- توجه به اینجا
        duration = (datetime.now() - start_time).total_seconds()

        return {
            "success": True,
            "message": f"🎯 عملیات با موفقیت انجام شد. {items_count} آیتم ذخیره شد.",
            "duration_seconds": duration,
            "items_count": items_count,
            "start_time": start_time.isoformat(),
            "end_time": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ خطای غیرمنتظره در به‌روزرسانی داده‌ها: {str(e)}")
        return {
            "success": False,
            "message": f"خطا: {str(e)}",
            "duration_seconds": (datetime.now() - start_time).total_seconds(),
            "items_count": 0
        }

# توابع جدید برای endpoint های جدید

async def fetch_latest_created_properties() -> Optional[List[Dict[str, Any]]]:
    """
    دریافت ۱۰ ملک اخیر ایجاد شده از API خارجی
    
    Returns:
        Optional[List[Dict[str, Any]]]: لیست املاک دریافت شده یا None در صورت بروز خطا
    """
    headers = {
        "App-key": API_KEY,
        "Content-Type": "application/json"
    }
    
    try:
        logger.info("در حال دریافت املاک اخیر ایجاد شده از API")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(API_LATEST_CREATED_URL, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                if "properties" in data and isinstance(data["properties"], list):
                    logger.info(f"املاک اخیر ایجاد شده با موفقیت دریافت شدند. تعداد: {len(data['properties'])}")
                    return data["properties"]
                else:
                    logger.warning("ساختار داده دریافتی برای املاک اخیر ایجاد شده نامعتبر است")
                    return []
            else:
                logger.error(f"خطا در دریافت املاک اخیر ایجاد شده: {response.status_code} - {response.text}")
                return None
    
    except Exception as e:
        logger.error(f"خطا در اتصال به API املاک اخیر ایجاد شده: {str(e)}")
        return None

async def fetch_latest_updated_properties() -> Optional[List[Dict[str, Any]]]:
    """
    دریافت ۱۰ ملک اخیر به‌روزرسانی شده از API خارجی
    
    Returns:
        Optional[List[Dict[str, Any]]]: لیست املاک دریافت شده یا None در صورت بروز خطا
    """
    headers = {
        "App-key": API_KEY,
        "Content-Type": "application/json"
    }
    
    try:
        logger.info("در حال دریافت املاک اخیر به‌روزرسانی شده از API")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(API_LATEST_UPDATED_URL, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                if "properties" in data and isinstance(data["properties"], list):
                    logger.info(f"املاک اخیر به‌روزرسانی شده با موفقیت دریافت شدند. تعداد: {len(data['properties'])}")
                    return data["properties"]
                else:
                    logger.warning("ساختار داده دریافتی برای املاک اخیر به‌روزرسانی شده نامعتبر است")
                    return []
            else:
                logger.error(f"خطا در دریافت املاک اخیر به‌روزرسانی شده: {response.status_code} - {response.text}")
                return None
    
    except Exception as e:
        logger.error(f"خطا در اتصال به API املاک اخیر به‌روزرسانی شده: {str(e)}")
        return None

async def fetch_single_property(property_id: int) -> Optional[Dict[str, Any]]:
    """
    دریافت اطلاعات یک ملک خاص از API خارجی
    
    Args:
        property_id (int): شناسه ملک مورد نظر
        
    Returns:
        Optional[Dict[str, Any]]: اطلاعات ملک یا None در صورت بروز خطا
    """
    headers = {
        "App-key": API_KEY,
        "Content-Type": "application/json"
    }
    
    try:
        logger.info(f"در حال دریافت اطلاعات ملک با شناسه {property_id} از API")
        
        data = {"id": property_id}
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(API_GET_PROPERTY_URL, headers=headers, json=data)
            
            if response.status_code == 200:
                data = response.json()
                if "property" in data and isinstance(data["property"], dict):
                    logger.info(f"اطلاعات ملک با شناسه {property_id} با موفقیت دریافت شد")
                    return data["property"]
                else:
                    logger.warning(f"ساختار داده دریافتی برای ملک با شناسه {property_id} نامعتبر است")
                    return None
            else:
                logger.error(f"خطا در دریافت اطلاعات ملک: {response.status_code} - {response.text}")
                return None
    
    except Exception as e:
        logger.error(f"خطا در اتصال به API دریافت اطلاعات ملک: {str(e)}")
        return None

async def fetch_filters() -> Optional[Dict[str, Any]]:
    """
    دریافت لیست فیلترهای موجود از API خارجی
    
    Returns:
        Optional[Dict[str, Any]]: لیست فیلترهای موجود یا None در صورت بروز خطا
    """
    headers = {
        "App-key": API_KEY,
        "Content-Type": "application/json"
    }
    
    try:
        logger.info("در حال دریافت لیست فیلترها از API")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(API_GET_FILTERS_URL, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                logger.info("لیست فیلترها با موفقیت دریافت شد")
                return data
            else:
                logger.error(f"خطا در دریافت لیست فیلترها: {response.status_code} - {response.text}")
                return None
    
    except Exception as e:
        logger.error(f"خطا در اتصال به API دریافت فیلترها: {str(e)}")
        return None

async def filter_properties(filter_params: FilterParams, sorting_params: SortingParams) -> Optional[Dict[str, Any]]:
    """
    فیلتر کردن املاک با پارامترهای مختلف از API خارجی
    
    Args:
        filter_params (FilterParams): پارامترهای فیلتر
        sorting_params (SortingParams): پارامترهای مرتب‌سازی
        
    Returns:
        Optional[Dict[str, Any]]: لیست املاک فیلتر شده یا None در صورت بروز خطا
    """
    headers = {
        "App-key": API_KEY,
        "Content-Type": "application/json"
    }
    
    try:
        logger.info("در حال فیلتر کردن املاک از API")
        
        # تبدیل پارامترهای فیلتر به دیکشنری
        filter_data = filter_params.dict(exclude_none=True)
        
        # اضافه کردن پارامتر مرتب‌سازی
        if sorting_params.sorting_by:
            filter_data["sorting_by"] = sorting_params.sorting_by
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(API_FILTER_URL, headers=headers, json=filter_data)
            
            if response.status_code == 200:
                data = response.json()
                if "properties" in data:
                    logger.info(f"املاک فیلتر شده با موفقیت دریافت شدند. تعداد: {len(data['properties'])}")
                    return data
                else:
                    logger.warning("ساختار داده دریافتی برای املاک فیلتر شده نامعتبر است")
                    return {"properties": []}
            else:
                logger.error(f"خطا در فیلتر کردن املاک: {response.status_code} - {response.text}")
                return None
    
    except Exception as e:
        logger.error(f"خطا در اتصال به API فیلتر املاک: {str(e)}")
        return None
    
from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, JSON
from App.database import Base
class FilteredProperty(Base):
    __tablename__ = "filtered_properties"

    id = Column(Integer, primary_key=True, autoincrement=True)
    property_id = Column(String, unique=True, nullable=False)
    title = Column(String)
    raw_data = Column(JSON, nullable=False)
    fetched_at = Column(DateTime, default=datetime.utcnow)

    # ستون‌های جدید برای داده‌های اضافی
    property_type = Column(String, nullable=True)
    payment_plan = Column(Integer, nullable=True)
    post_delivery = Column(Integer, nullable=True)
    property_facilities = Column(JSON, nullable=True) 
    delivery_date = Column(String, nullable=True)

async def save_filtered_properties_to_db(db: Session, properties_data: List[Dict[str, Any]]) -> int:
    from sqlalchemy.exc import IntegrityError

    saved = 0
    for prop in properties_data:
        try:
            property_id = str(prop.get("id"))
            existing = db.query(FilteredProperty).filter_by(property_id=property_id).first()

            if existing:
                existing.raw_data = prop
                existing.fetched_at = datetime.utcnow()
            else:
                new_item = FilteredProperty(
                    property_id=property_id,
                    title=prop.get("title", ""),
                    raw_data=prop
                )
                db.add(new_item)
            
            saved += 1
        except IntegrityError as e:
            db.rollback()
            logger.warning(f"خطای یکپارچگی در ذخیره ملک فیلتر شده {property_id}: {str(e)}")
        except Exception as e:
            db.rollback()
            logger.error(f"خطا در ذخیره ملک فیلتر شده: {str(e)}")
    
    db.commit()
    logger.info(f"🎯 {saved} ملک فیلتر شده ذخیره شد.")
    return saved



async def enrich_filtered_properties_from_api(db: Session):
    """
    گرفتن اطلاعات تکمیلی برای تمام property_idها و ذخیره در ستون‌های اختصاصی جدول فیلتر شده.
    """
    updated = 0
    try:
        all_props = db.query(FilteredProperty).all()

        for item in all_props:
            try:
                fresh_data = await fetch_single_property(int(item.property_id))
                if not fresh_data:
                    continue

                # استخراج فیلدهای مورد نظر از پاسخ API
                # بررسی امن برای property_type
                if isinstance(fresh_data.get("property_type"), dict):
                    item.property_type = fresh_data["property_type"].get("name")

                # بررسی امن برای payment_plan و post_delivery
                item.payment_plan = int(fresh_data.get("payment_plan")) if fresh_data.get("payment_plan") is not None else None
                item.post_delivery = int(fresh_data.get("post_delivery")) if fresh_data.get("post_delivery") is not None else None

                # بررسی امن برای property_facilities (باید JSON باشد)
                if isinstance(fresh_data.get("property_facilities"), list):
                    item.property_facilities = fresh_data["property_facilities"]

                # delivery_date همانطور که هست خوب کار می‌کند
                item.delivery_date = fresh_data.get("delivery_date")

                print({
                    "id": item.property_id,
                    "property_type": item.property_type,
                    "payment_plan": item.payment_plan,
                    "post_delivery": item.post_delivery,
                    "delivery_date": item.delivery_date
                })

                db.add(item)
                db.commit()
                updated += 1

            except Exception as e:
                db.rollback()
                logger.warning(f"❌ خطا در به‌روزرسانی ملک {item.property_id}: {str(e)}")

        # db.commit()
        logger.info(f"✅ {updated} ملک با اطلاعات تکمیلی به‌روزرسانی شد.")
    except Exception as e:
        db.rollback()
        logger.error(f"❌ خطای کلی در enrich_filtered_properties_from_api: {str(e)}")




async def update_filtered_properties_from_api(db: Session) -> Dict[str, Any]:
    """
    واکشی همه املاک با فیلتر خالی و ذخیره در جدول جداگانه (FilteredProperty).
    """
    start_time = datetime.now()
    logger.info(f"🚀 شروع دریافت املاک فیلتر شده در {start_time}")

    try:
        filter_params = FilterParams()  # فیلتر خالی
        sorting_params = SortingParams()

        result = await filter_properties(filter_params, sorting_params)

        if not result or "properties" not in result or not result["properties"]:
            logger.warning("⚠️ هیچ داده‌ای برای ذخیره‌سازی فیلترها دریافت نشد.")
            return {
                "success": False,
                "message": "⚠️ هیچ داده‌ای دریافت نشد",
                "duration_seconds": (datetime.now() - start_time).total_seconds(),
                "items_count": 0
            }

        properties_data = result["properties"]
        saved_count = await save_filtered_properties_to_db(db, properties_data)

        await enrich_filtered_properties_from_api(db)

        return {
            "success": True,
            "message": f"✅ ذخیره‌سازی فیلترها انجام شد | مجموع: {saved_count}",
            "duration_seconds": (datetime.now() - start_time).total_seconds(),
            "items_count": saved_count,
            "start_time": start_time.isoformat(),
            "end_time": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ خطا در ذخیره‌سازی فیلترها: {str(e)}")
        return {
            "success": False,
            "message": f"❌ خطا در پردازش فیلترها: {str(e)}",
            "duration_seconds": (datetime.now() - start_time).total_seconds(),
            "items_count": 0
        }

# توابع کار با دیتابیس برای endpoint های جدید

async def get_latest_created_properties_db(db: Session, limit: int = 10) -> List[Property]:
    """
    دریافت لیست املاک اخیر ایجاد شده از دیتابیس
    
    Args:
        db (Session): نشست دیتابیس
        limit (int): تعداد املاک برای نمایش (پیش‌فرض: ۱۰)
        
    Returns:
        List[Property]: لیست املاک اخیر ایجاد شده
    """
    return db.query(Property).order_by(desc(Property.created_at)).limit(limit).all()

async def get_latest_updated_properties_db(db: Session, limit: int = 10) -> List[Property]:
    """
    دریافت لیست املاک اخیر به‌روزرسانی شده از دیتابیس
    
    Args:
        db (Session): نشست دیتابیس
        limit (int): تعداد املاک برای نمایش (پیش‌فرض: ۱۰)
        
    Returns:
        List[Property]: لیست املاک اخیر به‌روزرسانی شده
    """
    return db.query(Property).order_by(desc(Property.updated_at)).limit(limit).all()


async def filter_properties_db(db: Session, filter_params: FilterParams, 
                            sorting_params: SortingParams) -> tuple[list[Property], int]:
    """
    فیلتر کردن املاک در دیتابیس با پارامترهای مختلف
    """
    query = db.query(Property)
    
    # اعمال فیلترها با استفاده از raw_data
    if filter_params.propertyType:
        query = query.filter(
            cast(Property.raw_data, JSON)['property_type_id'].astext.cast(Integer) == filter_params.propertyType
        )
    
    if filter_params.apartmentType:
        query = query.filter(
            cast(Property.raw_data, JSON)['apartment_type_id'].astext.cast(Integer) == filter_params.apartmentType
        )
    
    if filter_params.apartment:
        query = query.filter(
            cast(Property.raw_data, JSON)['apartment_id'].astext.cast(Integer) == filter_params.apartment
        )
    
    if filter_params.district:
        query = query.filter(
            text("raw_data->>'district'->>'name' = :district")
        ).params(district=filter_params.district)
    
    if filter_params.minPrice is not None:
        query = query.filter(
            cast(Property.raw_data, JSON)['low_price'].astext.cast(Float) >= filter_params.minPrice
        )
    
    if filter_params.maxPrice is not None:
        query = query.filter(
            cast(Property.raw_data, JSON)['low_price'].astext.cast(Float) <= filter_params.maxPrice
        )
    
    # اعمال مرتب‌سازی
    sort_field = sorting_params.field or "created_at"
    sort_order = sorting_params.order or "desc"
    
    if sort_order == "desc":
        query = query.order_by(desc(getattr(Property, sort_field)))
    else:
        query = query.order_by(asc(getattr(Property, sort_field)))
    
    # دریافت تعداد کل نتایج
    total_count = query.count()
    
    # اجرای کوئری
    properties = query.all()
    
    return properties, total_count
