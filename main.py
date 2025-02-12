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

cache = TTLCache(maxsize=100, ttl=600)

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
client = openai.OpenAI(api_key=api_key)


# ESTATY_API_KEY = 'g46s5rt87SDG874s4872sd4b6a'
ESTATY_API_KEY = os.getenv("ESTATY_API_KEY")
ESTATY_API_URL = "https://panel.estaty.app/api/v1"


# ✅ Define headers for authentication
HEADERS = {
    "App-Key": ESTATY_API_KEY,
    "Content-Type": "application/json"
}

import random
memory_state = {}
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
        if property.get("sales_status", {}).get("name", "").lower() in ["available", "pre launch"]
        and (district_filter is None or (property.get("district") and property["district"].get("name", "").lower() == district_filter))
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
    - اگر `district`, `city`, یا `property_type` جدیدی داده شده که با مقدار قبلی **فرق دارد**، مقدار `"new_search"` را `true` تنظیم کن.
    - 🚨 **اگر کلمه "منطقه" بدون ذکر نام خاصی آمده باشد (مثل "همین منطقه")، مقدار `district` را تغییر نده و `new_search` را `false` بگذار.**  
    - **اگر کاربر از کلماتی مانند "قیمت بالاتر"، "گرون‌تر"، "بالای X" استفاده کند، مقدار `min_price` را تنظیم کن.**
    - **اگر کاربر از کلماتی مانند "قیمت پایین‌تر"، "ارزون‌تر"، "زیر X" استفاده کند، مقدار `max_price` را تنظیم کن .**
    - 🚨 اگر `min_price` مقدار جدیدی دارد، ولی `max_price` در پیام جدید ذکر نشده، مقدار `max_price` را **حتماً حذف کن** (حتی اگر مقدار قبلی وجود داشته باشد).
    - 🚨 اگر `max_price` مقدار جدیدی دارد، ولی `min_price` در پیام جدید ذکر نشده، مقدار `min_price` را **حتماً حذف کن** (حتی اگر مقدار قبلی وجود داشته باشد).
    - اگر `min_price` و `max_price` جدید داده نشده، مقدار قبلی را نگه دار.


    خروجی باید یک شیء JSON باشد که شامل فیلدهای زیر باشد:
    - "new_search": true | false, 
    - "city" (مثلاً "Dubai")
    - "district" (اگر ذکر شده، مانند "JVC")
    - "property_type" (مثلاً "آپارتمان"، "ویلا"، "پنت‌هاوس")
    - "max_price" (اگر اشاره شده)
    - "min_price" (اگر اشاره شده)
    - "bedrooms" (اگر مشخص شده)
    - "bathrooms" (اگر مشخص شده)
    - "area_min" (اگر ذکر شده)
    - "area_max" (اگر ذکر شده)
    - "furnished" (اگر اشاره شده، مقدار true یا false)
    - "status" (مثلاً "جدید"، "آف پلن"، "آماده تحویل")



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
        
        if extracted_data.get("new_search"):
            previous_filters.clear()  # **✅ ریست `memory_state`**

        print("🔹 خروجی در تابع:",extracted_data)

        # ✅ بررسی تغییر مقدار `min_price` و `max_price`
        if extracted_data.get("min_price") is not None and extracted_data.get("max_price") is None:
            extracted_data["max_price"] = None  

        if extracted_data.get("max_price") is not None and extracted_data.get("min_price") is None:
            extracted_data["min_price"] = None  

        if extracted_data.get("district") is None:
            extracted_data["district"] = previous_filters.get("district")

        # for key, value in previous_filters.items():
        #         if extracted_data.get(key) is None:
        #             extracted_data[key] = value



        
        # if previous_filters:
        #     # بررسی تغییر مقدار `min_price`
        #     # if extracted_data.get("min_price") is not None:
        #     #     if "max_price" in previous_filters and extracted_data.get("max_price") is None:
        #     #         extracted_data["max_price"] = None  # حذف `max_price`

        #     # # بررسی تغییر مقدار `max_price`
        #     # if extracted_data.get("max_price") is not None:
        #     #     if "min_price" in previous_filters and extracted_data.get("min_price") is None:
        #     #         extracted_data["min_price"] = None  # حذف `min_price`

        #     if extracted_data.get("min_price") is not None and extracted_data.get("max_price") is None:
        #         extracted_data["max_price"] = None  

        #     # اگر فقط `max_price` تغییر کرده باشد، `min_price` را حذف کن
        #     if extracted_data.get("max_price") is not None and extracted_data.get("min_price") is None:
        #         extracted_data["min_price"] = None  

        #     # اگر کاربر مقدار جدیدی برای `min_price` و `max_price` داده، مقدار قبلی را جایگزین کن
        #     if extracted_data.get("min_price") is not None and extracted_data.get("max_price") is not None:
        #         extracted_data["min_price"] = extracted_data["min_price"]
        #         extracted_data["max_price"] = extracted_data["max_price"]

        #     if extracted_data.get("district") is None:  # اگر منطقه جدیدی ذکر نشده باشد
        #         extracted_data["district"] = previous_filters.get("district")  # مقدار قبلی را نگه‌دار

        #     for key, value in previous_filters.items():
        #             if extracted_data.get(key) is None:
        #                 extracted_data[key] = value  


        # ✅ پردازش رشته JSON به یک دیکشنری
        return extracted_data

    except json.JSONDecodeError as e:
        print("❌ JSON Decode Error:", e)
        return {}

    except Exception as e:
        print("❌ Unexpected Error:", e)
        return {}




