import openai
import os
import requests
import json
import pandas as pd
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
import uvicorn
import time
from cachetools import TTLCache, cached
from datetime import datetime, timezone
import re
from openai import AsyncOpenAI
import asyncio

cache = TTLCache(maxsize=100, ttl=600)

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
client = openai.OpenAI(api_key=api_key)

client_2 = AsyncOpenAI(api_key=api_key)  # استفاده از نسخه async

ESTATY_API_KEY = os.getenv("ESTATY_API_KEY")
ESTATY_API_URL = "https://panel.estaty.app/api/v1"

# ✅ Define headers for authentication
HEADERS = {
    "App-Key": ESTATY_API_KEY,
    "Content-Type": "application/json"
}

import random

memory_state = {}
last_property_id = None
last_properties_list = []
last_selected_property = None  # ✅ ذخیره آخرین ملکی که کاربر در مورد آن اطلاعات بیشتری خواسته
current_property_index = 0  # ✅ نگه‌داری ایندکس برای نمایش املاک بعدی


# ✅ تابع فیلتر املاک از API
def filter_properties(filters):
    print("🔹 فیلترهای ارسال‌شده به API:", filters)
    # filters["cache_bypass"] = random.randint(1000, 9999)
    """ جستجوی املاک بر اساس فیلترهای کاربر """
    response = requests.post(f"{ESTATY_API_URL}/filter", json=filters, headers=HEADERS)

    # print("🔹 وضعیت پاسخ API:", response.status_code)
    response_data = response.json()
    # print("🔹 داده‌های دریافت‌شده از API:", response_data)

    ####
    # filtered_properties = [
    #     property for property in response_data.get("properties", [])
    #     if property.get("sales_status", {}).get("name", "").lower() in ["available", "pre launch"]
    # ]

    ##########
    # فیلتر کردن املاک بر اساس وضعیت فروش و منطقه
    district_filter = filters.get("district")
    if district_filter:
        district_filter = district_filter.lower()

    # مقداردهی فیلتر قیمت
    max_price = filters.get("max_price")
    min_price = filters.get("min_price")

    # فیلتر کردن املاک بر اساس وضعیت فروش، منطقه و قیمت
    filtered_properties = [
        property for property in response_data.get("properties", [])
        if property.get("sales_status", {}).get("name", "").lower() in ["available"]
           and (district_filter is None or (
                    property.get("district") and property["district"].get("name", "").lower() == district_filter))
           and (max_price is None or (property.get("low_price") is not None and property["low_price"] <= max_price))
           and (min_price is None or (property.get("low_price") is not None and property["low_price"] >= min_price))
    ]

    ##########

    # print(f"🔹 تعداد املاک قابل فروش پس از فیلتر: {len(filtered_properties)}")
    return filtered_properties

    ####

    # return response.json().get("properties", [])


# ✅ تابع دریافت اطلاعات کامل یک ملک خاص
def fetch_single_property(property_id):
    """ دریافت اطلاعات تکمیلی ملک از API """
    response = requests.post(f"{ESTATY_API_URL}/getProperty", json={"id": property_id}, headers=HEADERS)
    return response.json().get("property", {})


# property_data = fetch_single_property(1560)  # جایگذاری ID یک ملک واقعی
# print("🔹 اطلاعات ملک دریافت‌شده از API:", property_data)


# ✅ راه‌اندازی FastAPI
app = FastAPI()


# ✅ مدل دریافت پیام از کاربر
class ChatRequest(BaseModel):
    message: str


