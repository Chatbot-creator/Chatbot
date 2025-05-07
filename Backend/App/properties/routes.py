from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import asyncio
import json
from App.database import get_db
from App.properties.models import Property
from App.properties.schemas import PropertyResponse, FilterParams, SortingParams, FilterResponse, PropertyResponseWrapper, SinglePropertyWrapper, SinglePropertyParams
from App.properties.service import (
    update_properties_from_api,
    fetch_latest_created_properties,
    fetch_latest_updated_properties,
    fetch_single_property,
    fetch_filters,
    filter_properties,
    get_latest_created_properties_db,
    get_latest_updated_properties_db,
    filter_properties_db,
    save_properties_to_db,
    process_property_data
)
from App.properties.scheduler import (
    start_scheduler, 
    stop_scheduler, 
    get_scheduler_status, 
    initialize_scheduler
)

router = APIRouter(
    prefix="",
    tags=["properties"],
    responses={404: {"description": "Not Found"}},
)


# روت برای دریافت فیلترهای موجود
@router.get("/filters", response_model=Dict[str, Any])
async def get_filters():
    """
    آوردمش اول چون با get ارور میداد چون قبلش single property بود.
    دریافت لیست فیلترهای موجود برای املاک.
    
    این API لیست تمام فیلترهای موجود برای املاک را برمی‌گرداند.
    
    Returns:
        Dict[str, Any]: لیست فیلترهای موجود
    """
    filters = await fetch_filters()
    
    if not filters:
        raise HTTPException(status_code=500, detail="خطا در دریافت فیلترها")
    
    return filters


def convert_to_original_format(prop: Property) -> dict:
    """
    تبدیل مدل Property به دیکشنری مطابق ساختار اصلی API
    شامل داده‌های خام ذخیره‌شده در raw_data با ترتیب دقیق.
    """
    import json

    raw = prop.raw_data
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}

    return {
        "id": raw.get("id") or int(prop.property_id),
        "city_id": raw.get("city_id"),
        "developer_company_id": raw.get("developer_company_id"),
        "property_type_id": raw.get("property_type_id"),
        "district_id": raw.get("district_id"),
        "title": raw.get("title") or prop.title,
        "cover": raw.get("cover"),
        "address": raw.get("address") or prop.address,
        "address_text": raw.get("address_text"),
        "delivery_date": raw.get("delivery_date"),
        "property_status_id": raw.get("property_status_id"),
        "sales_status_id": raw.get("sales_status_id"),
        "updated_at": raw.get("updated_at") or prop.updated_at.isoformat(),
        "min_area": float(raw.get("min_area") or 0),
        "low_price": float(raw.get("low_price") or 0),
        "developer_company": raw.get("developer_company"),
        "city": raw.get("city"),
        "district": raw.get("district"),
        "property_type": raw.get("property_type"),
        "property_status": raw.get("property_status"),
        "sales_status": raw.get("sales_status"),
        "created_at": prop.created_at.isoformat(),
        "fetched_at": prop.fetched_at.isoformat()
    }