def generate_ai_summary(properties, start_index=0):
    """ ارائه خلاصه کوتاه از املاک پیشنهادی """

    global last_properties_list, current_property_index
    number_property = 1

    if not properties:
        return "متأسفانه هیچ ملکی با این مشخصات پیدا نشد. لطفاً بازه قیمتی را تغییر دهید یا منطقه دیگری انتخاب کنید."

    # ✅ ذخیره املاک و ایندکس جدید برای مشاهده موارد بیشتر
    last_properties_list = properties
    current_property_index = start_index + number_property

    # ✅ انتخاب ۳ ملک بعدی
    selected_properties = properties[start_index:current_property_index]
    

    if not selected_properties:
        return "✅ تمامی املاک نمایش داده شده‌اند و مورد جدیدی موجود نیست."

    # ✅ پرامپت برای خلاصه‌سازی املاک
    prompt = f"""
    شما یک مشاور املاک در دبی هستید. کاربران به دنبال خرید ملک در دبی هستند. 
    لطفاً خلاصه‌ای کوتاه و جذاب از این املاک ارائه دهید تا کاربر بتواند راحت‌تر انتخاب کند:

    {json.dumps(selected_properties, ensure_ascii=False, indent=2)}


    اطلاعاتی که می‌توان به صورت خلاصه ارائه داد شامل:
    - **آی‌دی ملک** (برای بررسی دقیق‌تر)
    - نام ملک (به انگلیسی)
    - معرفی کلی ملک  
    - موقعیت جغرافیایی  
    - وضعیت فروش (آماده تحویل / در حال ساخت / فروخته شده)
    - قیمت و متراژ
    - لینک مشاهده اطلاعات کامل ملک در سایت رسمی **[سایت Trunest](https://www.trunest.ae/property/{selected_properties[0]['id']})**
    

    **لحن شما باید حرفه‌ای، صمیمی و کمک‌کننده باشد، مثل یک مشاور املاک واقعی که به مشتری توضیح می‌دهد.**

    **قوانین پاسخ:**
    - هر ملک را در 5 تا 6 جمله خلاصه کنید.
    - قیمت، متراژ، موقعیت مکانی و یک ویژگی کلیدی را ذکر کنید.
    - در انتهای پیام بگویید که کاربر می‌تواند برای جزئیات بیشتر شماره ملک را وارد کند (مثلاً: 'ملک ۲').
    - اگر کاربر بخواهد املاک بیشتری ببیند، بگویید که می‌تواند درخواست "املاک دیگه رو نشونم بده" کند.
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": prompt}]
    )

    return response.choices[0].message.content


# ✅ تابع ارائه اطلاعات تکمیلی یک ملک خاص
def generate_ai_details(property_number, detail_type=None):
    """ ارائه اطلاعات تکمیلی یک ملک خاص یا بخشی خاص از آن """

    if not last_properties_list or property_number < 1 or property_number > len(last_properties_list):
        return "❌ لطفاً شماره ملک را به‌درستی وارد کنید. مثال: 'ملک ۲'"

    selected_property = last_properties_list[property_number - 1]
    property_id = selected_property.get("id")
    last_selected_property = selected_property

    detailed_info = fetch_single_property(property_id)

    combined_info = {**selected_property, **detailed_info}
    combined_info["property_url"] = f"https://www.trunest.ae/property/{property_id}"

    # ✅ در صورتی که کاربر درخواست جزئیات خاصی کرده باشد
    if detail_type:
        prompt = f"""
        شما یک مشاور املاک در دبی هستید. کاربران می‌خواهند اطلاعات بیشتری درباره بخش خاصی از این ملک بدانند.

        اطلاعات ملک:
        {json.dumps(combined_info, ensure_ascii=False, indent=2)}

        **جزئیاتی که کاربر درخواست کرده:** {detail_type}

        لطفاً فقط اطلاعات مربوط به این بخش را به‌صورت حرفه‌ای، دقیق و کمک‌کننده ارائه دهید.
        """

    else:
        # ✅ پرامپت برای توضیح تکمیلی کلی ملک
        prompt = f"""
        شما یک مشاور املاک در دبی هستید. لطفاً اطلاعات زیر را به‌فارسی روان و طبیعی به صورت حرفه‌ای، دقیق و کمک‌کننده ارائه دهید:


        {json.dumps(combined_info, ensure_ascii=False, indent=2)}

        لحن شما باید حرفه‌ای، دوستانه و کمک‌کننده باشد. اطلاعاتی که می‌توان ارائه داد شامل:
        - **آی‌دی ملک** (برای بررسی دقیق‌تر)
        - نام ملک (به انگلیسی)
        - معرفی کلی ملک و دلیل پیشنهاد آن
        - موقعیت جغرافیایی و دسترسی‌ها
        - وضعیت فروش (آماده تحویل / در حال ساخت / فروخته شده)
        - قیمت و متراژ
        - امکانات برجسته
        - وضعیت ساخت و شرایط پرداخت
        - لینک مشاهده اطلاعات کامل ملک در سایت رسمی
        """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": prompt}]
    )

    return response.choices[0].message.content



async def real_estate_chatbot(user_message: str) -> str:
    """ بررسی نوع پیام و ارائه پاسخ مناسب با تشخیص هوشمند """

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
    کاربر در حال مکالمه با یک مشاور املاک در دبی است. پیام زیر را تجزیه و تحلیل کن:

    "{user_message}"


     آیا این پیام یکی از موارد زیر است؟

    - `search`: درخواست کلی برای جستجوی ملک (مثلاً: "خانه می‌خوام"، "یه ملک معرفی کن")
    - `details`: درخواست اطلاعات بیشتر درباره‌ی یکی از املاک قبلاً معرفی‌شده (مثلاً: "همین ملک را توضیح بده"، "درباره ملک ۲ توضیح بده"، "قیمت ملک ۱ چقدره؟"، "امکانات ملک ۲"، "قیمت ملک ۱ چقدره؟")
    - `more`: درخواست نمایش املاک بیشتر (مثلاً: "ملکای دیگه رو نشونم بده"،"ملک دیگه ای نشون بده"، "موردای بیشتری دارین؟")
    - `search`: درخواست کلی برای جستجوی ملک (مثلاً: "خانه می‌خوام"، "یه ملک معرفی کن")
    - `unknown`: نامشخص


    **اگر کاربر درباره جزئیات یک ملک سوال کرده باشد، نوع اطلاعاتی که می‌خواهد مشخص کن:**  
    - `price`: قیمت ملک  
    - `features`: امکانات ملک  
    - `location`: موقعیت جغرافیایی ملک  
    - `payment`: شرایط پرداخت ملک 

    اگر کاربر از عبارات "همین ملک"، "ملک فعلی"، یا "اسم ملک" استفاده کرده باشد، تشخیص دهید که به ملک آخرین معرفی‌شده اشاره دارد.


    ** اگر پیام مربوط به درخواست جستجوی ملک است، بررسی کن آیا کاربر جزئیات قبلی (مانند منطقه، قیمت و نوع ملک) را تغییر داده یا یک درخواست جدید داده است.**


    **خروجی فقط یک JSON شامل دو مقدار باشد:**  
    - `"type"`: یکی از گزینه‌های `search`, `details`, `more`, `unknown`  
    - `"detail_requested"`: اگر `details` باشد، مقدار `price`, `features`, `location`, `payment` باشد، وگرنه مقدار `null` باشد.

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

    print(f"🔹 نوع درخواست: {response_type}, جزئیات درخواستی: {detail_requested}")

    # ✅ **۳. تشخیص درخواست اطلاعات بیشتر درباره املاک قبلاً معرفی‌شده**
    if "details" in response_type.lower():
        # اگر کاربر عددی برای شماره ملک مشخص کرده باشد
        words = user_message.split()
        property_number = None
        for word in words:
            if word.isdigit():
                property_number = int(word)
                break

        # اگر شماره ملک مشخص نشده باشد، فرض بر این است که کاربر آخرین ملک معرفی‌شده را می‌خواهد
        if property_number is None and last_properties_list:
            property_number = 1  # اولین ملک از لیست آخرین ملک‌های معرفی‌شده

        if property_number is None:
            return "❌ لطفاً شماره ملک را مشخص کنید. مثال: 'امکانات ملک ۲ را بگو'."

        return generate_ai_details(property_number, detail_type=detail_requested)
    
    
    if "more" in response_type.lower():
        return generate_ai_summary(last_properties_list, start_index=current_property_index)
    

    
    # ✅ **۵. اگر درخواست جستجوی ملک است، فیلترها را استخراج کرده و ملک پیشنهاد بده**
    if "search" in response_type.lower():
        print("✅ تابع extract_filters در حال اجرا است...")
        extracted_data = extract_filters(user_message, memory_state)


    # ✅ بررسی آیا یک جستجوی کاملاً جدید است
        if extracted_data.get("new_search"):
            memory_state.clear()  # **✅ ریست `memory_state`**
        # بررسی مقدار `extracted_data`
        print("🔹 داده‌های استخراج‌شده از پیام کاربر:", extracted_data)

        if not extracted_data:
            return "❌ OpenAI نتوانست اطلاعاتی را از پیام شما استخراج کند."


        # if memory_state:
        #     for key in memory_state.keys():
        #         if key not in extracted_data or extracted_data[key] is None:
        #             extracted_data[key] = memory_state[key]


        # has_min_price = "min_price" in extracted_data and extracted_data["min_price"] is not None
        # has_max_price = "max_price" in extracted_data and extracted_data["max_price"] is not None

        # if has_min_price and not has_max_price:
        #     extracted_data["max_price"] = None  # اگر فقط `min_price` مشخص شده بود، `max_price` را پاک کن

        # if has_max_price and not has_min_price:
        #     extracted_data["min_price"] = None  # اگر فقط `max_price` مشخص شده بود، `min_price` را پاک کن


        # **به‌روزرسانی حافظه با اطلاعات جدید**
        # memory_state = extracted_data.copy()

        filters = {}

        if extracted_data.get("city"):
            filters["city"] = extracted_data.get("city")

        if extracted_data.get("district"):
            filters["district"] = extracted_data.get("district")

        if extracted_data.get("bedrooms") is not None:
            filters["bedrooms"] = extracted_data.get("bedrooms")

        if extracted_data.get("max_price") is not None:
            filters["max_price"] = extracted_data.get("max_price")

        if extracted_data.get("min_price") is not None:
            filters["min_price"] = extracted_data.get("min_price")

        if extracted_data.get("property_type"):
            filters["property_type"] = extracted_data.get("property_type")

        filters["property_status"] = ["Off Plan"]

        print("🔹 فیلترهای اصلاح‌شده و ارسال‌شده به API:", filters)
        memory_state = filters.copy()

        properties = filter_properties(memory_state)

        print(f"🔹 تعداد املاک دریافت‌شده از API: {len(properties)}")

        response = generate_ai_summary(properties)

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


# ✅ اجرای FastAPI
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)




# ####

# # ✅ تابع اصلی چت‌بات
# async def real_estate_chatbot(user_message: str) -> str:
#     """ بررسی نوع پیام و ارائه پاسخ مناسب """

#     global last_properties_list, current_property_index

#     # ✅ **۱. تشخیص اینکه پیام فقط یک سلام است یا سوالی در مورد ملک**
#     greetings = ["سلام", "سلام خوبی؟", "سلام چطوری؟", "سلام وقت بخیر", "سلام روزت بخیر"]
#     if user_message.strip() in greetings:
#         return random.choice([
#             "سلام! من اینجا هستم که به شما در خرید ملک کمک کنم 😊 اگر سوالی در مورد املاک دارید، بفرمایید.",
#             "سلام دوست عزیز! به چت‌بات مشاور املاک خوش آمدید. چطور می‌توانم کمکتان کنم؟ 🏡",
#             "سلام! اگر به دنبال خرید یا سرمایه‌گذاری در املاک دبی هستید، من راهنمای شما هستم!",
#         ])
    

#     # ✅ بررسی اینکه آیا کاربر شماره ملک را درخواست کرده است
#     if user_message.startswith("ملک"):
#         try:
#             property_number = int(user_message.split()[1])
#             return generate_ai_details(property_number)
#         except (IndexError, ValueError):
#             return "❌ لطفاً شماره ملک را به‌درستی وارد کنید. مثال: 'ملک ۲'"

#     # ✅ بررسی اگر کاربر جزئیات خاصی را درخواست کرده است
#     for keyword in ["قیمت", "امکانات", "شرایط پرداخت", "موقعیت"]:
#         if keyword in user_message:
#             words = user_message.split()
#             try:
#                 property_number = int(words[words.index(keyword) - 1])
#                 return generate_ai_details(property_number, detail_type=keyword)
#             except (IndexError, ValueError):
#                 return "❌ لطفاً شماره ملک را به‌درستی وارد کنید. مثال: 'هزینه ملک ۲'"

#     # ✅ بررسی درخواست نمایش املاک بیشتر
#     if "ملکای دیگه رو نشونم بده" in user_message:
#         return generate_ai_summary(last_properties_list, start_index=current_property_index)


#     """ جستجو و ارائه پیشنهادات املاک به صورت توضیح طبیعی با هوش مصنوعی """
#     extracted_data = extract_filters(user_message)

#     # ✅ بررسی مقدار `extracted_data`
#     print("🔹 داده‌های استخراج‌شده از پیام کاربر:", extracted_data)

#     if not extracted_data:
#         return "❌ OpenAI نتوانست اطلاعاتی را از پیام شما استخراج کند."

#     filters = {}

#     if extracted_data.get("city"):
#         filters["city"] = extracted_data.get("city")

#     if extracted_data.get("district"):
#         filters["district"] = extracted_data.get("district")

#     if extracted_data.get("bedrooms") is not None:
#         filters["bedrooms"] = extracted_data.get("bedrooms")

#     if extracted_data.get("max_price") is not None:
#         filters["max_price"] = extracted_data.get("max_price")

#     if extracted_data.get("min_price") is not None:
#         filters["min_price"] = extracted_data.get("min_price")

#     if extracted_data.get("property_type"):
#         filters["property_type"] = extracted_data.get("property_type")

#     filters["property_status"] = ["Off Plan"]
#     # filters["sales_status"] = ["Available"]

#     print("🔹 فیلترهای اصلاح‌شده و ارسال‌شده به API:", filters)


#     properties = filter_properties(filters)

#     print(f"🔹 تعداد املاک دریافت‌شده از API: {len(properties)}")

#     response = generate_ai_summary(properties)

#     return response


######## حالت قبل


# # ✅ استفاده از هوش مصنوعی برای تولید پاسخ‌های انسانی به زبان فارسی
# def generate_ai_response(properties):
#     """ استفاده از هوش مصنوعی برای توضیح املاک به فارسی """
#     if not properties:
#         return "متأسفانه هیچ ملکی با این مشخصات پیدا نشد. لطفاً بازه قیمتی را تغییر دهید یا منطقه دیگری انتخاب کنید"

#     # random.shuffle(properties)
#     # انتخاب ۳ ملک برتر برای توضیح
#     top_properties = properties[:1]
#     # time.sleep(60)
#     ####
#     detailed_properties = []

#     for prop in top_properties:
#         property_id = prop.get("id")
#         detailed_info = fetch_single_property(property_id)  # دریافت اطلاعات تکمیلی ملک

#         # **ترکیب اطلاعات کلی و جزئی**
#         combined_info = {**prop, **detailed_info}  # ادغام داده‌ها
#         combined_info["property_url"] = f"https://www.trunest.ae/property/{property_id}"  # افزودن لینک ملک
        
#         detailed_properties.append(combined_info)

#     ####

#     # تولید توضیحات
#     prompt = f"""
#     شما یک مشاور املاک در دبی هستید. لطفاً این املاک را به فارسی روان و طبیعی توضیح دهید:

#     {json.dumps(detailed_properties, ensure_ascii=False, indent=2)}

#     لحن شما باید حرفه‌ای، دوستانه و کمک‌کننده باشد. اطلاعاتی که می‌توان ارائه داد شامل:
#     - **آی‌دی ملک** (برای بررسی دقیق‌تر)
#     - نام ملک (به انگلیسی)
#     - معرفی کلی ملک و دلیل پیشنهاد آن
#     - موقعیت جغرافیایی و دسترسی‌ها
#     - وضعیت فروش (آماده تحویل / در حال ساخت / فروخته شده)
#     - قیمت و متراژ
#     - امکانات برجسته
#     - وضعیت ساخت و شرایط پرداخت
#     - لینک مشاهده اطلاعات کامل ملک در سایت رسمی
    

#     **لحن شما باید حرفه‌ای، صمیمی و کمک‌کننده باشد، مثل یک مشاور املاک واقعی که به مشتری توضیح می‌دهد.**
#     """
#     response = client.chat.completions.create(
#         model="gpt-4o-mini",
#         messages=[{"role": "system", "content": prompt}]
#         )

#     return response.choices[0].message.content



# def generate_detailed_ai_response(properties):
#     """ استفاده از هوش مصنوعی برای توضیح املاک به فارسی """
#     if not properties:
#         return "متأسفانه هیچ ملکی با این مشخصات پیدا نشد. لطفاً بازه قیمتی را تغییر دهید یا منطقه دیگری انتخاب کنید"