# ✅ استخراج فیلترهای جستجو از پیام کاربر
def extract_filters(user_message: str, previous_filters: dict):
    """ استفاده از GPT-4 برای استخراج اطلاعات کلیدی از پیام کاربر """
    prompt = f"""
    کاربر به دنبال یک ملک در دبی است. از پیام زیر جزئیات مرتبط را استخراج کن:

    "{user_message}"


    **🔹 اطلاعات قبلی کاربر درباره جستجوی ملک:**
    ```json
    {json.dumps(previous_filters, ensure_ascii=False)}
    ```

    **📌 قوانین پردازش:**
    - 🚨 اگر یکی از موارد max_price: حداکثر بودجه، bedrooms: تعداد اتاق‌خواب در پیام کاربر یا در اطلاعات قبلی کاربر موجود نیست مقدار "search_ready": false قرا بده و سؤالات پیشنهادی را که اطلاعاتش توسط کاربر داده نشده را بپرس.
    - اگر `district`, `city`, یا `property_type` جدیدی داده شده که با مقدار قبلی **فرق دارد**، مقدار `"new_search"` را `true` تنظیم کن.
    - 🚨 **اگر کلمه "منطقه" بدون ذکر نام خاصی آمده باشد (مثل "همین منطقه")، مقدار `district` را تغییر نده و `new_search` را `false` بگذار.**  
    - **اگر کاربر از کلماتی مانند "قیمت بالاتر"، "گرون‌تر"، "بالای X" استفاده کند، مقدار `min_price` را تنظیم کن.**
    - **اگر کاربر از کلماتی مانند "قیمت پایین‌تر"، "ارزون‌تر"، "زیر X" استفاده کند، مقدار `max_price` را تنظیم کن .**
    - 🚨 اگر `min_price` مقدار جدیدی دارد، ولی `max_price` در پیام جدید ذکر نشده، مقدار `max_price` را **حتماً حذف کن** (حتی اگر مقدار قبلی وجود داشته باشد).
    - 🚨 اگر `max_price` مقدار جدیدی دارد، ولی `min_price` در پیام جدید ذکر نشده، مقدار `min_price` را **حتماً حذف کن** (حتی اگر مقدار قبلی وجود داشته باشد).
    - اگر `min_price` و `max_price` جدید داده نشده، مقدار قبلی را نگه دار.
    - اگر اسامی مناطق یا نوع property به فارسی نوشته شد اول انگلیسیش کن بعد ذخیره کن
    - اگر مقدار `search_ready` قبلاً `false` بوده، ولی اطلاعات کافی اضافه شده باشد، مقدار `new_search` را `false` بگذار و `search_ready` را `true` تنظیم کن.
    - 🚨 اگر کاربر درباره `district` یا `max_price` یا `bedrooms` چیزی نگفت یا عباراتی مانند "برام فرقی نداره"، "هرچند اتاق باشه اوکیه"، "مهم نیست چندتا اتاق داشته باشه" را گفت، مقدار `bedrooms` را `null` قرار بده و آن را در فیلتر لحاظ نکن.
    - 🚨 اگر کاربر درباره `bedrooms` چیزی نگفت یا عباراتی مانند "فرقی نداره"، "هرچند اتاق باشه اوکیه"، "مهم نیست چندتا اتاق داشته باشه" را گفت، مقدار `bedrooms` را `null` قرار بده، و **نباید در `questions_needed` قرار بگیرد.**
    - وقتی کاربر بودجه میگه منظور max_price است
    - اگر پیام کاربر فقط اطلاعات تکمیلی (مثلاً قیمت، منطقه یا تعداد اتاق) را اضافه کرده باشد و تغییری در موارد قبلی نداده باشد، مقدار `"new_search"` را `false` بگذار.
    - **🚨 مهم:** `questions_needed` را فقط برای اطلاعاتی که هنوز موجود نیستند برگردان، نه برای اطلاعاتی که قبلاً داده شده‌اند.
    - **🚨 اگر کاربر منطقه جدیدی گفته و `district` تغییر کرده، حتماً مقدار جدید را جایگزین مقدار قبلی کن.**
    - **🚨 تو تشخیص 'district' دقت کن و بدون که مناطقی در دوبی گفته میشود **
    - **🚨 تو سوالاتی که میپرسی دقت کن که اگر مقدریش چه قبلا چه الان داده شده درمورد اون سوال نپرس **
    - ** فقط اطلاعاتی را که در پیام جدید کاربر **نیامده است و در اطلاعات قبلی نیز وجود ندارد**، در `questions_needed` قرار بده.** 
    -  اگر منطقه یا بودجه یا تعداد اتاق خواب مشخص نشده بود سوال متناسب با آنرا از ** questions_needed انتخاب و خروجی بده**
    - **اگر مقدار `district` مشخص است، دیگر نباید در `questions_needed` ظاهر شود.**
    - **اگر مقدار `district` null است پرسیده شود و seacrch_ready مقدارش false بزار باید در `questions_needed` سوال در مورد منطقه که در.**
    -  اگر نام منطقه (district) در پیام کاربر وجود دارد ولی واژه‌ی "منطقه" در کنار آن نیامده، همچنان آن را به‌عنوان منطقه تشخیص بده.
    - اگر کاربر گفت اقساط یا پرداخت بعد از تحویل مقدار 'post_delivery' را 'Yes' بذار و اگر گفت نداشته باشه مقدارش را 'No' بذار.
    - اگر کاربر گفت برنامه پرداخت داشته باشه مقدار 'payment_plan' را 'Yes' بذار و اگر گفت نداشته باشه مقدارش را 'No' بذار.
    - اگر کاربر گفت گارانتی اجاره داشته باشه مقدار 'guarantee_rental_guarantee' را 'Yes' بذار و اگر گفت نداشته باشه مقدارش را 'No' بذار.
    - 🚨 **نکته:** اگر کاربر فقط "اقساط" گفت و اشاره‌ای به برنامه پرداخت نکرد، مقدار `payment_plan` را به اشتباه 'yes' نکن!  
    - 🚨 **نکته:** اگر کاربر فقط "برنامه پرداخت" گفت و اشاره‌ای به پرداخت بعد از تحویل نکرد، مقدار `post_delivery` را به اشتباه 'yes' نکن!  
    - **قیمت‌ها (`min_price`, `max_price`) باید همیشه به عنوان `عدد` (`int`) برگردانده شوند، نه `string`**.
    - اسم شرکت ها رو به انگلیسی ذخیره کن. اگر به فارسی نوشته شده با توجه به اطلاعاتت اسم شرکت رو ذخیره کن یا چیزی نزدیک به آن را
    - امکانات گفته شده رو به انگلیسی ذخیره کن
    - اگر کاربر گفت 'با حدود X میلیون خونه میخوام' یا 'با X میلیون خونه میخوام'، مقدار X را به عدد تبدیل کن و برای فیلدهای `min_price` و `max_price` به‌صورت زیر مقداردهی کن:
        - مقدار `max_price` را 100000  بیشتر از مقدار گفته‌شده قرار بده.
        - مقدار `min_price` را 100000  کمتر از مقدار گفته‌شده تنظیم کن.


    - **اگر اطلاعات ناقص است، لیست سؤالات موردنیاز برای تکمیل را بده.**

    خروجی باید یک شیء JSON باشد که شامل فیلدهای زیر باشد:
    - "new_search": true | false
    - "search_ready": true | false
    - "questions_needed": ["بودجه شما چقدر است؟", "چند اتاق خواب مدنظرتان است؟"]
    - "city" (مثلاً "Dubai")
    - "district" (منطقه اگر ذکر شده، مانند "JVC")
    - "property_type" ("مثلاً "Residential"، "Commercial")
    - "apartmentType" ("مثلاً "apartment"، "villa"، "penthouse")
    - "max_price" (اگر اشاره شده)
    - "min_price" (اگر اشاره شده)
    - "bedrooms" (اگر مشخص شده. مثلا میتونه عدد باشه اگر کاربر تعداد اتاق خواب رو بگه یا میتونه نوشته باشه مثلا کاربر بگه استودیو میخوام اونوقت studio رو ذخیره کن)
    - "min_area" (اگر ذکر شده)
    - "max_area" (اگر ذکر شده)
    - "sales_status" ("مثلاً "موجود )
    - "developer_company" (اگر شرکت سازنده ذکر شده)
    - "delivery_date" ( اگر ذکر شده به فرمت `YYYY-MM` خروجی بده)
    - "payment_plan" (اگر ذکر شده و میخواد 'Yes' بده اگر نخواست 'No' بده اگر چیزی نگفت 'null' بزار)
    - "post_delivery" (اگر ذکر شده و میخواد 'Yes' بده اگر نخواست 'No' بده اگر چیزی نگفت 'null' بزار)
    - "guarantee_rental_guarantee" (اگر ذکر شده و میخواد 'Yes' بده اگر نخواست 'No' بده اگر چیزی نگفت 'null' بزار)
    - "facilities_name" (امکانات املاک مثل "Cinema"، "Clinic")


    **اگر هر یک از این فیلدها در درخواست کاربر ذکر نشده بود، مقدار آن را null قرار بده.**
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": prompt}]
        )

        print("🔹 پاسخ OpenAI:", response)

        # ✅ دریافت مقدار `content` از پاسخ OpenAI
        response_content = response.choices[0].message.content.strip()

        if not response_content:
            print("❌ OpenAI response is empty!")
            return {}

        # ✅ حذف ` ```json ` و ` ``` ` از رشته بازگشتی
        if response_content.startswith("```json"):
            response_content = response_content.replace("```json", "").replace("```", "").strip()

        print("🔹 داده JSON پردازش شده:", response_content)
        extracted_data = json.loads(response_content)
        # حفظ فیلترهای قبلی اگر مقدار جدیدی ارائه نشده باشد

        # if not extracted_data.get("search_ready"):
        #     missing_questions = extracted_data.get("questions_needed", [])
        #     if missing_questions:
        #         return "❓ برای جستجو، لطفاً این اطلاعات را مشخص کنید: " + "، ".join(missing_questions)

        # بررسی اگر `bedrooms`, `max_price`, `district` مقدار داشته باشند، `search_ready` را `true` کن
        # , "developer_company", "post_delivery", "facilities_name", "guarantee_rental_guarantee", "payment_plan"
        essential_keys = ["bedrooms", "max_price"]

        for key in essential_keys:
            if extracted_data.get(key) is None and memory_state.get(key) is not None:
                extracted_data[key] = memory_state[key]  # ✅ مقدار قبلی را نگه دار

        if extracted_data.get("bedrooms") is not None and extracted_data.get("max_price") is not None:
            extracted_data["search_ready"] = True  # ✅ اطلاعات کافی است، `search_ready` را `true` کن
            extracted_data["questions_needed"] = []
        else:
            extracted_data["search_ready"] = False  # 🚨 اطلاعات ناقص است، `search_ready` باید `false` بماند

        if not extracted_data.get("search_ready"):
            missing_questions = extracted_data.get("questions_needed", [])
            if missing_questions:
                extracted_data["questions_needed"] = missing_questions  # سوالات را داخل `extracted_data` نگه دار

        if extracted_data.get("new_search"):
            previous_filters.clear()  # **✅ ریست `memory_state`**

        # if extracted_data.get("new_search"):
        #     if previous_filters.get("search_ready") is False:
        #         extracted_data["new_search"] = False  # ✅ `new_search` را `false` نگه دار، چون هنوز اطلاعات قبلی تکمیل نشده
        #     else:
        #         previous_filters.clear()

        print("🔹 خروجی در تابع:", extracted_data)

        # ✅ بررسی تغییر مقدار `min_price` و `max_price`
        if extracted_data.get("min_price") is not None and extracted_data.get("max_price") is None:
            extracted_data["max_price"] = None

        if extracted_data.get("max_price") is not None and extracted_data.get("min_price") is None:
            extracted_data["min_price"] = None

        if extracted_data.get("district") is None:
            extracted_data["district"] = previous_filters.get("district")

        previous_filters.update(extracted_data)

        # ✅ پردازش رشته JSON به یک دیکشنری
        return extracted_data

    except json.JSONDecodeError as e:
        print("❌ JSON Decode Error:", e)
        return {}

    except Exception as e:
        print("❌ Unexpected Error:", e)
        return {}


property_name_to_id = {}


async def generate_ai_summary(properties, start_index=0):
    """ ارائه خلاصه کوتاه از املاک پیشنهادی به صورت تدریجی """

    global last_properties_list, current_property_index, selected_properties, property_name_to_id, comp_properties
    number_property = 3

    if not properties:
        return "متأسفانه هیچ ملکی با این مشخصات پیدا نشد. لطفاً بازه قیمتی را تغییر دهید یا منطقه دیگری انتخاب کنید."

    last_properties_list = properties
    comp_properties = properties
    current_property_index = start_index + number_property
    st_index = start_index + 1
    index_n = len(property_name_to_id) + 1

    selected_properties = properties[start_index:current_property_index]

    if not selected_properties:
        return "✅ تمامی املاک نمایش داده شده‌اند و مورد جدیدی موجود نیست."

    formatted_output = ""
    # ✅ **ذخیره نام ملک و ID آن برای جستجوهای بعدی**
    for prop in selected_properties:
        prop_name = prop.get("title", "").strip().lower()
        prop_id = prop.get("id")

        # ✅ تبدیل تاریخ تحویل اگر مقدار دارد
        if "delivery_date" in prop and isinstance(prop["delivery_date"], str):
            unix_timestamp = int(prop["delivery_date"])  # تبدیل رشته به عدد
            prop["delivery_date"] = datetime.fromtimestamp(unix_timestamp, tz=timezone.utc).strftime('%Y-%m-%d')

        if prop_name and prop_id:
            property_name_to_id[prop_name] = prop_id

    print("📌 لیست املاک ذخیره‌شده پس از مقداردهی:", property_name_to_id)
    print("📌 تعداد املاک ذخیره‌شده:", len(property_name_to_id))

    async def process_property(prop, index):
        """ پردازش و نمایش هر ملک به‌صورت جداگانه بدون انتظار برای بقیه """
        image_url = prop.get("cover", "https://via.placeholder.com/150")
        property_id = prop.get("id")

        # ✅ پرامپت برای خلاصه‌سازی املاک
        prompt = f"""
        شما یک مشاور املاک در دبی هستید. کاربران به دنبال خرید ملک در دبی هستند. 
        لطفاً خلاصه‌ای کوتاه و جذاب به زبان فارسی از این املاک ارائه دهید تا کاربر بتواند راحت‌تر انتخاب کند:

        {json.dumps(prop, ensure_ascii=False, indent=2)}

        **📌 مقدار 'index' برای شماره‌گذاری املاک: {index}**


        اطلاعاتی که می‌توان ارائه داد شامل:
        - 🏡 {index}. نام پروژه: نام ملک (به انگلیسی)
        - 🏡 معرفی کلی ملک  
        - 📍 موقعیت جغرافیایی  
        - زمان تحویل: (آماده تحویل / در حال ساخت ) و تاریخ تحویل به میلادی و تاریخی که میخوای بنویسی رو قبلش به ماهی که بهش نزدیکه گرد کن یعنی اگر اخر فوریه 2027 هست بنویس مارچ 2027 و برای بقیه ماه ها هم همین الگو را داشته باش
        - 💲 شروع قیمت به درهم
        - 📏 حداقل مساحت حتما به فوت مربع
        - 🔗 لینک مشاهده اطلاعات کامل ملک در سایت رسمی **[سایت Trunest](https://www.trunest.ae/property/{property_id})**


        **لحن شما باید حرفه‌ای، صمیمی و کمک‌کننده باشد، مثل یک مشاور املاک واقعی که به مشتری توضیح می‌دهد.**

        **قوانین پاسخ:**
        - شماره گذاری برای معرفی املاک رو از `{index}` بگیر و کنار اسم پروژه قرار بده.
        - معرفی کلی ملک کوتاه باشد در حد حداکثر سه خط و بقیه رو هم به صورت تیتر و متن بنویس
        - برای موقعیت جغرافیایی مختصات رو ننویس
        - قیمت، متراژ، موقعیت مکانی و یک ویژگی کلیدی را ذکر کنید.

        - تایتل‌ها را داخل `<h3>` قرار بده تا بزرگتر نمایش داده شوند.
        - متن توضیحی را داخل `<p>` قرار بده تا با اندازه عادی باشد.

        - حتماً لینک‌ها را به صورت **هایپرلینک HTML** بنویس. مثال: <a href="https://www.trunest.ae/property/{property_id}">🔗 سایت Trunest</a>


        """

        response = await client_2.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": prompt}]
        )

        return f"""
        <div style="display: flex; flex-direction: column; align-items: center; padding: 10px;">
            <img src="{image_url}" alt="تصویر ملک" style="width: 250px; height: 180px; border-radius: 8px; object-fit: cover;">
            <div style="flex-grow: 1; text-align: right;">
                {response.choices[0].message.content}
            </div>
        </div>
        """

    # # **📌 پردازش و نمایش املاک به محض آماده شدن**
    # tasks = [process_property(prop, index) for index, prop in enumerate(selected_properties, start=index_n)]
    # results = await asyncio.gather(*tasks)

    # formatted_output += "".join(results)

    # # **📌 پردازش و نمایش املاک به محض آماده شدن**
    # for index, prop in enumerate(selected_properties, start=index_n):
    #     formatted_output += await process_property(prop, index)

    # **📌 پردازش همزمان سه ملک و نمایش به ترتیب**
    results = await asyncio.gather(
        *[process_property(prop, index) for index, prop in enumerate(selected_properties, start=index_n)]
    )

    formatted_output += "".join(results)

    # ✅ جمله پایانی برای راهنمایی کاربر
    formatted_output += """
    <div style="text-align: right; direction: rtl; padding: 10px; width: 100%;">
        <p style="margin: 0;">برای مشاهده اطلاعات بیشتر درباره هر ملک، لطفاً عبارت <b>'پروژه [نام پروژه] را بیشتر توضیح بده'</b> را بنویسید.</p>
        <p style="margin-top: 5px;">اگر به املاک بیشتری نیاز دارید، بگویید: <b>'املاک بیشتری نشان بده'</b>.</p>
    </div>
    """

    return formatted_output


# ✅ تابع ارائه اطلاعات تکمیلی یک ملک خاص
def generate_ai_details(property_id, detail_type=None):
    """ ارائه اطلاعات تکمیلی یک ملک خاص یا بخشی خاص از آن """

    global property_name_to_id, selected_properties
    selected_property = next((p for p in selected_properties if p.get("id") == property_id), None)
    if not selected_property:
        print(f"❌ هشدار: ملکی با آی‌دی {property_id} در selected_properties پیدا نشد!")
        selected_property = {}  # **اگر اطلاعات قبلی وجود ندارد، دیکشنری خالی باشد**

    detailed_info = fetch_single_property(property_id)

    combined_info = {**selected_property, **detailed_info}
    combined_info["property_url"] = f"https://www.trunest.ae/property/{property_id}"

    # ✅ در صورتی که کاربر درخواست جزئیات خاصی کرده باشد
    if detail_type:
        prompt = f"""
        شما یک مشاور املاک در دبی هستید که به زبان فارسی صحبت میکند. کاربران می‌خواهند اطلاعات بیشتری درباره بخش خاصی از این ملک بدانند.

        اطلاعات ملک:
        {json.dumps(combined_info, ensure_ascii=False, indent=2)}

        **جزئیاتی که کاربر درخواست کرده:** {detail_type}

        لطفاً فقط اطلاعات مربوط به این بخش را به‌صورت حرفه‌ای، دقیق و کمک‌کننده ارائه دهید.
        """

    else:
        # ✅ پرامپت برای توضیح تکمیلی کلی ملک
        prompt = f"""
        شما یک مشاور املاک در دبی هستید که به زبان فارسی صحبت میکند. لطفاً اطلاعات زیر را به‌فارسی روان و طبیعی به صورت حرفه‌ای، دقیق و کمک‌کننده ارائه دهید:


        {json.dumps(combined_info, ensure_ascii=False, indent=2)}

        لحن شما باید حرفه‌ای، دوستانه و کمک‌کننده باشد. اطلاعاتی که می‌توان ارائه داد شامل:
        - **آی‌دی ملک** (برای بررسی دقیق‌تر)
        - 🏡 نام ملک (به انگلیسی)
        - 🏡 معرفی کلی ملک و دلیل پیشنهاد آن
        - 📍 موقعیت جغرافیایی و دسترسی‌ها
        - 🏡 وضعیت فروش (آماده تحویل / در حال ساخت / فروخته شده)
        - 📏 حداقل مساحت واحد ها حتما به فوت مربع
        - 💲 قیمت انواع واحد ها
        - 🏆 امکانات برجسته
        - 🏗 وضعیت ساخت 
        - 💰 شرایط پرداخت
        - 🔗 لینک مشاهده اطلاعات کامل ملک در سایت رسمی

        **قوانین پاسخ:**
        - حتماً لینک‌ها را به صورت **هایپرلینک HTML** بنویس. مثال: <a href="https://www.trunest.ae/property/{selected_properties[0]['id']}">🔗 سایت Trunest</a>
        - تایتل‌ها را داخل `<h3>` قرار بده تا بزرگتر نمایش داده شوند.
        - متن توضیحی را داخل `<p>` قرار بده تا با اندازه عادی باشد.

        """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": prompt}]
    )

    return response.choices[0].message.content


from duckduckgo_search import DDGS
from fastapi import HTTPException


async def fetch_real_estate_trends(query):
    """ جستجو در اینترنت و خلاصه کردن اطلاعات بازار مسکن دبی """
    try:
        if "دبی" in query or "امارات" in query or "Dubai" in query or "UAE" in query:
            search_query = query  # تغییر نده، چون دبی در متن هست
        else:
            search_query = f"{query} در امارت"  # اضافه کردن "in Dubai"

        print(f"🔍 **جستجوی دقیق:** {search_query}")  # برای دیباگ

        search_summary = ""  # مقدار پیش‌فرض برای جلوگیری از کرش

        try:
            # ✅ جستجو در اینترنت با DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(search_query, max_results=5))

            if results:
                search_summary = "\n".join([f"{r['title']}: {r['body']}" for r in results if 'body' in r])
            else:
                print("⚠️ هیچ نتیجه‌ای از DDGS دریافت نشد.")

        except Exception as e:
            print(
                f"⚠️ خطا در جستجو با DDGS: {str(e)}. ادامه فقط با اطلاعات GPT.")  # هندل کردن تایم‌اوت و سایر خطاهای احتمالی

        prompt = f"""
        کاربز این سوال رو پرسیده :

        "{search_query}"

        همچنین این اطلاعات از اینترنت گرفته شده : 
        "{search_summary if search_summary else 'هیچ نتیجه‌ای از اینترنت دریافت نشد.'}"


        **🔹 لطفاً یک پاسخ دقیق، کوتاه و مفید در ۳ الی ۴ جمله به زبان فارسی  با توجه به اطلاعات خودت که میتونی به پیام کاربر جواب بدی و همچنین اطلاعاتی که از اینترنت گرفته شده بده و ارائه بده.**
        - لحن پاسخ باید حرفه‌ای و کمک‌کننده باشد.
        - اگر اطلاعات کافی نیست، جمله‌ای مانند "لطفاً به وب‌سایت‌های رسمی مراجعه کنید" اضافه کن.
        """

        ai_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": prompt}],
            max_tokens=150
        )

        return ai_response.choices[0].message.content.strip()

    except Exception as e:
        print(f"❌ خطا در جستجو: {str(e)}")  # لاگ خطا
        raise HTTPException(status_code=500, detail=f"خطا در جستجو یا پردازش اطلاعات: {str(e)}")


async def fetch_real_estate_buying_guide(user_question):
    """ جستجو و ارائه پاسخ به سؤالات درباره خرید ملک، ویزا و مالیات در دبی """

    try:
        if "دبی" in user_question or "امارات" in user_question or "Dubai" in user_question or "UAE" in user_question:
            search_query = user_question  # تغییر نده، چون دبی در متن هست
        else:
            search_query = f"{user_question} در امارات"  # اضافه کردن "in Dubai"

        print(f"🔍 **جستجوی دقیق:** {search_query}")  # برای دیباگ

        # # ✅ جستجوی مستقیم **سؤال کاربر**
        # search_query = user_question  # 🔹 جستجوی همان پیام کاربر!
        # print(f"🔍 **جستجوی گوگل برای:** {search_query}")  # برای دیباگ

        search_summary = ""  # مقدار پیش‌فرض برای جلوگیری از کرش

        try:
            # ✅ جستجو در اینترنت با DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(search_query, max_results=5))

            if results:
                search_summary = "\n".join([f"{r['title']}: {r['body']}" for r in results if 'body' in r])
            else:
                print("⚠️ هیچ نتیجه‌ای از DDGS دریافت نشد.")

        except Exception as e:
            print(
                f"⚠️ خطا در جستجو با DDGS: {str(e)}. ادامه فقط با اطلاعات GPT.")  # هندل کردن تایم‌اوت و سایر خطاهای احتمالی

        # ✅ ارسال اطلاعات به GPT برای تولید خلاصه فارسی
        response_prompt = f"""
        کاربز این سوال رو پرسیده :

        "{search_query}"

        همچنین این اطلاعات از اینترنت گرفته شده : 
        "{search_summary if search_summary else 'هیچ نتیجه‌ای از اینترنت دریافت نشد.'}"


        **🔹 لطفاً یک پاسخ دقیق، کوتاه و مفید در ۳ الی ۴ جمله به زبان فارسی  با توجه به اطلاعات خودت که میتونی به پیام کاربر جواب بدی و همچنین اطلاعاتی که از اینترنت گرفته شده بده و ارائه بده.**
        - لحن پاسخ باید حرفه‌ای و کمک‌کننده باشد.
        - اگر اطلاعات کافی نیست، جمله‌ای مانند "لطفاً به وب‌سایت‌های رسمی مراجعه کنید" اضافه کن.
        """
        ai_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": response_prompt}],
            max_tokens=150
        )

        return ai_response.choices[0].message.content.strip()

    except Exception as e:
        print(f"❌ خطا در جستجو: {str(e)}")  # لاگ خطا
        raise HTTPException(status_code=500, detail=f"خطا در جستجو یا پردازش اطلاعات: {str(e)}")


import json
from fuzzywuzzy import process


async def extract_property_identifier(user_message, property_name_to_id):
    """با استفاده از هوش مصنوعی، شماره یا نام ملک را از پیام کاربر استخراج می‌کند و ID آن را برمی‌گرداند."""

    # ✅ چاپ دیکشنری برای دیباگ
    print(f"📌 دیکشنری property_name_to_id: {property_name_to_id}")

    # **نام‌های املاک برای بررسی تطابق**
    property_names = list(property_name_to_id.keys())
    print(f"📌 لیست نام املاک برای تشخیص: {property_names}")

    if not property_names:
        return None  # اگر لیست خالی باشد، مقدار None برگردان

    # **پرامپت برای تشخیص شماره یا نام ملک**
    prompt = f"""
    کاربر یک مشاور املاک در دبی را خطاب قرار داده و در مورد جزئیات یک ملک سؤال می‌کند.

    **لیست املاک موجود:**
    {json.dumps(property_names, ensure_ascii=False)}

    **متن کاربر:**
    "{user_message}"

    **آیا کاربر شماره یا نام یکی از املاک بالا را مشخص کرده است؟**
    - اگر عددی چه به فارسی چه به انگلیسی ذکر شده (مثلاً ۲)، فقط همان عدد را در خروجی بده.  
    - اگر id ملک نوشته شده 
    - اگر نام یکی از املاک بالا ذکر شده، فقط نام آن را در خروجی بده.
    - اگر کاربر عباراتی مانند "ملک دوم"، "ملک شماره ۲"، "دومین ملک" و... استفاده کرد، شماره ملک را به ترتیب در لیست بگیر.

    **خروجی فقط شامل مقدار باشد:**
    - یک عدد (مثلاً `2`)
    - یا نام ملک (مثلاً `"Marriott Residences"`)
    """

    ai_response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": prompt}],
        max_tokens=30
    )

    extracted_info = ai_response.choices[0].message.content.strip()
    print(f"📌 پاسخ AI برای تشخیص ملک: {extracted_info}")

    if not extracted_info:
        return None

    # ✅ بررسی عددی بودن مقدار استخراج‌شده (اگر شماره ملک باشد)
    if extracted_info.isdigit():
        extracted_index = int(extracted_info) - 1  # **تبدیل شماره به ایندکس (1-based to 0-based)**

        if 0 <= extracted_index < len(property_names):  # **بررسی اینکه عدد در محدوده باشد**
            property_name = property_names[extracted_index]
            return property_name_to_id[property_name]  # **برگرداندن `id` ملک**

        return None  # اگر عدد معتبر نبود، مقدار `None` برگردد

    # ✅ بررسی اینکه آیا نام ملک در دیکشنری هست؟
    extracted_info = extracted_info.lower().strip()
    if extracted_info in property_name_to_id:
        return property_name_to_id[extracted_info]  # **برگرداندن `id` ملک**

    # ✅ اگر تطابق ۱۰۰٪ نبود، از fuzzy matching استفاده کن
    best_match, score = process.extractOne(extracted_info, property_names)
    print(f"📌 بهترین تطابق fuzzy: {best_match} (امتیاز: {score})")

    if score > 70:  # **اگر دقت بالا بود، مقدار را قبول کن**
        return property_name_to_id[best_match]

    return None  # **اگر هیچ تطابقی پیدا نشد، `None` برگردان**


def fetch_properties_from_estaty(property_names):
    """ جستجوی دو ملک در Estaty API برای دریافت ID آن‌ها """
    found_properties = []

    for name in property_names:
        filters = {"property_name": name}
        response = requests.post(f"{ESTATY_API_URL}/filter", json=filters, headers=HEADERS)

        if response.status_code == 200:
            properties = response.json().get("properties", [])
            if properties:
                found_properties.append((properties[0]["title"], properties[0]["id"]))

    return found_properties


async def compare_properties(user_message: str) -> str:
    """ مقایسه‌ی دو یا چند ملک و ارائه بهترین پیشنهاد """

    global comp_properties, property_name_to_id

    mentioned_properties = []

    # ✅ **بررسی اینکه آیا کاربر شماره‌ی املاک را وارد کرده است**
    property_numbers = re.findall(r'[\d۰۱۲۳۴۵۶۷۸۹]+', user_message)  # استخراج اعداد از متن
    mentioned_properties = []

    if len(property_numbers) == 2:
        first_index = int(property_numbers[0]) - 1  # ایندکس‌ها از 0 شروع می‌شوند
        second_index = int(property_numbers[1]) - 1

        if 0 <= first_index < len(comp_properties) and 0 <= second_index < len(comp_properties):
            mentioned_properties.append((comp_properties[first_index]["title"], comp_properties[first_index]["id"]))
            mentioned_properties.append((comp_properties[second_index]["title"], comp_properties[second_index]["id"]))

    # # ✅ **اگر اعداد پیدا نشدند، بررسی کنیم که آیا کاربر نام ملک را نوشته است**
    # if not mentioned_properties:
    #     for prop_name in property_name_to_id.keys():
    #         if prop_name in user_message:
    #             mentioned_properties.append((prop_name, property_name_to_id[prop_name]))

    if not mentioned_properties:
        # user_property_names = re.findall(r'\b[A-Za-z0-9\-]+\b', user_message)  # پیدا کردن نام‌های املاک از متن کاربر
        user_property_names = re.findall(r'([A-Za-z0-9\-]+(?:\s[A-Za-z0-9\-]+)*)',
                                         user_message)  # پیدا کردن نام‌های املاک از متن کاربر
        print(user_property_names)

        for user_prop in user_property_names:
            user_prop = user_prop.strip().lower()
            if user_prop in property_name_to_id:  # ✅ **اگر نام ملک قبلاً معرفی شده باشد**
                if user_prop not in dict(mentioned_properties):  # جلوگیری از تکراری شدن
                    mentioned_properties.append((user_prop, property_name_to_id[user_prop]))
            else:
                # ✅ **بررسی شباهت فقط برای املاک قبلاً معرفی‌شده**
                best_match, score = process.extractOne(user_prop,
                                                       property_name_to_id.keys()) if property_name_to_id else (None, 0)
                print(f"📌 بهترین تطابق fuzzy: {best_match} (امتیاز: {score})")

                if score > 75:  # **اگر شباهت بالای ۷۵٪ بود، این ملک را در نظر بگیر**
                    mentioned_properties.append((best_match, property_name_to_id[best_match]))

    # ✅ **بررسی تعداد املاک شناسایی شده**
    if len(mentioned_properties) < 2:
        # mentioned_names = re.findall(r'\b[A-Za-z0-9\-]+\b', user_message)  # پیدا کردن نام املاک از متن
        mentioned_names = re.findall(r'([A-Za-z0-9\-]+(?:\s[A-Za-z0-9\-]+)*)',
                                     user_message)  # پیدا کردن نام املاک از متن

        print(mentioned_names)

        if len(mentioned_names) >= 2:
            found_properties = fetch_properties_from_estaty(mentioned_names[:2])
            if len(found_properties) == 2:
                mentioned_properties.extend(found_properties)

    # ✅ **بررسی تعداد املاک شناسایی شده**
    if len(mentioned_properties) < 2:
        return "❌ لطفاً دقیق‌تر مشخص کنید که کدام دو ملک را می‌خواهید مقایسه کنید. می‌توانید نام یا شماره‌ی ملک را وارد کنید."

    # ✅ **دریافت اطلاعات دو ملک**
    first_property_name, first_property_id = mentioned_properties[0]
    second_property_name, second_property_id = mentioned_properties[1]

    first_property_details = fetch_single_property(first_property_id)
    second_property_details = fetch_single_property(second_property_id)

    # **بررسی اینکه آیا اطلاعات ملک‌ها پیدا شده است**
    if not first_property_details or not second_property_details:
        return "❌ متأسفم، نتوانستم اطلاعات یکی از این املاک را پیدا کنم."

    # for prop_name in property_name_to_id.keys():
    #     if prop_name in user_message:
    #         mentioned_properties.append((prop_name, property_name_to_id[prop_name]))

    # # ✅ **بررسی تعداد املاک شناسایی شده**
    # if len(mentioned_properties) < 2:
    #     return "❌ لطفاً نام املاکی که میخواهید مقایسه کنید را مشخص کنید."

    # # ✅ **دریافت اطلاعات دو ملک**
    # first_property_name, first_property_id = mentioned_properties[0]
    # second_property_name, second_property_id = mentioned_properties[1]

    # first_property_details = fetch_single_property(first_property_id)
    # second_property_details = fetch_single_property(second_property_id)

    # # **بررسی اینکه آیا اطلاعات ملک‌ها پیدا شده است**
    # if not first_property_details or not second_property_details:
    #     return "❌ متأسفم، نتوانستم اطلاعات یکی از این املاک را پیدا کنم."

    # ✅ پردازش داده‌ها برای مقایسه
    comparison_prompt = f"""
    شما یک مشاور املاک حرفه‌ای در دبی به زبان فارسی هستید. در ادامه اطلاعات چند ملک آورده شده است. لطفاً آن‌ها را از نظر:
    - 💲 قیمت 
    - 📏 متراژ و تعداد اتاق خواب 
    - 📍 موقعیت جغرافیایی  
    - 🏗 وضعیت فروش (در حال ساخت یا آماده تحویل)و تاریخ تحویل  
    - 🏆ویژگی‌های برجسته  

    مقایسه کنید و در نهایت **بهترین گزینه را برای خرید معرفی کنید**.

    **🔹 اطلاعات ملک اول ({first_property_name}):**  
    {json.dumps(first_property_details, ensure_ascii=False, indent=2)}

    **🔹 اطلاعات ملک دوم ({second_property_name}):**  
    {json.dumps(second_property_details, ensure_ascii=False, indent=2)}

    🔹 **جمع‌بندی:**  
    - مشخص کنید کدام ملک بهتر است و چرا؟  
    - اگر مزیت خاصی در هر ملک هست، ذکر کنید.  
    - پیشنهاد نهایی خود را به مشتری ارائه دهید.  


    - تایتل‌ها را داخل `<h3>` قرار بده تا بزرگتر نمایش داده شوند.
    - متن توضیحی را داخل `<p>` قرار بده تا با اندازه عادی باشد.
    """

    ai_response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": comparison_prompt}]
    )

    return ai_response.choices[0].message.content.strip()


async def process_purchase_request(user_message: str) -> str:
    """ بررسی درخواست خرید ملک و ارائه اطلاعات پرداخت، اقساط و تخفیف‌ها """

    global property_name_to_id

    # ✅ **استخراج نام ملک از پیام کاربر**
    user_property_names = re.findall(r'([A-Za-z0-9\-]+(?:\s[A-Za-z0-9\-]+)*)', user_message)

    mentioned_properties = []

    # ✅ **بررسی نام ملک با Fuzzy Matching برای تشخیص غلط املایی**
    if property_name_to_id:
        for user_prop in user_property_names:
            best_match, score = process.extractOne(user_prop, property_name_to_id.keys())
            print(f"📌 بهترین تطابق fuzzy: {best_match} (امتیاز: {score})")  # دیباگ
            if score > 70:  # **اگر دقت بالای ۷۰٪ بود، مقدار را قبول کن**
                mentioned_properties.append((best_match, property_name_to_id[best_match]))

    # if not mentioned_properties:
    #     return "❌ لطفاً نام دقیق ملکی که قصد خرید آن را دارید مشخص کنید."
    if not mentioned_properties:
        # print("❌ ملک در لیست قبلی یافت نشد، جستجو در Estaty API انجام می‌شود...")
        found_properties = fetch_properties_from_estaty(user_property_names[:1])  # فقط اولین ملک را بررسی کن
        if not found_properties:
            return "❌ متأسفم، این ملک در لیست املاک موجود پیدا نشد. لطفاً نام دقیق‌تر را وارد کنید."

        mentioned_properties.append(found_properties[0])  # اولین ملک را به لیست اضافه کن

    # ✅ دریافت اطلاعات ملک از API
    property_name, property_id = mentioned_properties[0]
    property_details = fetch_single_property(property_id)

    if not property_details:
        return "❌ متأسفم، نتوانستم اطلاعات این ملک را پیدا کنم."

    # ✅ ایجاد پرامپت برای دریافت شرایط خرید ملک
    purchase_prompt = f"""
    شما یک مشاور املاک حرفه‌ای در دبی به زبان فارسی هستید. یک مشتری قصد خرید ملکی دارد و می‌خواهد درباره شرایط پرداخت و تخفیف‌های آن بداند.

    **🔹 مشخصات ملک:**  
    {json.dumps(property_details, ensure_ascii=False, indent=2)}

    🔹 **لطفاً اطلاعات زیر را ارائه دهید:**  
    - **قیمت کل ملک و روش‌های پرداخت**  
    - **مبلغ پیش‌پرداخت و شرایط اقساط**  
    - **تخفیف‌های احتمالی یا پیشنهادات ویژه**  
    - **مراحل رسمی خرید این ملک در دبی**  
    - 🔗 لینک مشاهده اطلاعات کامل ملک در سایت رسمی **[سایت Trunest](https://www.trunest.ae/property/{property_id})**

    **قوانین پاسخ:**
    - حتماً لینک‌ها را به صورت **هایپرلینک HTML** بنویس. مثال: <a href="https://www.trunest.ae/property/{selected_properties[0]['id']}">🔗 سایت Trunest</a>
    - تایتل‌ها را داخل `<h3>` قرار بده تا بزرگتر نمایش داده شوند.
    - متن توضیحی را داخل `<p>` قرار بده تا با اندازه عادی باشد.

    **لحن شما باید حرفه‌ای، دقیق و کمک‌کننده باشد.**  
    """

    ai_response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": purchase_prompt}]
    )

    return ai_response.choices[0].message.content.strip()


def find_districts_by_budget(max_price, bedrooms=None, apartment_typ=None, min_price=None):
    """جستجوی مناطق مناسب با توجه به بودجه و تعداد اتاق‌خواب"""

    filters = {
        "max_price": max_price
    }
    if min_price is not None:
        filters["min_price"] = min_price

    if apartment_typ is not None:
        apartment_typ = str(apartment_typ).strip().title()  # تبدیل به فرمت استاندارد
        # ✅ دیکشنری نگاشت نوع آپارتمان به `id`
        apartment_type_mapping = {
            "Apartment": 1,
            "Building": 31,
            "Duplex": 27,
            "Full Floor": 4,
            "Hotel": 32,
            "Hotel Apartment": 8,
            "Land / Plot": 6,
            "Loft": 34,
            "Office": 7,
            "Penthouse": 10,
            "Retail": 33,
            "Shop": 29,
            "Show Room": 30,
            "Store": 25,
            "Suite": 35,
            "Townhouse": 9,
            "Triplex": 28,
            "Villa": 3,
            "Warehouse": 26
        }

        # ✅ تبدیل مقدار `property_type` به `id` معادل آن
        filters["apartmentTypes"] = [apartment_type_mapping.get(apartment_typ, apartment_typ)]

    if bedrooms is not None:
        bedrooms_count = str(bedrooms)  # مقدار را به رشته تبدیل کن

        bedrooms_mapping = {
            "1": 10,
            "1.5": 23,
            "2": 11,
            "2.5": 24,
            "3": 12,
            "3.5": 25,
            "4": 13,
            "4.5": 26,
            "5": 14,
            "5.5": 27,
            "6": 15,
            "6.5": 28,
            "7": 16,
            "7.5": 29,
            "8": 17,
            "9": 18,
            "10": 19,
            "11": 22,
            "Studio": 9,
            "Penthouse": 34,
            "Retail": 31,
            "Office": 20,
            "Showroom": 35,
            "Store": 30,
            "Suite": 32,
            "Hotel Room": 33,
            "Full Floor": 36,
            "Land / Plot": 21
        }

        # مقدار `property_type` را به `id` تغییر بده
        filters["apartments"] = [bedrooms_mapping.get(bedrooms_count, bedrooms_count)]

    print(filters)

    response = requests.post(f"{ESTATY_API_URL}/filter", json=filters, headers=HEADERS)

    print(response)
    if response.status_code != 200:
        return "❌ خطا در دریافت اطلاعات مناطق. لطفاً دوباره امتحان کنید."

    data = response.json()
    properties = data.get("properties", [])

    if not properties:
        return "❌ متأسفم، هیچ منطقه‌ای متناسب با بودجه شما پیدا نشد."

    # ✅ استخراج مناطق و شمارش تعداد املاک موجود در هر منطقه
    district_counts = {}
    for prop in properties:
        district_info = prop.get("district")
        if district_info and isinstance(district_info, dict):  # بررسی می‌کنیم که district وجود دارد و دیکشنری است
            district_name = district_info.get("name")
            if district_name:
                district_counts[district_name] = district_counts.get(district_name, 0) + 1

    if not district_counts:
        return "❌ هیچ منطقه‌ای با این بودجه پیدا نشد."

    # ✅ مرتب‌سازی بر اساس تعداد املاک موجود
    sorted_districts = sorted(district_counts.items(), key=lambda x: x[1], reverse=True)

    # ✅ ایجاد پاسخ مناسب برای کاربر
    response_text = "**📍 مناطقی که با بودجه شما مناسب هستند:**\n"
    for district, count in sorted_districts[:5]:  # نمایش ۵ منطقه برتر
        response_text += f"- **{district}** ({count} ملک موجود)\n"

    return response_text


async def real_estate_chatbot(user_message: str) -> str:
    """ بررسی نوع پیام و ارائه پاسخ مناسب با تشخیص هوشمند """

    print(f"📌  user message : {user_message}")

    global last_properties_list, current_property_index, memory_state

    # ✅ **۱. تشخیص اینکه پیام فقط یک سلام است یا سوالی در مورد ملک**
    greetings = ["سلام", "سلام خوبی؟", "سلام چطوری؟", "سلام وقت بخیر", "سلام روزت بخیر"]
    if user_message.strip() in greetings:
        return random.choice([
            "سلام! من اینجا هستم که به شما در خرید ملک کمک کنم 😊 اگر سوالی در مورد املاک دارید، بفرمایید.",
            "سلام دوست عزیز! به چت‌بات مشاور املاک خوش آمدید. چطور می‌توانم کمکتان کنم؟ 🏡",
            "سلام! اگر به دنبال خرید یا سرمایه‌گذاری در املاک دبی هستید، من راهنمای شما هستم!",
        ])

    # ✅ **۲. استفاده از هوش مصنوعی برای تشخیص نوع درخواست کاربر**
    prompt = f"""
    کاربر در حال مکالمه با یک مشاور املاک در دبی به زبان فارسی است. پیام زیر را تجزیه و تحلیل کن:

    "{user_message}"


    **📌 اطلاعات قبلی مکالمه:**
    ```json
    {json.dumps(memory_state, ensure_ascii=False)}
    ```

    **🔹 نوع پیام قبلی:** "{memory_state.get('previous_type', 'unknown')}"


    **لطفاً مشخص کنید که پیام کاربر به کدام یک از این دسته‌ها تعلق دارد:**


    ### **۱. `search` - درخواست جستجوی ملک**  
    ✅ وقتی کاربر **به دنبال پیدا کردن یک ملک است **، مثلاً:  
    - "خانه‌ای در جمیرا می‌خوام"  
    - "یه آپارتمان با قیمت کمتر از دو میلیون درهم می‌خوام"  
    - "بهترین پروژه‌های سرمایه‌گذاری رو معرفی کن"  


    ❌ **این دسته را انتخاب نکنید اگر کاربر درباره روند خرید ملک در دبی سؤال کرده باشد.** 
    ❌ **این دسته را انتخاب کن اگر کاربر در جستجوی قبلی خود 'search' بود و پیام جدیدش کامل کننده پیام قبلیش مثل قیمت یا منطقه یا تعداد اتاق خواب بود**  



    ---

    ### **۲. `details` - درخواست اطلاعات بیشتر درباره‌ی یک ملک خاص**  
    ✅ وقتی کاربر می‌خواهد جزئیات یک ملک معرفی‌شده را بپرسد، مثلاً:  
    - "درباره ملک شماره ۲ توضیح بده"  
    - "امکانات ملک اول رو بگو"  
    - "قیمت ملک مارینا رزیدنس چقدره؟" 

    ---

    ### **۳. `more` - درخواست نمایش املاک بیشتر**  
    ✅ وقتی کاربر می‌خواهد املاک بیشتری ببیند، مثلاً:  
    - "ملکای بیشتری بهم نشون بده"  
    - "موردای دیگه‌ای داری؟"  

    ---

    ### **۴. `market` - سوال درباره وضعیت بازار مسکن در دبی**  
    ✅ وقتی کاربر درباره روند کلی بازار املاک دبی سؤال کند، مثلاً:  
    - "قیمت مسکن تو دبی تو ۲۰۲۵ چطوره؟"  
    - "سرمایه‌گذاری در ملک تو دبی چطوره؟"  
    - "روند قیمت‌ املاک تو چند سال آینده چجوریه؟"  

    ---

    ### **۵. `buying_guide` - سوال درباره نحوه خرید ملک در دبی**  
    ✅ وقتی کاربر **درباره روند خرید ملک، قوانین، ویزا یا مالیات یا درباره مناطق** بدون گفتن نام ملک سؤال می‌کند، مثلاً:  
    - "چطور در دبی خانه بخرم؟"  
    - "آیا خارجی‌ها می‌توانند در دبی ملک بخرند؟"  
    - "شرایط دریافت ویزای سرمایه‌گذاری چیه؟"  
    - "برای خرید ملک تو دبی باید مالیات بدم؟"  

    ❌ **این دسته را انتخاب نکنید اگر کاربر دنبال پیدا کردن یک خانه خاص باشد.**  

    ---

    ### **۶. `unknown` - نامشخص**  
    ✅ اگر پیام کاربر به هیچ‌کدام از موارد بالا مربوط نبود.  

    ---

    ### **۷. `reset` - کاربر می‌خواهد اطلاعات قبلی را حذف کرده و جستجو را از اول شروع کند.**  

    ---

    ### **۸. `compare` - مقایسه بین دو یا چند ملک**  
    ✅ وقتی کاربر می‌خواهد دو یا چند ملک را با هم مقایسه کند، مثلاً:  
    - "ملک اول و دوم رو با هم مقایسه کن"  
    - "اسم های املاکی که میخواد با هم مقایسه کنه رو میگه و میگه مقایسه کن اینارو"
    - "کدوم یکی بهتره، ملک شماره ۲ یا ۳؟"  
    - "بین این دو ملک، کدوم مناسب‌تره؟"  
    ---

    ### **۹. `purchase` - خرید ملک**  
    ✅ وقتی کاربر **می‌خواهد ملکی را بخرد** و نام ملک رو هم میگوید، مثلاً:  
    - "می‌خوام این ملک رو بخرم"  
    - "چطوری میتونم واحدی در Onda by Kasco بخرم؟"  
    - "شرایط خرید ملک Onda by Kasco چیه؟"  
    - "قیمت نهایی با تخفیف برای این ملک چقدره؟"  
    ---

    ### **۱۰. `budget_search` - جستجو منطقه**
    ✅ وقتی کاربر **به دنبال مناطقی است که متناسب با بودجه‌اش باشند و سوال میپرسه که با بودجه مشخص منطقه معرفی کن و اگر فقط قیمت گفت این حالت رو انتخاب نکن**، مثلاً:
    - "توی چه منطقه‌ای می‌تونم با ۱ میلیون درهم خانه دو خوابه بخرم؟"
    - "کجا آپارتمان یک‌خوابه زیر ۲ میلیون درهم پیدا می‌کنم؟"
    - "بهترین مناطق برای خرید ویلا با بودجه ۵ میلیون درهم کجا هستند؟"

    🚨 **این حالت را انتخاب نکن اگر:**
    - کاربر قبلاً جستجوی ملک انجام داده و فقط بودجه را اضافه کرده است. (در این صورت `search` را انتخاب کن.)

    🚨 **این حالت را انتخاب نکن اگر کاربر مستقیماً درخواست جستجوی ملک داده باشد (در این صورت `search` را انتخاب کن).** 
    ---

    ### **۱۱. `search_no_bedroom` - جستجوی ملک بدون توجه به تعداد اتاق خواب**  
    ✅ وقتی کاربر **به‌طور خاص می‌گوید "فرقی ندارد"، "مهم نیست"، "هر چقدر باشه اوکیه"** در مورد تعداد اتاق خواب،  

    🚨 **در این حالت، مقدار `bedrooms` را `null` قرار بده و در خروجی JSON نوع پیام را `search` بگذار.**  

    ---

    **🔹 قوانین تشخیص بین حالت 'purchase' و 'details':**  
    ✅ اگر کاربر از عباراتی مانند **"می‌خوام بخرم"**، **"چطور بخرم؟"**، **"برای خرید این ملک راهنمایی کن"**، یا اسم ملک و به همراه خرید میگه، نوع پیام را `purchase` قرار بده.  
    ✅ اگر کاربر فقط اطلاعات بیشتری در مورد **امکانات، قیمت یا ویژگی‌های ملک** خواست، نوع پیام را `details` قرار بده.  


    ### **⏳ مهم:**  
    اگر پیام کاربر **نامشخص** بود یا **ممکن بود چند دسته را شامل شود**، **قبل از تصمیم‌گیری، بیشتر بررسی کن و عجله نکن.**  
    اگر پیام قبلی کاربر ** search **بوده و الان اطلاعات تکمیلی داده برام حالت رو همان قرار بده
    ** اگر نوع پیام قبلی کاربر budget_search بود در پیام جدید search قرار بده**
    - اگر تاریخ تحویل در پیام داده شده حالت را 'search' قرار بده


    **اگر کاربر درباره جزئیات یک ملک سوال کرده باشد، نوع اطلاعاتی که می‌خواهد مشخص کن:**  
    - `price`: قیمت ملک  
    - `features`: امکانات ملک  
    - `location`: موقعیت جغرافیایی ملک  
    - `payment`: شرایط پرداخت ملک 

    اگر کاربر از عبارات "همین ملک"، "ملک فعلی"، یا "اسم ملک" استفاده کرده باشد، تشخیص دهید که به ملک آخرین معرفی‌شده اشاره دارد.


    ** اگر پیام مربوط به درخواست جستجوی ملک است، بررسی کن آیا کاربر جزئیات قبلی (مانند منطقه، قیمت و نوع ملک) را تغییر داده یا یک درخواست جدید داده است.**


    **خروجی فقط یک JSON شامل دو مقدار باشد:**  
    - `"type"`: یکی از گزینه‌های `search`, `market`, `buying_guide`, `details`, `more`, `unknown`  
    - `"detail_requested"`: اگر `details` باشد، مقدار `price`, `features`, `location`, `payment` باشد، وگرنه مقدار `null` باشد.
    - `"reset"`: `true` اگر کاربر درخواست ریست داده باشد، و `false` در غیر این صورت.

    """

    ai_response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": prompt}],
        max_tokens=50
    )

    # ✅ استخراج پاسخ هوش مصنوعی
    response_content = ai_response.choices[0].message.content.strip()
    print(f"🔍 پاسخ OpenAI: {response_content}")

    try:
        if response_content.startswith("```json"):
            response_content = response_content.replace("```json", "").replace("```", "").strip()

        # ✅ حالا مقدار پردازش شده را نمایش می‌دهیم
        print(f"✅ پاسخ OpenAI بعد از پردازش: {response_content}")

        # ✅ تبدیل به JSON
        parsed_response = json.loads(response_content)

    except json.JSONDecodeError:
        return "متوجه نشدم که به دنبال چه چیزی هستید. لطفاً واضح‌تر بگویید که دنبال ملک هستید یا اطلاعات بیشتری درباره ملکی می‌خواهید."

    response_type = parsed_response.get("type", "unknown")
    detail_requested = parsed_response.get("detail_requested", None)
    reset_requested = parsed_response.get("reset", False)

    print(f"🔹 نوع درخواست: {response_type}, جزئیات درخواستی: {detail_requested}, ریست: {reset_requested}")
    # type_search = response_type
    memory_state["previous_type"] = response_type

    if reset_requested:
        print("🔄 کاربر درخواست ریست داده است. پاک‌سازی حافظه...")
        memory_state.clear()  # 🚀 حافظه را ریست کن
        return "✅ اطلاعات قبلی حذف شد. لطفاً بگویید که دنبال چه ملکی هستید. 😊"

    if "market" in response_type.lower():
        return await fetch_real_estate_trends(user_message)

    # ✅ **۳. تشخیص درخواست اطلاعات بیشتر درباره املاک قبلاً معرفی‌شده**
    if "details" in response_type.lower():
        # ✅ استخراج شماره یا نام ملک از پیام کاربر
        property_id = await extract_property_identifier(user_message, property_name_to_id)
        print(f"📌 مقدار property_identifier استخراج‌شده: {property_id}")

        global last_property_id
        if property_id is None:
            if last_property_id is not None:
                property_id = last_property_id  # استفاده از ملک قبلی
                print(f"ℹ️ استفاده از آخرین ملک پرسیده‌شده: {property_id}")
            else:
                return "❌ لطفاً شماره یا نام ملک را مشخص کنید."

        # ✅ ذخیره این ملک به عنوان آخرین ملکی که درباره‌اش سوال شده است
        last_property_id = property_id

        return generate_ai_details(property_id, detail_type=detail_requested)

    if "compare" in response_type.lower():
        return await compare_properties(user_message)

    if "purchase" in response_type.lower():
        detail_requested = None  # مقدار detail_requested را خالی کن
        return await process_purchase_request(user_message)

    if "budget_search" in response_type.lower():
        extracted_data = extract_filters(user_message, memory_state)
        memory_state.update(extracted_data)
        max_price = extracted_data.get("max_price")
        min_price = extracted_data.get("min_price")
        apartment_typ = extracted_data.get("apartmentType")
        bedrooms = extracted_data.get("bedrooms")

        if max_price is None:
            return "❌ لطفاً بودجه خود را مشخص کنید."

        return find_districts_by_budget(max_price, bedrooms, apartment_typ, min_price)

    if "more" in response_type.lower():
        return await generate_ai_summary(last_properties_list, start_index=current_property_index)

    if "buying_guide" in response_type.lower():
        return await fetch_real_estate_buying_guide(user_message)

    # ✅ **۵. اگر درخواست جستجوی ملک است، فیلترها را استخراج کرده و ملک پیشنهاد بده**
    if "search" in response_type.lower():
        print("✅ تابع extract_filters در حال اجرا است...")
        print("🔹 memory", memory_state)

        extracted_data = extract_filters(user_message, memory_state)

        if "questions_needed" in extracted_data and len(extracted_data["questions_needed"]) > 0:
            # print("❓ اطلاعات ناقص است، سوالات لازم: ", extracted_data["questions_needed"])

            # 🚀 ذخیره فقط `bedrooms`, `max_price`, `district` در `memory_state`
            essential_keys = ["bedrooms", "max_price", "district"]
            for key in essential_keys:
                if extracted_data.get(key) is not None:
                    memory_state[key] = extracted_data[key]  # مقدار جدید را ذخیره کن

            print("✅ اطلاعات ضروری از extracted_data در memory_state ذخیره شد:", memory_state)

            return "❓ " + "، ".join(extracted_data["questions_needed"])

        # بررسی مقدار `extracted_data`
        print("🔹 داده‌های استخراج‌شده از پیام کاربر:", extracted_data)

        if not extracted_data:
            return "❌ OpenAI نتوانست اطلاعاتی را از پیام شما استخراج کند."

        memory_state.update(extracted_data)

        filters = {}
        filters_date = {}

        if extracted_data.get("city"):
            filters["city"] = extracted_data.get("city")

        if extracted_data.get("district"):
            district_i = str(extracted_data["district"]).strip().title()  # مقدار را به رشته تبدیل کن

            district_mapping = {
                'Masdar City': 340, 'Meydan': 133, 'Wadi AlSafa 2': 146, 'Wadi AlSafa 5': 246, 'Alamerah': 279,
                'JVC': 243, 'Remraam': 284, 'Aljadaf': 122, 'Liwan': 294, 'Arjan': 201, 'Dubai Creek Harbour': 152,
                'Damac Lagoons': 259, 'Dubai Downtown': 143, 'Muwaileh': 304, 'Palm Jumeirah': 134, 'Business Bay': 252,
                'City Walk': 228, 'Emaar South': 354, 'Dubai Production City': 217, 'Nadd Al Shiba': 355,
                'Dubai Hills': 241,
                'Jabal Ali Industrial Second': 131, 'AlYelayiss 2': 162, 'Town Square Dubai': 275, 'Majan': 231,
                'Ramhan Island': 315,
                'AlKifaf': 167, 'Alyasmeen': 310, 'Sports City': 203, 'Mbr District One': 319, 'Alraha': 352,
                'Damac Hills 2': 213,
                'Wadi AlSafa 4': 189, 'Expo City': 292, 'Almarjan Island': 297, 'Zaabeel Second': 120,
                'Yas Island': 303,
                'Zayed City': 295, 'Port Rashid': 378, 'Alhamra Island': 278, 'Jabal Ali First': 130,
                'Dubai Land Residence Complex': 307,
                'Reem Island': 298, 'Dubai Investment Park': 156, 'The Oasis': 363, 'Alheliow1': 311,
                'Dubai South': 328, 'The Valley': 361,
                'JVT': 244, 'Rashid Yachts and Marina': 383, 'Golf City': 266, 'Jebel Ali Village': 345,
                'Alhudayriyat Island': 365,
                'Damac Hills': 210, 'Alzorah': 364, 'Alfurjan': 346, 'Discovery Gardens': 235, 'Dubai Islands': 233,
                'Alsatwa': 273,
                'Dubai Motor City': 124, 'Palm Jabal Ali': 161, 'Saadiyat Island': 296, 'Dubai Marina': 239,
                'Dubai Industrial City': 308,
                'Mina Alarab': 293, 'Sobha Hartland': 332, 'Alwasl': 141, 'Bluewaters Bay': 286, 'JLT': 212,
                'World Islands': 247,
                'Mirdif': 163, 'Jumeirah Island One': 150, 'City Of Arabia': 236, 'Alreem Island': 264, 'Almaryah': 337,
                'Albarsha South': 341, 'Aljada': 327, 'International City Phase (2)': 309, 'Alshamkha': 362,
                'Ghaf Woods': 389,
                'Hamriya West': 353, 'Al Yelayiss 1': 397, 'Al Tay': 343, 'Studio City': 316, 'Maryam Island': 314,
                'Rukan Community': 414,
                'Madinat Jumeirah Living': 285, 'Dubai Maritime City': 216, 'Wadi Al Safa 7': 261, 'Alzahya': 312,
                'Jumeirah Park': 317,
                'Bukadra': 349, 'Alsafouh Second': 407, 'Dubai Sports City': 342, 'Al Barsha South Second': 409,
                'Mohammed Bin Rashid City': 318,
                'Jumeirah 2': 334, 'Uptown, AlThanyah Fifth': 220, 'Wadi AlSafa 3': 187, 'Jumeirah Heights': 402,
                'Dubai Silicon Oasis': 245,
                'Dubai Design District': 230, 'Tilal AlGhaf': 199, 'Albelaida': 280, 'Jumeirah Beach Residence': 375,
                'Dubai International Financial Centre (DIFC)': 333,
                'Dubai Water Canal': 387, 'Al Barsha 1': 400, 'Alwadi Desert': 406, 'Jumeirah Golf Estates': 291,
                'Warsan Fourth': 249,
                'Meydan D11': 404, 'Nad Alsheba 1': 413, 'Aljurf': 359, 'MBR City D11': 368, 'International City': 248,
                'Alrashidiya 1': 386, 'Free Zone': 367, 'Dubai Internet City': 398, 'Khalifa City': 357,
                'Ghantoot': 358,
                'Alnuaimia 1': 392, 'Alhamriyah': 415, 'Barsha Heights': 385, 'Ajmal Makan City': 276,
                'Motor City': 326,
                'Legends': 412, 'Sharm': 374, 'AlSafouh First': 125, 'Barashi': 305, 'Al Maryah Island': 399,
                'Jumeirah Garden City': 356,
                'Dubai Investment Park 2': 366, 'Sheikh Zayed Road, Alsafa': 263, 'Dubai Land': 417,
                'Madinat Almataar': 250,
                'Emaar Beachfront': 391, 'Dubai Harbour': 242, 'Alheliow2': 313, 'Alsuyoh Suburb': 324, 'Tilal': 325,
                'Almuntazah': 339, 'Alrashidiya 3': 321, 'Alsafa': 268, 'Almamzar': 306, 'Sobha Hartland 2': 408,
                'Siniya Island': 360,
                'Ras AlKhor Ind. First': 257, 'Albarari': 418, 'Alwaha': 416, 'Dubai Science Park': 351,
                'Ain Al Fayda': 369,
                'Marina': 336, 'Dubai Healthcare City': 238, 'Trade Center First': 148, 'Damac Islands': 394,
                'The Heights Country Club': 396, 'Al Yelayiss 5': 411, 'Hayat Islands': 283,
                'Mina AlArab, Hayat Islands': 282,
                'Dubai Media City': 258, 'Al Khalidiya': 382, 'AlBarsha South Fourth': 301, 'Alrahmaniya': 390,
                'AlBarsha South Fifth': 123,
                "AlFaqa'": 329, 'Raha Island': 347

            }

            best_match, score = process.extractOne(district_i, district_mapping.keys())
            print(f"📌 بهترین تطابق fuzzy: {best_match} (امتیاز: {score})")  # نمایش اطلاعات برای دیباگ

            if score > 70:  # **اگر دقت بالای ۷۰٪ بود، مقدار را قبول کن**
                filters["district"] = best_match  # ✅ **ذخیره نام منطقه به جای ID**
            else:
                filters["district"] = district_i  # اگر تطابق نداشت، همان مقدار ورودی کاربر را نگه دار

            # if score > 70:  # اگر دقت بالای ۷۰٪ بود، مقدار را قبول کن
            #     filters["district"] = [district_mapping[best_match]]
            # else:
            #     print(f"⚠️ نام منطقه '{district_i}' به هیچ منطقه‌ای تطابق نداشت!")

        if extracted_data.get("bedrooms") is not None:
            bedrooms_count = str(extracted_data["bedrooms"]).strip().title()  # مقدار را به رشته تبدیل کن

            bedrooms_mapping = {
                "1": 10,
                "1.5": 23,
                "2": 11,
                "2.5": 24,
                "3": 12,
                "3.5": 25,
                "4": 13,
                "4.5": 26,
                "5": 14,
                "5.5": 27,
                "6": 15,
                "6.5": 28,
                "7": 16,
                "7.5": 29,
                "8": 17,
                "9": 18,
                "10": 19,
                "11": 22,
                "Studio": 9,
                "Penthouse": 34,
                "Retail": 31,
                "Office": 20,
                "Showroom": 35,
                "Store": 30,
                "Suite": 32,
                "Hotel Room": 33,
                "Full Floor": 36,
                "Land / Plot": 21
            }

            # مقدار `property_type` را به `id` تغییر بده
            filters["apartments"] = [bedrooms_mapping.get(bedrooms_count, bedrooms_count)]

        if extracted_data.get("max_price") is not None:
            filters["max_price"] = extracted_data.get("max_price")

        if extracted_data.get("min_price") is not None:
            filters["min_price"] = extracted_data.get("min_price")

        # if extracted_data.get("bathrooms") is not None:
        #     filters["bathrooms"] = extracted_data.get("bathrooms")

        if extracted_data.get("min_area") is not None:
            filters["min_area"] = extracted_data.get("min_area")

        if extracted_data.get("max_area") is not None:
            filters["max_area"] = extracted_data.get("max_area")

        if extracted_data.get("property_type") is not None:
            property_type_name = extracted_data.get("property_type")

            if isinstance(property_type_name, dict):
                property_type_name = property_type_name.get("name", "")

            # تبدیل نام انگلیسی به ID
            property_type_mapping = {
                "Residential": {"id": 20, "name": "Residential"},
                "Commercial": {"id": 3, "name": "Commercial"}
            }

            # مقدار `property_type` را به `id` تغییر بده
            filters["property_type"] = property_type_mapping.get(property_type_name, property_type_name)

        # if extracted_data.get("property_type"):
        #     filters["property_type"] = extracted_data.get("property_type")

        if extracted_data.get("apartmentType") is not None:
            apartment_type = str(extracted_data["apartmentType"]).strip().title()  # تبدیل به فرمت استاندارد
            # ✅ دیکشنری نگاشت نوع آپارتمان به `id`
            apartment_type_mapping = {
                "Apartment": 1,
                "Building": 31,
                "Duplex": 27,
                "Full Floor": 4,
                "Hotel": 32,
                "Hotel Apartment": 8,
                "Land / Plot": 6,
                "Loft": 34,
                "Office": 7,
                "Penthouse": 10,
                "Retail": 33,
                "Shop": 29,
                "Show Room": 30,
                "Store": 25,
                "Suite": 35,
                "Townhouse": 9,
                "Triplex": 28,
                "Villa": 3,
                "Warehouse": 26
            }

            # ✅ تبدیل مقدار `property_type` به `id` معادل آن
            filters["apartmentTypes"] = [apartment_type_mapping.get(apartment_type, apartment_type)]

        # ✅ اضافه کردن `delivery_date`
        if extracted_data.get("delivery_date") is not None:
            try:
                user_date = extracted_data["delivery_date"].strip()

                # استخراج فقط سال از فرمت YYYY-MM
                match = re.match(r"^(\d{4})-(\d{2})$", user_date)
                if match:
                    year = match.group(1)  # فقط سال را بگیر
                    filters_date["delivery_date"] = int(year)  # ذخیره فقط سال
                elif len(user_date) == 4 and user_date.isdigit():  # اگر فقط سال داده شده باشد
                    filters_date["delivery_date"] = int(user_date)  # ذخیره فقط سال
                else:
                    print("❌ فرمت تاریخ نامعتبر است! مقدار را نادیده می‌گیریم.")
                    filters_date["delivery_date"] = None

            except Exception as e:
                print(f"❌ خطا در پردازش تاریخ: {e}")
                filters_date["delivery_date"] = None

                # ✅ اضافه کردن `payment_plan`
        if extracted_data.get("payment_plan") is not None:
            value = str(extracted_data["payment_plan"]).lower()  # تبدیل مقدار به رشته و کوچک کردن حروف
            if value == "yes" or value == "1":  # اگر مقدار yes یا 1 بود
                filters["payment_plan"] = 1
            elif value == "no" or value == "0":  # اگر مقدار no یا 0 بود
                filters["payment_plan"] = 0

        # ✅ اضافه کردن `post_delivery`
        if extracted_data.get("post_delivery") is not None:
            value = str(extracted_data["post_delivery"]).lower()  # تبدیل مقدار به رشته و کوچک کردن حروف
            if value == "yes" or value == "1":  # اگر مقدار yes یا 1 بود
                filters["post_delivery"] = 1
            elif value == "no" or value == "0":  # اگر مقدار no یا 0 بود
                filters["post_delivery"] = 0

        if extracted_data.get("guarantee_rental_guarantee") is not None:
            value = str(extracted_data["guarantee_rental_guarantee"]).lower()  # تبدیل مقدار به رشته و کوچک کردن حروف
            if value == "yes" or value == "1":  # اگر مقدار yes یا 1 بود
                filters["guarantee_rental_guarantee"] = 1
            elif value == "no" or value == "0":  # اگر مقدار no یا 0 بود
                filters["guarantee_rental_guarantee"] = 0

        # ✅ اضافه کردن `developer_company_id`
        if extracted_data.get("developer_company") is not None:
            developer_list = extracted_data["developer_company"]  # دریافت نام شرکت توسعه‌دهنده

            # **بررسی و تبدیل `developer_company` به لیست در صورت نیاز**
            if isinstance(developer_list, str):
                developer_list = [developer_list]  # تبدیل رشته به لیست تک‌عضوی

            developer_mapping = {
                'Burtville Developments': 330, 'Ellington Properties': 50, 'Sobha': 3, 'Tiger Properties': 103,
                'Azizi': 37, 'GJ Properties': 326, 'Green Group': 346, 'Meraas': 70, 'Dubai Properties': 258,
                'Confident Group': 308, 'Iman Developers': 61, 'EMAAR': 2, 'Damac': 318, 'Shapoorji Pallonji': 91,
                'Arada Properties': 35, 'Omniyat': 77, 'Oro24': 241, 'Prestige One': 80, 'Deyaar': 45,
                'Select Group': 85,
                'Nshama': 76, 'Marquis Point': 274, 'Arenco Real Estate': 398, 'Rijas Aces Property': 233,
                'Eagle Hills': 299,
                'Wasl': 109, 'London Gate': 264, 'Nakheel': 74, 'Reportage': 232, 'GFH': 60, 'Expo City': 54,
                'AYS Developments': 36,
                'Imtiaz': 87, 'Park Group': 366, 'Almazaya Holding': 68, 'Samana Developers': 83, 'Aldar': 32,
                'Bloom Holding': 270,
                'AG Properties': 317, 'Swank Development': 393, 'Binghatti': 38, 'Divine One Group': 311,
                'Emirates properties': 267,
                'Dubai South': 323, 'Pearlshire Developments': 329, 'Gulf Land': 239, 'Radiant': 269,
                'Modon Properties': 394,
                'Alzorah Development': 383, 'Algouta Properties': 380, 'Majid Al Futtaim Group': 111, 'HMB': 247,
                'Naseeb Group': 265,
                'Amwaj Development': 348, 'Condor Group': 41, 'Grid properties': 296, 'Enso Development': 403,
                'Aqua Properties': 34,
                'SRG Holding': 95, 'Dugasta': 276, 'Roya Lifestyle Developments': 338, 'Meteora': 278,
                'Aqasa Developers': 333,
                'Zimaya Properties': 392, 'Citi Developers': 283, 'Amali Properties': 341, 'Dubai Invesment': 254,
                'Credo': 324,
                'AAF Development': 409, 'Saas Properties': 300, 'Object 1': 237, 'Meraki Developers': 71,
                'Dalands Developer': 427,
                'Taraf': 100, 'The Heart of Europe': 101, 'HRE Development': 399, 'Lootah': 65,
                'AJ Gargash Real Estate': 465,
                'Sol Properties': 94, 'Townx Real Estate': 105, 'Ajmal Makan': 260, 'Symbolic': 97,
                'Mashriq Elite': 332,
                'Nabni developments': 294, 'Danube Properties': 42, 'IFA Hotels & Resorts': 486, 'Q Properties': 408,
                'ARAS Real Estate': 293, 'East & West Properties': 49, 'Amaya Properties LLC': 413, 'H&H': 315,
                'Laya': 238,
                'Leos': 240, 'Pure Gold': 256, 'Empire Development': 52, 'KASCO Development': 433,
                'Swiss Properties': 96,
                'Beyond': 443, 'Rabdan': 289, 'Esnad Management': 421, 'Durar': 320, 'Signature D T': 203,
                'ABA Group': 336,
                'Luxe Developer': 327, 'Vincitore': 108, 'Uniestate Properties': 107, 'Avelon Developments': 287,
                'Rokane': 417,
                'Orange': 303, 'Iraz Developments': 335, 'Aqaar': 305, 'Keymavens development': 345,
                'Peak Summit Real Estate Development': 350,
                'Baraka Development': 304, 'LMD Real Estate': 227, 'Arista Properties': 321, 'Ginco Properties': 374,
                'Lacasa Living': 477, 'Wow Resorts': 405, 'Aark Developers': 26, 'Pantheon Development': 78,
                'DV8 Developers': 423,
                "Mada'in": 154, 'Mubadala': 468, 'Lucky Aeon': 66, 'Meydan': 422, 'Anax Developments': 301,
                'Shoumous': 261,
                'Five Holdings': 56, 'Acube Developments': 309, 'World Of Wonders': 291, 'Palladium Development': 356,
                'Skyline Builders': 285, "Khamas Group Of Investment Co's": 363, 'Baccarat': 370,
                'Metac Properties L.L.C': 23,
                'Riviera Group': 298, 'MAG': 242, 'Kingdom Properties': 456, 'MeDoRe': 255, 'Revolution': 342,
                'BNH Real Estate Developer': 429,
                'Esnaad': 302, 'Takmeel Real Estate': 314, 'Mered': 288, 'Emerald Palace Group': 51,
                'RAK Properties': 245,
                'Fortune 5': 58, 'Siadah International Real Estate': 406, 'Peace Homes Development': 250,
                'BnW Developments': 382,
                'Tuscany Real Estate Development': 396, 'One Development': 425, 'AHS Properties': 319,
                'ARIB Developments': 389,
                'Alseeb Real Estate Development': 442, 'Tarrad Real Estate': 451, 'Stamn Development': 440,
                'Vantage Properties': 469,
                'Range Developments': 479, 'Zane Development': 481, 'Alta Real Estate Development': 491,
                'Qube Development': 354,
                'Green Yard Properties': 412, 'MGS Development': 353, 'Mira Developments': 282,
                'True Future Development': 495,
                'Sama Ezdan': 205, 'AiZN Development': 404, 'Wellington Developments': 497, 'Ohana Developments': 369,
                'Heilbronn Properties': 339, 'Seven Tides': 89, 'Kamdar developments': 470, 'IGO': 259,
                'Ahmadyar Developments': 375,
                'Karma': 62, 'Imkan': 371, 'LAPIS Properties': 419, 'S&S Real Estate': 499, 'Fakhruddin Properties': 55,
                'Saba Property Developers': 416, 'Majid Developments': 401, 'JRP Development': 410, 'DarGlobal': 44,
                'HVM Living': 484, 'Segrex': 284, 'Mr. Eight Development': 430, 'Golden Wood': 407,
                'EL Prime Properties': 431,
                'Wellcube.life': 395, 'Mubarak Al Beshara Real Estate Development': 420, 'Source of Fate': 434,
                'Dar Alkarama': 43,
                'Palma Holding': 340, 'Shurooq Development': 435, 'Vakson Real Estate': 358,
                'Tasmeer Indigo Properties': 352,
                'AB Developers': 367, 'Alzarooni Development': 444, 'Amaal': 498, 'Wahat Al Zaweya': 397, 'Galaxy': 379,
                'MS Homes': 376, 'MAK Developers': 415, 'City View Developments': 391, 'Reef Luxury Development': 424,
                'Blanco Thornton Properties': 402, 'ADE Properties': 446, 'IRTH': 372, 'Forum Real Estate': 387,
                'Nine Yards Development': 494, 'One Yard': 200, 'AAA Development': 441, 'Nine Development': 411,
                'vision developments': 390, 'Alef Group': 273, 'Svarn': 368, 'Valores': 480,
                'Crystal Bay Development': 377,
            }

            if isinstance(developer_list, list):  # بررسی اینکه ورودی یک لیست باشد
                mapped_developers = []

                for developer in developer_list:
                    best_match, score = process.extractOne(developer.strip(), developer_mapping.keys())

                    if score > 70:  # **فقط اگر دقت بالای ۷۰٪ بود، مقدار را قبول کن**
                        mapped_developers.append(developer_mapping[best_match])

                if mapped_developers:  # **اگر شرکت‌هایی پیدا شدند، به `filters` اضافه شود**
                    filters["developer_company_id"] = mapped_developers

        # ✅ اضافه کردن `facilities` (لیست امکانات)
        if extracted_data.get("facilities_name") is not None:
            facilities_list = extracted_data["facilities_name"]  # دریافت امکانات از `extracted_data`

            # **بررسی و تبدیل `facilities` به لیست در صورت نیاز**
            if isinstance(facilities_list, str):
                facilities_list = [facilities_list]  # تبدیل رشته به لیست تک‌عضوی

            facilities_mapping = {
                "24 hour security": "408",
                "24/7 Security and Maintenance Services": "399",
                "Access Control System": "314",
                "Air Fitness zones": "570",
                "Art Garden": "510",
                "BBQ Area": "21",
                "Baby Care Centre": "163",
                "Badminton Court": "100",
                "Balcony": "76",
                "Basketball Court": "427",
                "Basketball Playground": "10",
                "Beach": "387",
                "Beach Club": "595",
                "Beauty Saloon": "106",
                "Bicycle parking": "348",
                "Bike Paths": "52",
                "Bike tracks": "458",
                "Bocce Play Area": "525",
                "Broadband Internet": "46",
                "Building Management System": "325",
                "Business Centre": "175",
                "CCTV Surveillance": "313",
                "Cabana Seating": "88",
                "Cafe": "184",
                "Central A/C & Heating": "47",
                "Changing Room and Locker": "533",
                "Chess Board": "97",
                "Children's Play Area": "6",
                "Children's Swimming Pool": "7",
                "Cinema": "19",
                "Clinic": "279",
                "Close Circuit TV System": "323",
                "Club House": "226",
                "Co-Working Spaces": "221",
                "Community hubs": "460",
                "Concierge Service": "37",
                "Covered Parking": "31",
                "Cricket Pitch": "95",
                "Cycling Track": "276",
                "Direct Beach Access": "96",
                "Dog Park": "363",
                "Electric Vehicle Charging Stations": "229",
                "Fitness Area": "424",
                "Fitness Club": "50",
                "Fitness studio": "397",
                "Football Playground": "9",
                "Games Lounge Room": "269",
                "Garden": "11",
                "Gym": "334",
                "Gymnasium": "454",
                "Health Club": "102",
                "Hospital": "368",
                "Jogging Track": "105",
                "Kids Pool": "381",
                "Kids Swimming Pool": "452",
                "Laundry Room": "107",
                "Library": "87",
                "Mall": "111",
                "Meeting Rooms": "369",
                "Mini Golf": "96",
                "Mosque": "204",
                "Music Room": "268",
                "Nursery": "217",
                "Outdoor Gym": "26",
                "Padel Tennis": "467",
                "Park": "54",
                "Parking": "405",
                "Pet Shop": "281",
                "Pharmacy": "57",
                "Play Area": "425",
                "Playground": "319",
                "Pool Deck": "415",
                "Private Cinema For Each Unit": "364",
                "Private Parking for Each unit": "484",
                "Security": "40",
                "SPA": "43",
                "Sauna": "13",
                "Sauna & Steam Room": "144",
                "School": "49",
                "Shared Outdoor Swimming Pool": "20",
                "Skate Park": "428",
                "Smart Homes": "378",
                "Squash Courts": "209",
                "Supermarket": "56",
                "Swimming Pool": "74",
                "Tennis Playground": "8",
                "Theater": "19",
                "VR Game Room": "382",
                "Water Fountain": "356",
                "Veterinary Clinic": "280",
                "Yoga": "167",
                "Zen Garden": "511",
                "Kids Club": "331",
                "Safe & Secure": "529"
            }

            if isinstance(facilities_list, list):  # بررسی اینکه ورودی یک لیست باشد
                mapped_facilities = []

                for facility in facilities_list:
                    best_match, score = process.extractOne(facility.strip(), facilities_mapping.keys())

                    if score > 70:  # **فقط اگر دقت بالای ۷۰٪ بود، مقدار را قبول کن**
                        mapped_facilities.append(facilities_mapping[best_match])

                if mapped_facilities:  # **اگر امکاناتی پیدا شد، به `filters` اضافه شود**
                    filters["facilities"] = mapped_facilities

        filters["property_status"] = 'Off Plan'
        # filters["property_status"] = [2]
        filters["sales_status"] = [1]
        # filters["sales_status"] = 'Available'
        # filters["apartments"] = [12]

        print("🔹 فیلترهای اصلاح‌شده و ارسال‌شده به API:", filters)
        memory_state = filters.copy()

        if "delivery_date" in memory_state:
            del memory_state["delivery_date"]

        properties = filter_properties(memory_state)

        # ✅ فیلتر `delivery_date` (تحویل ملک) فقط بر اساس سال
        if filters_date.get("delivery_date"):
            target_year = filters_date["delivery_date"]  # سال موردنظر کاربر
            start_of_year = int(datetime(target_year, 1, 1).timestamp())  # تبدیل به یونیکس (ژانویه)
            end_of_year = int(datetime(target_year, 12, 31, 23, 59, 59).timestamp())  # تبدیل به یونیکس (دسامبر)

            properties = [
                prop for prop in properties
                if "delivery_date" in prop and prop["delivery_date"].isdigit() and
                   start_of_year <= int(prop["delivery_date"]) <= end_of_year
            ]

            print(f"🔍 بعد از فیلتر بر اساس سال تحویل ({target_year}): {len(properties)}")

        if "delivery_date" in filters_date:
            memory_state["delivery_date"] = f"{target_year}-01"

        if "bedrooms" in extracted_data:
            memory_state["bedrooms"] = extracted_data.get("bedrooms")

        if "developer_company" in extracted_data:
            memory_state["developer_company"] = extracted_data.get("developer_company")

        if "facilities_name" in extracted_data:
            memory_state["facilities_name"] = extracted_data.get("facilities_name")

        print("🔹 memory:", memory_state)

        print(f"🔹 تعداد املاک دریافت‌شده از API: {len(properties)}")
        # print(properties[:3])

        # response = generate_ai_summary(properties)
        response = await generate_ai_summary(properties)

        return response

    # ✅ **۶. اگر درخواست ناشناخته بود**
    return "متوجه نشدم که به دنبال چه چیزی هستید. لطفاً واضح‌تر بگویید که دنبال ملک هستید یا اطلاعات بیشتری درباره ملکی می‌خواهید."


# ✅ مسیر API برای چت‌بات
@app.post("/chat")
async def chat(request: ChatRequest):
    user_message = request.message.strip()

    # ✅ **۱. اگر چت‌بات برای اولین بار باز شود، پیام خوش‌آمدگویی ارسال کند**
    if not user_message:
        welcome_message = """
        👋 **به چت‌بات مشاور املاک شرکت ترونست خوش آمدید!**  
        من اینجا هستم تا به شما در پیدا کردن **بهترین املاک در دبی** کمک کنم. 🏡✨  

        **چطور می‌توانم کمکتان کنم؟**  
        """
        return {"response": welcome_message}

    """ دریافت پیام کاربر و ارسال پاسخ از طریق هوش مصنوعی """
    bot_response = await real_estate_chatbot(request.message)
    return {"response": bot_response}


from fastapi.responses import FileResponse
import os


@app.get("/")
async def serve_home():
    return FileResponse(os.path.join(os.getcwd(), "index.html"))


# ✅ اجرای FastAPI
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

# "Authorization": f"Bearer {ESTATY_API_KEY}"