# روت برای دریافت لیست املاک
from math import ceil
@router.get("/", response_model=Dict)
async def get_properties(
    page: int = Query(1, ge=1, description="شماره صفحه جاری"),
    per_page: int = Query(12, ge=1, le=100, description="تعداد آیتم در هر صفحه"),
    db: Session = Depends(get_db)
):
    
    """
    دریافت لیست املاک به‌همراه اطلاعات صفحه‌بندی با فرمت مشابه API اصلی Estaty.

    Args:
        page (int): شماره صفحه جاری (شروع از ۱).
        per_page (int): تعداد آیتم در هر صفحه (بین ۱ تا ۱۰۰).
        db (Session): نشست پایگاه داده (از طریق Depends دریافت می‌شود).

    Returns:
        Dict: شامل اطلاعات کامل املاک صفحه جاری + اطلاعات صفحه‌بندی (current_page, total, next_page_url, links, و غیره).
    """

    total = db.query(Property).count()
    last_page = ceil(total / per_page)
    skip = (page - 1) * per_page

    properties = db.query(Property).offset(skip).limit(per_page).all()
    data = [convert_to_original_format(p) for p in properties]

    # لینک‌های صفحه‌بندی
    base_url = "https://panel.estaty.app/api/v1/getProperties"
    links = []

    # Previous
    links.append({
        "url": f"{base_url}?page={page - 1}" if page > 1 else None,
        "label": "pagination.previous",
        "active": False
    })

    # Numbers + ellipsis logic (simple first 3 + last 2 example)
    for i in range(1, min(last_page + 1, 11)):  # صفحه‌های 1 تا 10
        links.append({
            "url": f"{base_url}?page={i}",
            "label": str(i),
            "active": (i == page)
        })

    if last_page > 11:
        links.append({"url": None, "label": "...", "active": False})
        links.append({
            "url": f"{base_url}?page={last_page - 1}",
            "label": str(last_page - 1),
            "active": False
        })
        links.append({
            "url": f"{base_url}?page={last_page}",
            "label": str(last_page),
            "active": False
        })

    # Next
    links.append({
        "url": f"{base_url}?page={page + 1}" if page < last_page else None,
        "label": "pagination.next",
        "active": False
    })

    from_item = skip + 1 if total > 0 else 0
    to_item = min(skip + per_page, total)

    return {
        "properties": {

            "current_page": page,
            "data": data,
            "first_page_url": f"{base_url}?page=1",
            "from": from_item,
            "last_page": last_page,
            "last_page_url": f"{base_url}?page={last_page}",
            "links": links,
            "next_page_url": f"{base_url}?page={page + 1}" if page < last_page else None,
            "path": base_url,
            "per_page": per_page,
            "prev_page_url": f"{base_url}?page={page - 1}" if page > 1 else None,
            "to": to_item,
            "total": total
        }
    }


def convert_to_original_format_single(prop: Property) -> dict:
    """
    تبدیل مدل Property به دیکشنری مطابق ساختار اصلی API single property
    شامل تمام فیلدهای لازم با ترتیب دقیق.
    """
    import json

    raw = prop.raw_data
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}

    return {
        "id": raw.get("id") or int(prop.property_id),
        "city_id": raw.get("city_id"),
        "developer_company_id": raw.get("developer_company_id"),
        "property_type_id": raw.get("property_type_id"),
        "district_id": raw.get("district_id"),
        "title": raw.get("title") or prop.title,
        "description": raw.get("description"),
        "cover": raw.get("cover"),
        "address": raw.get("address") or prop.address,
        "address_text": raw.get("address_text"),
        "delivery_date": raw.get("delivery_date"),
        "property_status_id": raw.get("property_status_id"),
        "sales_status_id": raw.get("sales_status_id"),
        "completion_rate": raw.get("completion_rate"),
        "residential_units": raw.get("residential_units"),
        "commercial_units": raw.get("commercial_units"),
        "payment_plan": raw.get("payment_plan"),
        "post_delivery": raw.get("post_delivery"),
        "payment_minimum_down_payment": raw.get("payment_minimum_down_payment"),
        "guarantee_rental_guarantee": raw.get("guarantee_rental_guarantee"),
        "guarantee_rental_guarantee_value": raw.get("guarantee_rental_guarantee_value"),
        "updated_at": raw.get("updated_at") or prop.updated_at.isoformat(),
        "downPayment": raw.get("downPayment"),
        "grouped_apartments": raw.get("grouped_apartments") or [],
        "low_price": float(raw.get("low_price") or 0),
        "min_area": float(raw.get("min_area") or 0),
        "developer_company": raw.get("developer_company"),
        "city": raw.get("city"),
        "district": raw.get("district"),
        "property_images": raw.get("property_images") or [],
        "property_type": raw.get("property_type"),
        "property_facilities": raw.get("property_facilities") or [],
        "property_status": raw.get("property_status"),
        "sales_status": raw.get("sales_status"),
        "payment_plans": raw.get("payment_plans") or [],
        "created_at": prop.created_at.isoformat(),
        "fetched_at": prop.fetched_at.isoformat()
    }

# # روت برای دریافت جزئیات یک ملک با شناسه
# @router.get("/{property_id}", response_model=PropertyResponse)
# async def get_property(property_id: str, db: Session = Depends(get_db)):
#     """
#     دریافت جزئیات یک ملک با شناسه.
    
#     این API جزئیات یک ملک را بر اساس شناسه آن برمی‌گرداند.
    
#     Args:
#         property_id (str): شناسه منحصر به فرد ملک
#         db (Session): نشست دیتابیس
        
#     Returns:
#         PropertyResponse: جزئیات ملک
        
