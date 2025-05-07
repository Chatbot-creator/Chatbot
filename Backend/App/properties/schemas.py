from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from pydantic import BaseModel, Field

# class PropertyBase(BaseModel):
#     """مدل پایه برای داده‌های ملک"""
#     property_id: Optional[str] = None
#     title: Optional[str] = None
#     description: Optional[str] = None
#     price: Optional[float] = None
#     property_type: Optional[str] = None
#     city: Optional[str] = None
#     address: Optional[str] = None
#     latitude: Optional[float] = None
#     longitude: Optional[float] = None
#     bedrooms: Optional[int] = None
#     bathrooms: Optional[int] = None
#     area: Optional[float] = None
#     images: Optional[str] = None  # تغییر به رشته JSON
#     raw_data: Optional[str] = None  # تغییر به رشته JSON


# class PropertyCreate(PropertyBase):
#     """مدل برای ایجاد یک ملک جدید"""
#     pass

# class PropertyResponse(PropertyBase):
#     """مدل پاسخ برای نمایش اطلاعات ملک"""
#     id: int
#     created_at: datetime
#     updated_at: datetime
#     fetched_at: datetime

#     class Config:
#         from_attributes = True


class NamedObject(BaseModel):
    """
    مدل عمومی برای نمایش اشیاء دارای شناسه و نام مانند شهر، نوع ملک و غیره.

    Attributes:
        id (int): شناسه عددی شیء.
        name (str): نام شیء.
    """
    id: int
    name: str



class PropertyResponse(BaseModel):
    """
    مدل پاسخ‌دهی برای نمایش کامل اطلاعات ملک، مشابه ساختار خروجی API اصلی.
    """

    id: int
    city_id: Optional[int] = None
    developer_company_id: Optional[int] = None
    property_type_id: Optional[int] = None
    district_id: Optional[int] = None
    title: str
    cover: Optional[str] = None
    address: Optional[str] = None
    address_text: Optional[str] = None
    delivery_date: Optional[str] = None
    property_status_id: Optional[int] = None
    sales_status_id: Optional[int] = None
    updated_at: Optional[datetime] = None
    min_area: Optional[float] = None
    low_price: Optional[float] = None

    developer_company: Optional[NamedObject] = None
    city: Optional[NamedObject] = None
    district: Optional[NamedObject] = None
    property_type: Optional[NamedObject] = None
    property_status: Optional[NamedObject] = None
    sales_status: Optional[NamedObject] = None

    created_at: Optional[datetime] = None
    fetched_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# class PropertyResponse(BaseModel):
#     """
#     مدل پاسخ‌دهی برای نمایش کامل اطلاعات ملک، مشابه ساختار خروجی API اصلی.

#     Attributes:
#         id (int): شناسه داخلی ملک در دیتابیس.
#         city_id (int): شناسه شهر.
#         developer_company_id (int): شناسه شرکت سازنده.
#         property_type_id (int): شناسه نوع ملک.
#         district_id (int): شناسه منطقه.
#         title (str): عنوان ملک.
#         cover (str): URL تصویر کاور.
#         address (str): مختصات مکان ملک (Latitude,Longitude).
#         address_text (str): لینک موقعیت ملک در Google Maps.
#         delivery_date (str): تاریخ تحویل ملک به صورت timestamp یونیکس.
#         property_status_id (int): شناسه وضعیت ساخت ملک (مثلاً آماده، در حال ساخت).
#         sales_status_id (int): شناسه وضعیت فروش (مثلاً موجود، فروخته شده).
#         updated_at (datetime): زمان آخرین بروزرسانی.
#         min_area (float, optional): حداقل مساحت ملک.
#         low_price (float, optional): قیمت پایه ملک.
#         developer_company (NamedObject): اطلاعات شرکت سازنده.
#         city (NamedObject): اطلاعات شهر.
#         district (NamedObject): اطلاعات منطقه.
#         property_type (NamedObject): نوع ملک.
#         property_status (NamedObject): وضعیت ساخت.
#         sales_status (NamedObject): وضعیت فروش.
#         created_at (datetime): زمان ایجاد رکورد در سیستم.
#         fetched_at (datetime): زمان دریافت اطلاعات از API خارجی.
#     """
    
#     id: int
#     city_id: int
#     developer_company_id: int
#     property_type_id: int
#     district_id: int
#     title: str
#     cover: str
#     address: str
#     address_text: str
#     delivery_date: str
#     property_status_id: int
#     sales_status_id: int
#     updated_at: datetime
#     min_area: Optional[float] = None
#     low_price: Optional[float] = None