#     # random.shuffle(properties)
#     # انتخاب ۳ ملک برتر برای توضیح
#     top_properties = properties[:1]
#     # time.sleep(60)
#     ####
#     detailed_properties = []

#     for prop in top_properties:
#         property_id = prop.get("id")
#         detailed_info = fetch_single_property(property_id)  # دریافت اطلاعات تکمیلی ملک

#         # **ترکیب اطلاعات کلی و جزئی**
#         combined_info = {**prop, **detailed_info}  # ادغام داده‌ها
#         combined_info["property_url"] = f"https://www.trunest.ae/property/{property_id}"  # افزودن لینک ملک
        
#         detailed_properties.append(combined_info)

#     ####

#     # تولید توضیحات
#     prompt = f"""
#     شما یک مشاور املاک در دبی هستید. لطفاً این املاک را به فارسی روان و طبیعی توضیح دهید:

#     {json.dumps(detailed_properties, ensure_ascii=False, indent=2)}

#     لحن شما باید حرفه‌ای، دوستانه و کمک‌کننده باشد. اطلاعاتی که می‌توان ارائه داد شامل:
#     - **آی‌دی ملک** (برای بررسی دقیق‌تر)
#     - نام ملک (به انگلیسی)
#     - معرفی کلی ملک و دلیل پیشنهاد آن
#     - موقعیت جغرافیایی و دسترسی‌ها
#     - وضعیت فروش (آماده تحویل / در حال ساخت / فروخته شده)
#     - قیمت و متراژ
#     - امکانات برجسته
#     - وضعیت ساخت و شرایط پرداخت
#     - لینک مشاهده اطلاعات کامل ملک در سایت رسمی
    