#     Raises:
#         HTTPException: اگر ملک مورد نظر یافت نشود، خطای 404 برگردانده می‌شود
#     """
#     property_item = db.query(Property).filter(Property.property_id == property_id).first()
#     if not property_item:
#         raise HTTPException(status_code=404, detail="ملک مورد نظر یافت نشد")
    
#     return convert_to_original_format(property_item)

# @router.get("/{property_id}")


@router.get("/{property_id}", response_model=SinglePropertyWrapper)
async def get_property(property_id: str, db: Session = Depends(get_db)):
    """
    دریافت جزئیات یک ملک با شناسه مشخص.

    ابتدا ملک را از دیتابیس جستجو می‌کند. اگر موجود نباشد، خطای 404 باز می‌گرداند.
    سپس داده‌ی خام (raw_data) را به ساختار استاندارد تبدیل می‌کند.
    اگر برخی از فیلدهای کلیدی مقدار نداشته باشند، اطلاعات کامل ملک از API اصلی مجدداً واکشی شده،
    در دیتابیس ذخیره می‌شود و نتیجه نهایی به کاربر بازگردانده می‌شود.
    """

    prop = db.query(Property).filter(Property.property_id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="ملک مورد نظر یافت نشد")
    # تلاش برای تبدیل raw_data فعلی
    result = convert_to_original_format_single(prop)

    # بررسی اینکه آیا برخی فیلدهای مهم مقدار ندارند
    critical_keys = [
        "description", "payment_plan", "grouped_apartments", 
        "payment_plans", "property_images", "property_facilities"
    ]
    missing_data = any(result.get(key) in (None, [], "") for key in critical_keys)

    # اگر داده ناقص بود، مجدداً از API اصلی دریافت و جایگزین کن
    if missing_data:
        fresh_data = await fetch_single_property(int(property_id))
        if fresh_data:
            prop.raw_data = json.dumps(fresh_data)
            db.commit()  # بروزرسانی در دیتابیس
            result = convert_to_original_format_single(prop)  # مجدداً تبدیل با داده کامل

    return {"property": result}

# روت‌های جدید بر اساس داکیومنت API

# روت برای دریافت ۱۰ ملک اخیر ایجاد شده
@router.post("/latest-created", response_model=Dict[str, Any])
async def get_latest_created_properties(db: Session = Depends(get_db)):
    """
    دریافت ۱۰ ملک اخیراً ایجاد شده.
    
    این API لیست ۱۰ ملک اخیر ایجاد شده را برمی‌گرداند.
    
    Args:
        db (Session): نشست دیتابیس
        
    Returns:
        Dict[str, Any]: لیست ملک‌های اخیر ایجاد شده
    """
    # ابتدا سعی می‌کنیم از دیتابیس محلی استفاده کنیم
    local_properties = await get_latest_created_properties_db(db)
    
    # اگر در دیتابیس داده‌ای نبود یا تعداد کافی نبود، از API می‌گیریم
    if not local_properties or len(local_properties) < 10:
        api_properties = await fetch_latest_created_properties()
        
        if api_properties:
            # ذخیره در دیتابیس
            await save_properties_to_db(db, api_properties)
            
            # بازیابی مجدد از دیتابیس بعد از ذخیره‌سازی
            local_properties = await get_latest_created_properties_db(db)
    
    # Convert SQLAlchemy model objects to dictionaries for serialization
    serializable_properties = []
    for prop in local_properties:
        prop_dict = {
            "property_id": prop.property_id,
            "title": prop.title,
            "description": prop.description,
            "price": prop.price,
            "property_type": prop.property_type,
            "city": prop.city,
            "address": prop.address,
            "latitude": prop.latitude,
            "longitude": prop.longitude,
            "bedrooms": prop.bedrooms,
            "bathrooms": prop.bathrooms,
            "area": prop.area,
            "images": prop.images,
            "created_at": prop.created_at.isoformat() if prop.created_at else None,
            "updated_at": prop.updated_at.isoformat() if prop.updated_at else None,
            "fetched_at": prop.fetched_at.isoformat() if prop.fetched_at else None,
        }
        serializable_properties.append(prop_dict)
    
    return {
        "properties": serializable_properties,
        "total": len(serializable_properties)
    }

