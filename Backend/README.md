# Backend FastAPI Project - املاک API

یک سرویس API برای مدیریت و نمایش اطلاعات املاک با قابلیت دریافت خودکار از API خارجی

## مشخصات پروژه

- **فریم‌ورک**: FastAPI
- **پایگاه داده**: PostgreSQL
- **زبان برنامه‌نویسی**: Python 3.9+
- **مدیریت وابستگی‌ها**: pip / requirements.txt
- **تست**: pytest

## ویژگی‌ها

- دریافت و ذخیره خودکار اطلاعات املاک از API خارجی
- جستجو و فیلتر املاک
- زمانبندی به‌روزرسانی داده‌ها
- احراز هویت کاربران
- مدیریت نشست‌های کاربری
- API مستندسازی خودکار با Swagger UI

## نصب و راه‌اندازی

### پیش‌نیازها

- Python 3.9+
- PostgreSQL
- Git

### مراحل نصب

1. کلون کردن مخزن:
```bash
git clone https://github.com/your-username/project-name.git
cd project-name/Backend
```

2. ایجاد محیط مجازی:
```bash
python -m venv venv
source venv/bin/activate  # در لینوکس/مک
venv\Scripts\activate     # در ویندوز
```

3. نصب وابستگی‌ها:
```bash
pip install -r requirements.txt
```

4. تنظیم متغیرهای محیطی:
```
# فایل config.env
ENV=development
DATABASE_URL=postgresql://username:password@localhost:5432/dbname
API_KEY=your_api_key
SECRET_KEY=your_secret_key
CORS_ORIGINS=http://localhost:3000
```

5. راه‌اندازی برنامه:
```bash
uvicorn main:app --reload
```

## استفاده از API

### مستندات Swagger UI

برای مشاهده و آزمایش تمام API ها می‌توانید به مستندات Swagger UI در آدرس زیر مراجعه کنید:

```
http://localhost:8000/docs
```

این صفحه امکان مشاهده تمام endpoint ها، پارامترها، و آزمایش آنها را فراهم می‌کند.

### مسیرهای اصلی

- `GET /api/properties` - دریافت لیست املاک
- `GET /api/properties/{property_id}` - دریافت جزئیات یک ملک
- `POST /api/properties/update` - شروع به‌روزرسانی در پس‌زمینه
- `GET /api/properties/filters` - دریافت فیلترهای موجود
- `POST /api/properties/filter` - جستجو در املاک با فیلتر

- `POST /api/users/session` - ایجاد جلسه جدید
- `GET /api/users/session` - دریافت جلسه فعلی
- `DELETE /api/users/session` - حذف جلسه

## توسعه و تست

### اجرای تست‌ها

برای اجرای تست‌ها:

```bash
pytest
```

### مهاجرت دیتابیس

این پروژه از Alembic برای مدیریت مهاجرت‌های دیتابیس استفاده می‌کند:

```bash
# ایجاد یک مهاجرت جدید
alembic revision --autogenerate -m "توضیح تغییرات"

# اعمال مهاجرت‌ها
alembic upgrade head
```

## مشارکت در توسعه

1. Fork کردن پروژه
2. ایجاد شاخه جدید برای ویژگی‌ها یا اصلاحات
3. ارسال درخواست Pull
4. مطالعه فایل CHANGELOG.md برای مشاهده تغییرات اخیر

## جزئیات API های جدید

### دریافت املاک اخیر ایجاد شده
- **Endpoint**: POST /api/properties/latest-created
- **توضیحات**: دریافت ۱۰ ملک اخیر ایجاد شده
- **هدرها**: App-key (الزامی)
- **پاسخ**: لیست املاک و تعداد کل

### دریافت املاک اخیر به‌روزرسانی شده
- **Endpoint**: POST /api/properties/latest-updated
- **توضیحات**: دریافت ۱۰ ملک اخیر به‌روزرسانی شده
- **هدرها**: App-key (الزامی)
- **پاسخ**: لیست املاک و تعداد کل

### دریافت یک ملک با شناسه
- **Endpoint**: POST /api/properties/get-property
- **توضیحات**: دریافت اطلاعات کامل یک ملک با شناسه
- **هدرها**: App-key (الزامی)
- **پارامترها**: property_id (الزامی)
- **پاسخ**: اطلاعات کامل ملک

### دریافت فیلترهای موجود
- **Endpoint**: GET /api/properties/filters
- **توضیحات**: دریافت لیست تمام فیلترهای موجود برای املاک
- **هدرها**: App-key (الزامی)
- **پاسخ**: لیست فیلترهای موجود شامل شهرها، مناطق، انواع ملک و غیره

### فیلتر کردن املاک
- **Endpoint**: POST /api/properties/filter
- **توضیحات**: فیلتر کردن املاک با پارامترهای مختلف
- **هدرها**: App-key (الزامی)
- **پارامترها**:
  - search_type: نوع جستجو (اختیاری)
  - property_name: نام ملک (اختیاری)
  - min_price: حداقل قیمت (اختیاری)
  - max_price: حداکثر قیمت (اختیاری)
  - min_area: حداقل مساحت (اختیاری)
  - max_area: حداکثر مساحت (اختیاری)
  - property_type: نوع ملک (اختیاری)
  - city_id: شهر (اختیاری)
  - و سایر پارامترهای فیلتر
- **پاسخ**: لیست املاک فیلتر شده و تعداد کل

## تست‌ها

### اجرای تست‌ها

تست‌های پروژه با pytest نوشته شده‌اند و می‌توانید آن‌ها را با دستور زیر اجرا کنید:

```bash
python -m pytest
```