#     **لحن شما باید حرفه‌ای، صمیمی و کمک‌کننده باشد، مثل یک مشاور املاک واقعی که به مشتری توضیح می‌دهد.**
#     """
#     response = client.chat.completions.create(
#         model="gpt-4o-mini",
#         messages=[{"role": "system", "content": prompt}]
#         )

#     return response.choices[0].message.content




# # ✅ تابع اصلی چت‌بات
# async def real_estate_chatbot(user_message: str) -> str:
#     """ بررسی نوع پیام و ارائه پاسخ مناسب """
    
#     # ✅ **۱. تشخیص اینکه پیام فقط یک سلام است یا سوالی در مورد ملک**
#     greetings = ["سلام", "سلام خوبی؟", "سلام چطوری؟", "سلام وقت بخیر", "سلام روزت بخیر"]
#     if user_message.strip() in greetings:
#         return random.choice([
#             "سلام! من اینجا هستم که به شما در خرید ملک کمک کنم 😊 اگر سوالی در مورد املاک دارید، بفرمایید.",
#             "سلام دوست عزیز! به چت‌بات مشاور املاک خوش آمدید. چطور می‌توانم کمکتان کنم؟ 🏡",
#             "سلام! اگر به دنبال خرید یا سرمایه‌گذاری در املاک دبی هستید، من راهنمای شما هستم!",
#         ])