# روت برای دریافت ۱۰ ملک اخیر به‌روزرسانی شده
@router.post("/latest-updated", response_model=Dict[str, Any])
async def get_latest_updated_properties(db: Session = Depends(get_db)):
    """
    دریافت ۱۰ ملک اخیراً به‌روزرسانی شده.
    
    این API لیست ۱۰ ملک اخیر به‌روزرسانی شده را برمی‌گرداند.
    
    Args:
        db (Session): نشست دیتابیس
        
    Returns:
        Dict[str, Any]: لیست ملک‌های اخیر به‌روزرسانی شده
    """
    # ابتدا سعی می‌کنیم از دیتابیس محلی استفاده کنیم
    local_properties = await get_latest_updated_properties_db(db)
    
    # اگر در دیتابیس داده‌ای نبود یا تعداد کافی نبود، از API می‌گیریم
    if not local_properties or len(local_properties) < 10:
        api_properties = await fetch_latest_updated_properties()
        
        if api_properties:
            # ذخیره در دیتابیس
            await save_properties_to_db(db, api_properties)
            
            # بازیابی مجدد از دیتابیس بعد از ذخیره‌سازی
            local_properties = await get_latest_updated_properties_db(db)
    
    # Convert SQLAlchemy model objects to dictionaries for serialization
    serializable_properties = []
    for prop in local_properties:
        prop_dict = {
            "property_id": prop.property_id,
            "title": prop.title,
            "description": prop.description,
            "price": prop.price,
            "property_type": prop.property_type,
            "city": prop.city,
            "address": prop.address,
            "latitude": prop.latitude,
            "longitude": prop.longitude,
            "bedrooms": prop.bedrooms,
            "bathrooms": prop.bathrooms,
            "area": prop.area,
            "images": prop.images,
            "created_at": prop.created_at.isoformat() if prop.created_at else None,
            "updated_at": prop.updated_at.isoformat() if prop.updated_at else None,
            "fetched_at": prop.fetched_at.isoformat() if prop.fetched_at else None,
        }
        serializable_properties.append(prop_dict)
    
    return {
        "properties": serializable_properties,
        "total": len(serializable_properties)
    }

# روت برای دریافت یک ملک خاص با شناسه
# @router.post("/get-property", response_model=Dict[str, Any])
# async def get_single_property(property_id: int, db: Session = Depends(get_db)):
#     """
#     دریافت اطلاعات کامل یک ملک با شناسه.
    
#     این API جزئیات کامل یک ملک را بر اساس شناسه آن برمی‌گرداند.
    
#     Args:
#         property_id (int): شناسه منحصر به فرد ملک
#         db (Session): نشست دیتابیس
        
#     Returns:
#         Dict[str, Any]: جزئیات کامل ملک
#     """
#     # ابتدا سعی می‌کنیم از دیتابیس محلی بگیریم
#     property_item = db.query(Property).filter(Property.property_id == str(property_id)).first()
    
#     # اگر در دیتابیس نبود، از API می‌گیریم
#     if not property_item:
#         api_property = await fetch_single_property(property_id)
        
#         if api_property:
#             # پردازش و ذخیره در دیتابیس
#             processed_data = process_property_data(api_property)
#             new_property = Property(**processed_data)
#             db.add(new_property)
#             db.commit()
#             db.refresh(new_property)
            
#             # Convert to dictionary for serialization
#             prop_dict = {
#                 "property_id": new_property.property_id,
#                 "title": new_property.title,
#                 "description": new_property.description,
#                 "price": new_property.price,
#                 "property_type": new_property.property_type,
#                 "city": new_property.city,
#                 "address": new_property.address,
#                 "latitude": new_property.latitude,
#                 "longitude": new_property.longitude,
#                 "bedrooms": new_property.bedrooms,
#                 "bathrooms": new_property.bathrooms,
#                 "area": new_property.area,
#                 "images": new_property.images,
#                 "created_at": new_property.created_at.isoformat() if new_property.created_at else None,
#                 "updated_at": new_property.updated_at.isoformat() if new_property.updated_at else None,
#                 "fetched_at": new_property.fetched_at.isoformat() if new_property.fetched_at else None,
#             }
            
#             return {"property": prop_dict}
#         else:
#             raise HTTPException(status_code=404, detail="ملک مورد نظر یافت نشد")
    