#     developer_company: NamedObject
#     city: NamedObject
#     district: NamedObject
#     property_type: NamedObject
#     property_status: NamedObject
#     sales_status: NamedObject

#     created_at: datetime
#     fetched_at: datetime

#     class Config:
#         from_attributes = True


class PropertyResponse_single(BaseModel):
    id: int
    city_id: int
    developer_company_id: int
    property_type_id: int
    district_id: int
    title: str
    description: Optional[str] = None
    cover: str
    address: str
    address_text: str
    delivery_date: str
    property_status_id: int
    sales_status_id: int
    completion_rate: Optional[float] = None
    residential_units: Optional[int] = None
    commercial_units: Optional[int] = None
    payment_plan: Optional[int] = None
    post_delivery: Optional[int] = None
    payment_minimum_down_payment: Optional[float] = None
    guarantee_rental_guarantee: Optional[int] = None
    guarantee_rental_guarantee_value: Optional[float] = None
    updated_at: datetime
    downPayment: Optional[float] = None
    grouped_apartments: Optional[List[dict]] = []
    low_price: Optional[float] = None
    min_area: Optional[float] = None

    developer_company: NamedObject
    city: NamedObject
    district: NamedObject
    property_type: NamedObject
    property_status: NamedObject
    sales_status: NamedObject

    property_images: Optional[List[dict]] = []
    property_facilities: Optional[List[dict]] = []
    payment_plans: Optional[List[dict]] = []

    created_at: datetime
    fetched_at: datetime

    class Config:
        from_attributes = True

class SinglePropertyWrapper(BaseModel):
    property: PropertyResponse_single

# class PropertyList(BaseModel):
#     """لیست املاک"""
#     items: List[PropertyResponse]
#     total: int

class PropertyPage(BaseModel):
    """
    مدل داده‌ای برای نمایش صفحه‌بندی‌شده از املاک.

    فیلدها:
        current_page (int): شماره صفحه جاری.
        data (List[PropertyResponse]): لیستی از املاک موجود در این صفحه.
        total (int): تعداد کل ملک‌های موجود در تمام صفحات.
    """
    current_page: int
    data: List[PropertyResponse]
    total: int

class PropertyResponseWrapper(BaseModel):
    """
    مدل داده‌ای برای پاسخ API که شامل اطلاعات صفحه‌بندی‌شده‌ی املاک است.

    فیلدها:
        properties (PropertyPage): اطلاعات کامل یک صفحه از املاک شامل لیست املاک،
        شماره صفحه و تعداد کل.
    """
    properties: PropertyPage

# مدل‌های جدید برای endpoint های جدید

class FilterParams(BaseModel):
    """پارامترهای فیلتر برای API داده‌های املاک"""
    search_type: Optional[int] = None
    sorting_by: Optional[int] = None
    property_name: Optional[str] = None
    developer_company_id: Optional[List[str]] = None
    marketing_agency_id: Optional[List[str]] = None
    city_id: Optional[List[str]] = None
    district_id: Optional[List[str]] = None
    status: Optional[List[str]] = None
    sales_status: Optional[List[str]] = None
    property_type: Optional[List[str]] = None
    apartmentType: Optional[List[str]] = None
    apartments: Optional[List[str]] = None
    facilities: Optional[List[str]] = None
    guarantee_rental_guarantee: Optional[List[str]] = None
    payment_plan: Optional[List[str]] = None
    post_delivery: Optional[List[str]] = None
    delivery_date: Optional[str] = None
    max_down_payment: Optional[List[str]] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_area: Optional[float] = None
    max_area: Optional[float] = None
    currency: Optional[str] = Field(None, description="کد ارز (مثلا USD, AED)")
    area_unit: Optional[str] = Field(None, description="واحد مساحت (مثلا متر مربع، فوت مربع)")

class SortingParams(BaseModel):
    """پارامترهای مرتب‌سازی برای API داده‌های املاک"""
    sorting_by: Optional[str] = Field("created_at_desc", 
        description="نحوه مرتب‌سازی (price_asc, price_desc, area_asc, area_desc, name_asc, name_desc, created_at_asc, created_at_desc)")

class SinglePropertyParams(BaseModel):
    """پارامترهای دریافت یک ملک"""
    id: int

class FilterResponse(BaseModel):
    """پاسخ API فیلترها"""
    cities: List[Dict[str, Any]]
    views: List[Dict[str, Any]]
    property_types: List[Dict[str, Any]]
    districts: List[Dict[str, Any]]
    developers: List[Dict[str, Any]]
    sales_statuses: List[Dict[str, Any]]
    property_statuses: List[Dict[str, Any]] 