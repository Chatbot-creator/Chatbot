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
        if property.get("sales_status", {}).get("name", "").lower() in ["available"]
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
    - اگر اسامی مناطق یا نوع property به فارسی نوشته شد اول انگلیسیش کن بعد ذخیره کن


    خروجی باید یک شیء JSON باشد که شامل فیلدهای زیر باشد:
    - "new_search": true | false, 
    - "city" (مثلاً "Dubai")
    - "district" (اگر ذکر شده، مانند "JVC")
    - "property_type" ("مثلاً "مسکونی"، "تجاری")
    - "grouped_apartments" ("مثلاً "آپارتمان"، "ویلا"، "پنت‌هاوس)
    - "max_price" (اگر اشاره شده)
    - "min_price" (اگر اشاره شده)
    - "bedrooms" (اگر مشخص شده)
    - "bathrooms" (اگر مشخص شده)
    - "area_min" (اگر ذکر شده)
    - "area_max" (اگر ذکر شده)
    - "sale_status" ("مثلاً "موجود )


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



        # ✅ پردازش رشته JSON به یک دیکشنری
        return extracted_data

    except json.JSONDecodeError as e:
        print("❌ JSON Decode Error:", e)
        return {}

    except Exception as e:
        print("❌ Unexpected Error:", e)
        return {}

property_name_to_id = {}


def generate_ai_summary(properties, start_index=0):
    """ ارائه خلاصه کوتاه از املاک پیشنهادی """

    global last_properties_list, current_property_index, selected_properties, property_name_to_id
    number_property = 3

    if not properties:
        return "متأسفانه هیچ ملکی با این مشخصات پیدا نشد. لطفاً بازه قیمتی را تغییر دهید یا منطقه دیگری انتخاب کنید."

    # ✅ ذخیره املاک و ایندکس جدید برای مشاهده موارد بیشتر
    last_properties_list = properties
    current_property_index = start_index + number_property

    # ✅ انتخاب ۳ ملک بعدی
    selected_properties = properties[start_index:current_property_index]
    
    print("📌 املاک دریافت‌شده برای نمایش:", selected_properties)
    if not selected_properties:
        return "✅ تمامی املاک نمایش داده شده‌اند و مورد جدیدی موجود نیست."
    

    for prop in selected_properties:
        prop_name = prop.get("title", "").strip().lower()
        prop_id = prop.get("id")

        if prop_name and prop_id:
            property_name_to_id[prop_name] = prop_id

    print("📌 لیست املاک ذخیره‌شده پس از مقداردهی:", property_name_to_id)


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
    - قیمت به درهم و متراژ حتما به فوت مربع
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
        - قیمت به درهم و متراژ حتما به فوت مربع
        - امکانات برجسته
        - وضعیت ساخت و شرایط پرداخت
        - لینک مشاهده اطلاعات کامل ملک در سایت رسمی
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

        with DDGS() as ddgs:
            results = list(ddgs.text(search_query, max_results=5))  # استخراج نتایج

        if not results:
            return "متأسفم، اطلاعاتی درباره این موضوع پیدا نشد."

        # ترکیب اطلاعات برای ارسال به GPT
        search_summary = "\n".join([f"{r['title']}: {r['body']}" for r in results if 'body' in r])

        prompt = f"""
        اطلاعات زیر درباره بازار املاک دبی از منابع مختلف جمع‌آوری شده است. لطفاً یک خلاصه مفید و مختصر از آن به زبان فارسی ارائه بده:

        {search_summary}

        **🔹 خلاصه‌ای کوتاه و مفید در ۳ الی ۴ جمله ارائه بده.**
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

        # ✅ جستجو در اینترنت
        with DDGS() as ddgs:
            results = list(ddgs.text(search_query, max_results=5))
        
        if not results:
            return "متأسفم، اطلاعاتی درباره این موضوع پیدا نشد."

        # ✅ ترکیب اطلاعات جستجو شده
        search_summary = "\n".join([f"{r['title']}: {r['body']}" for r in results if 'body' in r])

        # ✅ ارسال اطلاعات به GPT برای تولید خلاصه فارسی
        response_prompt = f"""
        اطلاعات زیر از منابع معتبر درباره "{user_question}" جمع‌آوری شده است:

        {search_summary}

        **🔹 لطفاً یک پاسخ دقیق، کوتاه و مفید در ۳ الی ۴ جمله به زبان فارسی ارائه بده.**
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
    - اگر عددی ذکر شده (مثلاً ۲)، فقط همان عدد را در خروجی بده.  
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
    کاربر در حال مکالمه با یک مشاور املاک در دبی است. پیام زیر را تجزیه و تحلیل کن:

    "{user_message}"


    **لطفاً مشخص کنید که پیام کاربر به کدام یک از این دسته‌ها تعلق دارد:**


    ### **۱. `search` - درخواست جستجوی ملک**  
    ✅ وقتی کاربر **به دنبال پیدا کردن یک ملک است**، مثلاً:  
    - "خانه‌ای در جمیرا می‌خوام"  
    - "یه آپارتمان با قیمت کمتر از دو میلیون درهم می‌خوام"  
    - "بهترین پروژه‌های سرمایه‌گذاری رو معرفی کن"  

    ❌ **این دسته را انتخاب نکنید اگر کاربر درباره روند خرید ملک در دبی سؤال کرده باشد.**  

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
    ✅ وقتی کاربر **درباره روند خرید ملک، قوانین، ویزا یا مالیات** سؤال می‌کند، مثلاً:  
    - "چطور در دبی خانه بخرم؟"  
    - "آیا خارجی‌ها می‌توانند در دبی ملک بخرند؟"  
    - "شرایط دریافت ویزای سرمایه‌گذاری چیه؟"  
    - "برای خرید ملک تو دبی باید مالیات بدم؟"  

    ❌ **این دسته را انتخاب نکنید اگر کاربر دنبال پیدا کردن یک خانه خاص باشد.**  

    ---

    ### **۶. `unknown` - نامشخص**  
    ✅ اگر پیام کاربر به هیچ‌کدام از موارد بالا مربوط نبود.  

    ---

    ### **⏳ مهم:**  
    اگر پیام کاربر **نامشخص** بود یا **ممکن بود چند دسته را شامل شود**، **قبل از تصمیم‌گیری، بیشتر بررسی کن و عجله نکن.**  


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

    if "market" in response_type.lower():
        return await fetch_real_estate_trends(user_message)

    # ✅ **۳. تشخیص درخواست اطلاعات بیشتر درباره املاک قبلاً معرفی‌شده**
    if "details" in response_type.lower():
    # ✅ استخراج شماره یا نام ملک از پیام کاربر
        property_id = await extract_property_identifier(user_message, property_name_to_id)
        print(f"📌 مقدار property_identifier استخراج‌شده: {property_id}")

        if property_id is None:
            return "❌ لطفاً شماره یا نام ملک را مشخص کنید."

        return generate_ai_details(property_id, detail_type=detail_requested)

    
    
    if "more" in response_type.lower():
        return generate_ai_summary(last_properties_list, start_index=current_property_index)
    
    if "buying_guide" in response_type.lower():
        return await fetch_real_estate_buying_guide(user_message)

    
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

        if extracted_data.get("bathrooms") is not None:
            filters["bathrooms"] = extracted_data.get("bathrooms")

        if extracted_data.get("area_min") is not None:
            filters["area_min"] = extracted_data.get("area_min")

        if extracted_data.get("area_max") is not None:
            filters["area_max"] = extracted_data.get("area_max")

        if extracted_data.get("property_type") is not None:
            property_type_name = extracted_data.get("property_type")

            # تبدیل نام انگلیسی به ID
            property_type_mapping = {
                "Residential": {"id": 20, "name": "Residential"},
                "Commercial": {"id": 3, "name": "Commercial"}
            }

            # مقدار `property_type` را به `id` تغییر بده
            filters["property_type"] = property_type_mapping.get(property_type_name, property_type_name)

        # if extracted_data.get("property_type"):
        #     filters["property_type"] = extracted_data.get("property_type")

        if extracted_data.get("grouped_apartments") is not None:
            filters["grouped_apartments"] = extracted_data.get("grouped_apartments")

        filters["property_status"] = 'Off Plan'
        filters["sale_status"] = 'Available'

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


from fastapi.responses import FileResponse
import os

@app.get("/")
async def serve_home():
    return FileResponse(os.path.join(os.getcwd(), "index.html"))


# ✅ اجرای FastAPI
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