#     # Convert to dictionary for serialization
#     prop_dict = {
#         "property_id": property_item.property_id,
#         "title": property_item.title,
#         "description": property_item.description,
#         "price": property_item.price,
#         "property_type": property_item.property_type,
#         "city": property_item.city,
#         "address": property_item.address,
#         "latitude": property_item.latitude,
#         "longitude": property_item.longitude,
#         "bedrooms": property_item.bedrooms,
#         "bathrooms": property_item.bathrooms,
#         "area": property_item.area,
#         "images": property_item.images,
#         "created_at": property_item.created_at.isoformat() if property_item.created_at else None,
#         "updated_at": property_item.updated_at.isoformat() if property_item.updated_at else None,
#         "fetched_at": property_item.fetched_at.isoformat() if property_item.fetched_at else None,
#     }
    
#     return {"property": prop_dict}


@router.post("/get-property", response_model=SinglePropertyWrapper)
async def get_single_property(data: SinglePropertyParams, db: Session = Depends(get_db)):
    """
    دریافت اطلاعات کامل یک ملک با شناسه.

    اگر ملک در دیتابیس لوکال نبود، از API می‌گیرد و ذخیره می‌کند.
    سپس خروجی با ساختار دقیق مشابه API اصلی بازمی‌گردد.
    """
    property_id = data.id
    property_item = db.query(Property).filter(Property.property_id == str(property_id)).first()

    if not property_item:
        api_property = await fetch_single_property(property_id)
        if not api_property:
            raise HTTPException(status_code=404, detail="ملک مورد نظر یافت نشد")
        
        processed_data = process_property_data(api_property)
        new_property = Property(**processed_data)
        db.add(new_property)
        db.commit()
        db.refresh(new_property)
        property_item = new_property

    # اگر داده‌های مهم ناقص بودن، یک بار دیگه fetch کنیم
    result = convert_to_original_format_single(property_item)
    critical_keys = [
        "description", "payment_plan", "grouped_apartments", 
        "payment_plans", "property_images", "property_facilities"
    ]
    if any(result.get(key) in (None, [], "") for key in critical_keys):
        fresh_data = await fetch_single_property(property_id)
        if fresh_data:
            property_item.raw_data = json.dumps(fresh_data)
            db.commit()
            result = convert_to_original_format_single(property_item)

    return {"property": result}