#     more_details_requests = ["جزئیات بیشتر", "می‌خواهم اطلاعات بیشتری بدانم", "توضیح بیشتر بده", "بیشتر توضیح بده"]
#     if any(request in user_message.lower() for request in more_details_requests):
#         return await generate_detailed_ai_response()

#     """ جستجو و ارائه پیشنهادات املاک به صورت توضیح طبیعی با هوش مصنوعی """
#     extracted_data = extract_filters(user_message)

#     # ✅ بررسی مقدار `extracted_data`
#     print("🔹 داده‌های استخراج‌شده از پیام کاربر:", extracted_data)

#     if not extracted_data:
#         return "❌ OpenAI نتوانست اطلاعاتی را از پیام شما استخراج کند."

#     filters = {}

#     if extracted_data.get("city"):
#         filters["city"] = extracted_data.get("city")

#     if extracted_data.get("district"):
#         filters["district"] = extracted_data.get("district")

#     if extracted_data.get("bedrooms") is not None:
#         filters["bedrooms"] = extracted_data.get("bedrooms")

#     if extracted_data.get("max_price") is not None:
#         filters["max_price"] = extracted_data.get("max_price")

#     if extracted_data.get("min_price") is not None:
#         filters["min_price"] = extracted_data.get("min_price")

#     if extracted_data.get("property_type"):
#         filters["property_type"] = extracted_data.get("property_type")

#     filters["property_status"] = ["Off Plan"]
#     # filters["sales_status"] = ["Available"]

#     print("🔹 فیلترهای اصلاح‌شده و ارسال‌شده به API:", filters)


#     # filters = {
        
#     #     "city": extracted_data.get("city"),
#     #     # "district": extracted_data.get("district"),
#     #     "district": extracted_data.get("district"),
#     #     "bedrooms": extracted_data.get("bedrooms"),
#     #     "max_price": extracted_data.get("max_price"),
#     #     "min_price": extracted_data.get("min_price"),
#     #     "property_type": extracted_data.get("property_type"),
#     #     "property_status": ["Off Plan"],  # ✅ فقط املاک در حال ساخت (آف پلن)
#     #     "sales_status": ["Available"]   
#     # }

#     properties = filter_properties(filters)

#     print(f"🔹 تعداد املاک دریافت‌شده از API: {len(properties)}")

#     response = generate_ai_response(properties)

#     return response

# # ✅ مسیر API برای چت‌بات
# @app.post("/chat")
# async def chat(request: ChatRequest):
#     """ دریافت پیام کاربر و ارسال پاسخ از طریق هوش مصنوعی """
#     bot_response = await real_estate_chatbot(request.message)
#     return {"response": bot_response}


# # ✅ اجرای FastAPI
# if __name__ == "__main__":
#     uvicorn.run(app, host="0.0.0.0", port=8000)

#########










# ####   حالت جزییات بدون هوش
# last_suggested_properties = {}  # متغیر سراسری برای ذخیره لیست املاک پیشنهادی

# def generate_ai_response(properties):
#     """ تولید پاسخ کوتاه اولیه برای معرفی چندین ملک """

#     global last_suggested_properties  # استفاده از متغیر سراسری
#     last_suggested_properties.clear()  # هر بار که جستجو انجام می‌شود، لیست قبلی پاک شود