def recursive_json_decode(data):
    while isinstance(data, str):
        try:
            decoded = json.loads(data)
            if isinstance(decoded, (dict, list)):
                data = decoded
            else:
                break
        except (json.JSONDecodeError, TypeError):
            break

    if isinstance(data, dict):
        return {k: recursive_json_decode(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [recursive_json_decode(v) for v in data]
    return data

# @router.post("/filter")
# async def filter_properties_route(
#     filter_params: FilterParams,
#     sorting_params: SortingParams = SortingParams(),
#     skip: int = Query(0, description="تعداد آیتم‌های رد شده برای صفحه‌بندی"),
#     limit: int = Query(10000, description="حداکثر تعداد آیتم‌های بازگشتی"),
#     db: Session = Depends(get_db)
# ):
#     """
#     فیلتر کردن املاک با پارامترهای مختلف و بازگرداندن داده‌های استخراج‌شده از raw_data.
#     """
#     result = await filter_properties_db(db, filter_params, sorting_params, skip, limit)

#     def convert_raw(prop):
#         raw = prop.raw_data
#         if isinstance(raw, str):
#             try:
#                 raw = json.loads(raw)
#             except json.JSONDecodeError:
#                 raw = {}

#         # raw = recursive_json_decode(raw)

#         # تزریق فیلدهایی که ممکنه در raw نباشن
#         raw["id"] = raw.get("id") or int(prop.property_id)
#         raw["title"] = raw.get("title") or prop.title
#         raw["updated_at"] = raw.get("updated_at") or (prop.updated_at.isoformat() if prop.updated_at else None)
#         raw["created_at"] = raw.get("created_at") or (prop.created_at.isoformat() if prop.created_at else None)
#         raw["fetched_at"] = prop.fetched_at.isoformat() if prop.fetched_at else None

#         return raw

#     return {
#         "properties": [convert_raw(p) for p in result["properties"]],
#         "total": result["total"]
#     }

# روت برای فیلتر کردن املاک
# @router.post("/filter", response_model=Dict[str, Any])
@router.post("/filter")
async def filter_properties_route(
    filter_params: FilterParams,
    sorting_params: SortingParams = SortingParams(),
    skip: int = Query(0, description="تعداد آیتم‌های رد شده برای صفحه‌بندی"),
    limit: int = Query(10000, description="حداکثر تعداد آیتم‌های بازگشتی"),
    db: Session = Depends(get_db)
):
    """
    فیلتر کردن املاک با پارامترهای مختلف و بازگرداندن داده‌های استخراج‌شده از raw_data.
    """
    result = await filter_properties_db(db, filter_params, sorting_params, skip, limit)


    def convert_raw(prop):
        raw = prop.raw_data
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = {}

        # raw = recursive_json_decode(raw)

        
        return {
            "id": raw.get("id") or int(prop.property_id),
            "title": raw.get("title") or prop.title,
            "description": raw.get("description"),
            "cover": raw.get("cover"),
            # "address": raw.get("address") or prop.address,
            "address_text": raw.get("address_text"),
            "delivery_date": raw.get("delivery_date"),
            "updated_at": raw.get("updated_at") or (prop.updated_at.isoformat() if prop.updated_at else None),
            # "created_at": prop.created_at.isoformat() if prop.created_at else None,
            "fetched_at": prop.fetched_at.isoformat() if prop.fetched_at else None,
            "is_deleted": raw.get("is_deleted"),
            "isDraft": raw.get("isDraft"),
            "requested_delete": raw.get("requested_delete"),
            "requested_create": raw.get("requested_create"),
            "is_fav": raw.get("is_fav"),
            "low_price": float(raw.get("low_price") or 0),
            "min_area": float(raw.get("min_area") or 0),

            # آیدی‌ها
            "city_id": raw.get("city_id"),
            "district_id": raw.get("district_id"),
            "developer_company_id": raw.get("developer_company_id"),
            "property_type_id": raw.get("property_type_id"),
            "sales_status_id": raw.get("sales_status_id"),
            "property_status_id": raw.get("property_status_id"),

            # آبجکت‌ها و آرایه‌ها
            "developer_company": raw.get("developer_company", {}),
            "city": raw.get("city", {}),
            "district": raw.get("district", {}),
            "neighborhood": raw.get("neighborhood", {}),
            "property_type": raw.get("property_type", {}),
            "property_status": raw.get("property_status", {}),
            "sales_status": raw.get("sales_status", {}),
            "property_images": raw.get("property_images", []),
            "property_facilities": raw.get("property_facilities", []),
            "payment_plans": raw.get("payment_plans", []),
            "grouped_apartments": raw.get("grouped_apartments", []),
            "translations": raw.get("translations", []),
            "apartment": raw.get("apartment", []),

            # سایر
            "completion_rate": raw.get("completion_rate"),
            "residential_units": raw.get("residential_units"),
            "commercial_units": raw.get("commercial_units"),
            "payment_plan": raw.get("payment_plan"),
            "post_delivery": raw.get("post_delivery"),
            "payment_minimum_down_payment": raw.get("payment_minimum_down_payment"),
            "guarantee_rental_guarantee": raw.get("guarantee_rental_guarantee"),
            "guarantee_rental_guarantee_value": raw.get("guarantee_rental_guarantee_value"),
            "downPayment": raw.get("downPayment")
        }


    return {
        "properties": [convert_raw(p) for p in result["properties"]],
        "total": result["total"]
    }

# @router.post("/filter", response_model=Dict[str, Any])
# async def filter_properties_route(
#     filter_params: FilterParams,
#     sorting_params: SortingParams = SortingParams(),
#     skip: int = Query(0, description="تعداد آیتم‌های رد شده برای صفحه‌بندی"),
#     limit: int = Query(100, description="حداکثر تعداد آیتم‌های بازگشتی"),
#     db: Session = Depends(get_db)
# ):
#     """
#     فیلتر کردن املاک با پارامترهای مختلف.
    
#     این API امکان فیلتر کردن املاک با پارامترهای مختلف را فراهم می‌کند.
    
#     Args:
#         filter_params (FilterParams): پارامترهای فیلتر
#         sorting_params (SortingParams): پارامترهای مرتب‌سازی
#         skip (int): تعداد آیتم‌ها برای پرش در صفحه‌بندی
#         limit (int): حداکثر تعداد آیتم‌های برگشتی
#         db (Session): نشست دیتابیس
        
#     Returns:
#         Dict[str, Any]: لیست املاک فیلتر شده و تعداد کل
#     """
#     # ابتدا سعی می‌کنیم از دیتابیس محلی بگیریم
#     result = await filter_properties_db(db, filter_params, sorting_params, skip, limit)
    
#     # اگر نتیجه‌ای نداشتیم یا تعداد کافی نبود، از API می‌گیریم
#     if not result["properties"] or len(result["properties"]) == 0:
#         api_result = await filter_properties(filter_params, sorting_params)
        
#         if api_result and "properties" in api_result and api_result["properties"]:
#             # ذخیره در دیتابیس
#             await save_properties_to_db(db, api_result["properties"])
            
#             # بازیابی مجدد از دیتابیس
#             result = await filter_properties_db(db, filter_params, sorting_params, skip, limit)
#     def serialize_model(obj):
#         data = obj.__dict__.copy()
#         data.pop("_sa_instance_state", None)
#         return data

#     return {
#         "properties": [serialize_model(p) for p in result["properties"]],
#         "total": result["total"]
#     }    
    # return {
    #     "properties": result["properties"],
    #     "total": result["total"]
    # }

# روت برای به‌روزرسانی دستی داده‌ها از API
@router.post("/update", response_model=Dict[str, Any])
async def manual_update(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    به‌روزرسانی دستی داده‌های املاک از API.
    
    این API یک به‌روزرسانی دستی را در پس‌زمینه شروع می‌کند و فوراً پاسخ می‌دهد.
    
    Args:
        background_tasks (BackgroundTasks): ابزار اجرای وظایف در پس‌زمینه FastAPI
        db (Session): نشست دیتابیس
        
    Returns:
        Dict[str, Any]: وضعیت درخواست به‌روزرسانی
    """
    # به‌روزرسانی در پس‌زمینه انجام می‌شود تا پاسخ API معطل نماند
    background_tasks.add_task(update_properties_in_background, db)
    
    return {
        "message": "درخواست به‌روزرسانی با موفقیت ثبت شد. این عملیات در پس‌زمینه انجام خواهد شد.",
        "status": "processing"
    }

# روت‌های مدیریت زمانبندی
@router.get("/scheduler/status", response_model=Dict[str, Any])
async def scheduler_status():
    """
    دریافت وضعیت فعلی زمانبندی.
    
    این API اطلاعات وضعیت فعلی زمانبند را برمی‌گرداند.
    
    Returns:
        Dict[str, Any]: وضعیت فعلی زمانبند شامل وضعیت اجرا، زمان‌های اجرا و تاریخچه
    """
    return get_scheduler_status()

@router.post("/scheduler/start", response_model=Dict[str, Any])
async def start_scheduler_route():
    """
    شروع زمانبندی به‌روزرسانی خودکار.
    
    این API زمانبند به‌روزرسانی خودکار را شروع می‌کند.
    
    Returns:
        Dict[str, Any]: نتیجه درخواست شروع زمانبند
    """
    result = start_scheduler()
    return {
        "success": result,
        "message": "زمانبندی با موفقیت شروع شد" if result else "زمانبندی قبلاً در حال اجراست"
    }

@router.post("/scheduler/stop", response_model=Dict[str, Any])
async def stop_scheduler_route():
    """
    توقف زمانبندی به‌روزرسانی خودکار.
    
    این API زمانبند به‌روزرسانی خودکار را متوقف می‌کند.
    
    Returns:
        Dict[str, Any]: نتیجه درخواست توقف زمانبند
    """
    result = stop_scheduler()
    return {
        "success": result,
        "message": "زمانبندی با موفقیت متوقف شد" if result else "زمانبندی در حال حاضر متوقف است"
    }

# روت برای اجرای فوری به‌روزرسانی بدون انتظار برای نتیجه
@router.post("/force-update", response_model=Dict[str, Any])
async def force_update(db: Session = Depends(get_db)):
    """
    اجرای فوری به‌روزرسانی و انتظار برای تکمیل.
    
    این API یک به‌روزرسانی فوری را اجرا می‌کند و تا زمان تکمیل آن منتظر می‌ماند.
    نتیجه کامل عملیات را برمی‌گرداند.
    
    Args:
        db (Session): نشست دیتابیس
        
    Returns:
        Dict[str, Any]: نتیجه کامل عملیات به‌روزرسانی
    """
    result = await update_properties_from_api(db)
    return result

# تابع کمکی برای اجرای به‌روزرسانی در پس‌زمینه
async def update_properties_in_background(db: Session):
    """
    اجرای به‌روزرسانی در پس‌زمینه.
    
    این تابع داخلی برای اجرای به‌روزرسانی در پس‌زمینه استفاده می‌شود.
    
    Args:
        db (Session): نشست دیتابیس
    """
    await update_properties_from_api(db) 