#     if not properties:
#         return "متأسفانه هیچ ملکی با این مشخصات پیدا نشد. لطفاً بازه قیمتی را تغییر دهید یا منطقه دیگری انتخاب کنید."

#     response_text = "**🏡 پیشنهادات املاک مطابق درخواست شما:**\n\n"

#     for index, prop in enumerate(properties[:3], start=1):  # حداکثر ۳ ملک را نمایش دهیم
#         property_id = prop.get("id")
#         last_suggested_properties[str(index)] = property_id  # ذخیره شماره انتخابی و آی‌دی ملک
#         last_suggested_properties[str(property_id)] = property_id  # ذخیره آی‌دی ملک به‌صورت مستقیم

#         response_text += f"""
#         **{index}. {prop['title']}**  
#         📍 **منطقه:** {prop['district']['name']}  
#         💰 **قیمت:** از {prop.get('low_price', 'نامشخص')} درهم  
#         📏 **متراژ:** {prop.get('min_area', 'نامشخص')} متر  
#         🔗 **[مشاهده جزئیات](https://www.trunest.ae/property/{property_id})**  
#         \n
#         """

#     response_text += "لطفاً شماره یا نام ملکی که می‌خواهید اطلاعات بیشتری درباره آن داشته باشید را انتخاب کنید. 🏠"
    
#     return response_text


# async def real_estate_chatbot(user_message: str) -> str:
#     """ بررسی نوع پیام و ارائه پاسخ مناسب """

#     global last_suggested_properties  # استفاده از لیست ذخیره‌شده

#     # ✅ اگر کاربر شماره یا آی‌دی ملکی را وارد کند، اطلاعات آن ملک را برگردانید
#     selected_property_id = last_suggested_properties.get(user_message.strip())
#     if selected_property_id:
#         return await generate_detailed_ai_response(selected_property_id)

#     # ✅ پردازش عادی پیام (جستجوی ملک جدید)
#     extracted_data = extract_filters(user_message)

#     if not extracted_data:
#         return "❌ OpenAI نتوانست اطلاعاتی را از پیام شما استخراج کند."

#     filters = {
#         "city": extracted_data.get("city"),
#         "district": extracted_data.get("district"),
#         "bedrooms": extracted_data.get("bedrooms"),
#         "max_price": extracted_data.get("max_price"),
#         "min_price": extracted_data.get("min_price"),
#         "property_type": extracted_data.get("property_type"),
#         "property_status": ["Off Plan"]
#     }

#     properties = filter_properties(filters)

#     print(f"🔹 تعداد املاک دریافت‌شده از API: {len(properties)}")

#     response = generate_ai_response(properties)

#     return response
# async def generate_detailed_ai_response(property_id):
#     """ تولید پاسخ جامع در صورت درخواست اطلاعات بیشتر درباره یک ملک خاص """
    
#     property_data = fetch_single_property(property_id)

#     if not property_data:
#         return "❌ اطلاعات این ملک در حال حاضر موجود نیست."

#     # ✅ تولید پرامپت جدید برای نمایش اطلاعات کامل ملک
#     prompt = f"""
#     🏡 **{property_data['title']} - {property_data['id']}**  
#     📍 **موقعیت:** {property_data['district']['name']} | 🏗 **تحویل:** {property_data.get('delivery_date', 'نامشخص')}  
#     💰 **قیمت:** از {property_data.get('low_price', 'نامشخص')} درهم | 📏 **متراژ:** {property_data.get('min_area', 'نامشخص')} متر  
#     🎯 **شرایط پرداخت:** {property_data.get('payment_plan', 'نامشخص')}  
#     🔥 **امکانات کامل:** {property_data.get('facilities', 'مشخص نشده')}  
#     📜 **ویژگی‌های خاص:** {property_data.get('special_features', 'مشخص نشده')}  
#     🔗 **[مشاهده اطلاعات کامل در سایت]({property_data['property_url']})**  

#     ✅ **اگر سوال دیگری دارید، من در خدمت شما هستم!**
#     """

#     response = client.chat.completions.create(
#         model="gpt-4o-mini",
#         messages=[{"role": "system", "content": prompt}],
#         max_tokens=500  # محدودیت تعداد توکن برای بهینه‌سازی هزینه
#     )

#     return response.choices[0].message.content
# ####