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
import logging
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi.responses import JSONResponse

# logging.basicConfig(
#     level=logging.INFO,  # می‌تونی DEBUG یا WARNING هم بذاری
#     format='%(asctime)s - %(levelname)s - %(message)s',
#     handlers=[
#         logging.FileHandler("app.log"),  # ذخیره تو فایل
#         logging.StreamHandler()          # نمایش تو کنسول
#     ]
# )



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

# کش با زمان انقضای 24 ساعت (86400 ثانیه)
property_cache = TTLCache(maxsize=1, ttl=86400)
def fetch_all_properties():
    print("🚀 شروع دریافت املاک از API...")
    all_properties = []
    page = 1
    limit = 100

    while True:
        print(f"📄 در حال پردازش صفحه {page}...")
        res = requests.post(f"{ESTATY_API_URL}/getProperties", json={"page": page, "limit": limit}, headers=HEADERS)
        json_data = res.json()

        current_data = json_data.get("properties", {}).get("data", [])
        if not current_data:
            break

        all_properties.extend(current_data)

        total = json_data.get("properties", {}).get("total", 0)
        if len(current_data) < 12:
            print("✅ به آخر لیست رسیدیم.")
            break
        # if page * limit >= total:
        #     print("✅ به آخر لیست رسیدیم.")
        #     break

        page += 1

    print(f"✅ Total fetched properties: {len(all_properties)}")
    return all_properties

def fetch_and_cache_properties():
    all_props = fetch_all_properties()
    property_cache["all"] = all_props
    print(f"🕓 Property cache updated at {datetime.now()}")
    print(f"✅ {len(all_props)} ملک ذخیره شد.")


scheduler = BackgroundScheduler()


def start_scheduler():
    scheduler.add_job(fetch_and_cache_properties, "interval", hours=24)
    scheduler.start()
    print("📅 Scheduler every 24h started.")

from contextlib import asynccontextmanager
@asynccontextmanager
async def lifespan(app: FastAPI):
    fetch_and_cache_properties() 
    start_scheduler()
    yield

app = FastAPI(lifespan=lifespan)

@app.get("/all-properties")
def get_cached_properties():
    data = property_cache.get("all")
    if data is None:
        return JSONResponse(content={"detail": "No data cached yet."}, status_code=404)
    return {"properties": data, "count": len(data)}



#----------------------------------------------------------------------Bot
import random
memory_state = {}
types = {}
memory_district = {}
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
# app = FastAPI()

# ✅ مدل دریافت پیام از کاربر
class ChatRequest(BaseModel):
    message: str

# ✅ استخراج فیلترهای جستجو از پیام کاربر
def extract_filters(user_message: str, previous_filters: dict):
    """ استفاده از GPT-4 برای استخراج اطلاعات کلیدی از پیام کاربر """
    district_mapping = {
            'Masdar City': 340, 'Meydan': 133, 'Wadi AlSafa 2': 146, 'Wadi AlSafa 5': 246, 'Alamerah': 279,
            'JVC': 243, 'Remraam': 284, 'Aljadaf': 122, 'Liwan': 294, 'Arjan': 201, 'Dubai Creek Harbour': 152,
            'Damac Lagoons': 259, 'Dubai Downtown': 143, 'Muwaileh': 304, 'Palm Jumeirah': 134, 'Business Bay': 252,
            'City Walk': 228, 'Emaar South': 354, 'Dubai Production City': 217, 'Nadd Al Shiba': 355, 'Dubai Hills': 241,
            'Jabal Ali Industrial Second': 131, 'AlYelayiss 2': 162, 'Town Square Dubai': 275, 'Majan': 231, 'Ramhan Island': 315,
            'AlKifaf': 167, 'Alyasmeen': 310, 'Sports City': 203, 'Mbr District One': 319, 'Alraha': 352, 'Damac Hills 2': 213,
            'Wadi AlSafa 4': 189, 'Expo City': 292, 'Almarjan Island': 297, 'Zaabeel Second': 120, 'Yas Island': 303,
            'Zayed City': 295, 'Port Rashid': 378, 'Alhamra Island': 278, 'Jabal Ali First': 130, 'Dubai Land Residence Complex': 307,
            'Reem Island': 298, 'Dubai Investment Park': 156, 'The Oasis': 363, 'Alheliow1': 311, 'Dubai South': 328, 'The Valley': 361,
            'JVT': 244, 'Rashid Yachts and Marina': 383, 'Golf City': 266, 'Jebel Ali Village': 345, 'Alhudayriyat Island': 365,
            'Damac Hills': 210, 'Alzorah': 364, 'Alfurjan': 346, 'Discovery Gardens': 235, 'Dubai Islands': 233, 'Alsatwa': 273,
            'Dubai Motor City': 124, 'Palm Jabal Ali': 161, 'Saadiyat Island': 296, 'Dubai Marina': 239, 'Dubai Industrial City': 308,
            'Mina Alarab': 293, 'Sobha Hartland': 332, 'Alwasl': 141, 'Bluewaters Bay': 286, 'JLT': 212, 'World Islands': 247,
            'Mirdif': 163, 'Jumeirah Island One': 150, 'City Of Arabia': 236, 'Alreem Island': 264, 'Almaryah': 337,
            'Albarsha South': 341, 'Aljada': 327, 'International City Phase (2)': 309, 'Alshamkha': 362, 'Ghaf Woods': 389,
            'Hamriya West': 353, 'Al Yelayiss 1': 397, 'Al Tay': 343, 'Studio City': 316, 'Maryam Island': 314, 'Rukan Community': 414,
            'Madinat Jumeirah Living': 285, 'Dubai Maritime City': 216, 'Wadi Al Safa 7': 261, 'Alzahya': 312, 'Jumeirah Park': 317,
            'Bukadra': 349, 'Alsafouh Second': 407, 'Dubai Sports City': 342, 'Al Barsha South Second': 409, 'Mohammed Bin Rashid City': 318,
            'Jumeirah 2': 334, 'Uptown, AlThanyah Fifth': 220, 'Wadi AlSafa 3': 187, 'Jumeirah Heights': 402, 'Dubai Silicon Oasis': 245,
            'Dubai Design District': 230, 'Tilal AlGhaf': 199, 'Albelaida': 280, 'Jumeirah Beach Residence': 375, 'Dubai International Financial Centre (DIFC)': 333,
            'Dubai Water Canal': 387, 'Al Barsha 1': 400, 'Alwadi Desert': 406, 'Jumeirah Golf Estates': 291, 'Warsan Fourth': 249,
            'Meydan D11': 404, 'Nad Alsheba 1': 413, 'Aljurf': 359, 'MBR City D11': 368, 'International City': 248,
            'Alrashidiya 1': 386, 'Free Zone': 367, 'Dubai Internet City': 398, 'Khalifa City': 357, 'Ghantoot': 358,
            'Alnuaimia 1': 392, 'Alhamriyah': 415, 'Barsha Heights': 385, 'Ajmal Makan City': 276, 'Motor City': 326,
            'Legends': 412, 'Sharm': 374, 'AlSafouh First': 125, 'Barashi': 305, 'Al Maryah Island': 399, 'Jumeirah Garden City': 356,
            'Dubai Investment Park 2': 366, 'Sheikh Zayed Road, Alsafa': 263, 'Dubai Land': 417, 'Madinat Almataar': 250,
            'Emaar Beachfront': 391, 'Dubai Harbour': 242, 'Alheliow2': 313, 'Alsuyoh Suburb': 324, 'Tilal': 325,
            'Almuntazah': 339, 'Alrashidiya 3': 321, 'Alsafa': 268, 'Almamzar': 306, 'Sobha Hartland 2': 408, 'Siniya Island': 360,
            'Ras AlKhor Ind. First': 257, 'Albarari': 418, 'Alwaha': 416, 'Dubai Science Park': 351, 'Ain Al Fayda': 369,
            'Marina': 336, 'Dubai Healthcare City': 238, 'Trade Center First': 148, 'Damac Islands': 394,
            'The Heights Country Club': 396, 'Al Yelayiss 5': 411, 'Hayat Islands': 283, 'Mina AlArab, Hayat Islands': 282,
            'Dubai Media City': 258, 'Al Khalidiya': 382, 'AlBarsha South Fourth': 301, 'Alrahmaniya': 390, 'AlBarsha South Fifth': 123,
            "AlFaqa'": 329, 'Raha Island': 347
            
        }
    
    developer_mapping = {
        "Burtville Developments": 330, "Sobha": 3, "Tiger Properties": 103, "Azizi": 37, "Meraas": 70,
        "Dubai Properties": 258, "Confident Group": 308, "Iman Developers": 61, "EMAAR": 2, "Shapoorji Pallonji": 91,
        "Arada Properties": 35, "Ellington Properties": 50, "Select Group": 85, "Nshama": 76, "Arenco Real Estate": 398,
        "Rijas Aces Property": 233, "Wasl": 109, "London Gate": 264, "Nakheel": 74, "GFH": 60,
        "Expo City": 54, "AYS Developments": 36, "Imtiaz": 87, "Park Group": 366, "Prestige One": 80,
        "Almazaya Holding": 68, "Samana Developers": 83, "Aldar": 32, "Bloom Holding": 270, "AG Properties": 317,
        "Swank Development": 393, "Binghatti": 38, "Divine One Group": 311, "Emirates properties": 267,
        "Dubai South": 323, "Pearlshire Developments": 329, "Gulf Land": 239, "Radiant": 269, "Modon Properties": 394,
        "Oro24": 241, "Alzorah Development": 383, "Algouta Properties": 380, "Naseeb Group": 265, "GJ Properties": 326,
        "Amwaj Development": 348, "Grid properties": 296, "Aqua Properties": 34, "SRG Holding": 95,
        "Roya Lifestyle Developments": 338, "Omniyat": 77, "Aqasa Developers": 333, "Zimaya Properties": 392,
        "Amali Properties": 341, "Credo": 324, "AAF Development": 409, "Dalands Developer": 427,
        "The Heart of Europe": 101, "HRE Development": 399, "Lootah": 65, "AJ Gargash Real Estate": 465, "Damac": 318,
        "Townx Real Estate": 105, "Symbolic": 97, "Nabni developments": 294, "Deyaar": 45, "Citi Developers": 283,
        "Mashriq Elite": 332, "IFA Hotels & Resorts": 486, "Q Properties": 408, "ARAS Real Estate": 293,
        "East & West Properties": 49, "H&H": 315, "Laya": 238, "Leos": 240, "Reportage": 232, "Empire Development": 52,
        "Object 1": 237, "KASCO Development": 433, "Esnad Management": 421, "Majid Al Futtaim Group": 111,
        "Signature D T": 203, "Sol Properties": 94, "Luxe Developer": 327, "Dugasta": 276, "Avelon Developments": 287,
        "Rokane": 417, "LMD Real Estate": 227, "Source of Fate": 434, "Vision developments": 390,
        "Peace Homes Development": 250, "JRP Development": 410, "MAG": 242, "Riviera Group": 298, "Durar": 320,
        "Meraki Developers": 71, "Uniestate Properties": 107, "Eagle Hills": 299, "IRTH": 372,
        "Amaya Properties LLC": 413, "Ajmal Makan": 260, "Siroya Ventures Realty L.L.C": 445, "HMB": 247,
        "Enso Development": 403, "Marquis Point": 274, "Meteora": 278, "Vincitore": 108, "Taraf": 100,
        "ADE Properties": 446, "Baccarat": 370, "Condor Group": 41, "Rabdan": 289, "Pure Gold": 256,
        "Saas Properties": 300, "Dubai Invesment": 254, "Swiss Properties": 96, "Beyond": 443, "Green Group": 346,
        "Mubadala": 468, "Main Realty": 334, "Danube Properties": 42, "Ambs Real Estate": 360, "MeDoRe": 255,
        "Heilbronn Properties": 339, "Maaia Developments": 517, "Ginco Properties": 374, "Qube Development": 354,
        "Orange": 303, "Alseeb Real Estate Development": 442, "Peak Summit Real Estate Development": 350,
        "Regent Developers": 501, "Mr. Eight Development": 430, "BnW Developments": 382, "Tuscany Real Estate Development": 396,
        "RAK Properties": 245, "Siadah International Real Estate": 406, "One Development": 425, "AHS Properties": 319,
        "ARIB Developments": 389, "Segrex": 284, "DIFC": 502, "DarGlobal": 44, "Fortune 5": 58,
        "Green Yard Properties": 412, "Ahmadyar Developments": 375, "Sankari Properties": 310, "Alta Real Estate Development": 491,
        "Sama Ezdan": 205, "Stamn Development": 440, "Kamdar developments": 470, "BT Properties": 507, "IGO": 259,
        "Orra Real Estate": 204, "Five Holdings": 56, "Karma": 62, "Almarwan Developments": 458,
        "Khamas Group Of Investment Co's": 363, "Imkan": 371, "LAPIS Properties": 419, "Liv Developers": 64,
        "S&S Real Estate": 499, "Fakhruddin Properties": 55, "Saba Property Developers": 416, "Majid Developments": 401,
        "HVM Living": 484, "Golden Wood": 407, "EL Prime Properties": 431, "Wellcube.life": 395,
        "Mubarak Al Beshara Real Estate Development": 420, "Dar Alkarama": 43, "Palma Holding": 340,
        "Vantage Properties": 469, "Shurooq Development": 435, "Vakson Real Estate": 358, "Tasmeer Indigo Properties": 352,
        "Acube Developments": 309, "Mada'in": 154, "Anax Developments": 301, "API": 455, "Alhamra": 351,
        "AB Developers": 367, "Tarrad Real Estate": 451, "Esnaad": 302, "4 Direction Developers": 508,
        "Alzarooni Development": 444, "Alma Developments": 500, "Reef Luxury Development": 424,
        "Blanco Thornton Properties": 402, "Amaal": 498, "Wahat Al Zaweya": 397, "Alef Group": 273,
        "One Yard": 200, "AAA Development": 441, "Ohana Developments": 369, "Forum Real Estate": 387,
        "Nine Development": 411, "Nine Yards Development": 494, "Mira Developments": 282, "MAK Developers": 415,
        "MS Homes": 376, "Crystal Bay Development": 377, "Galaxy": 379, "Advanced Properties": 268,
        "City View Developments": 391, "Svarn": 368, "Centurion Developers": 464, "Union Properties": 364,
        "Wellington Developments": 497, "Seven Mayfair Real Estate": 515, "DV8 Developers": 423, "Zenith Group": 513,
        "AlMadar Investment L.L.C": 428, "Abou Eid Real Estate": 252, "Asak Real Estate": 485,
        "Alhabtoor Group": 28, "Mill Hill Developer": 488, "Alaia Developments": 505, "True Future Development": 495,
        "ARTE Development": 432, "Time Properties": 104, "GFS Builders & Developers": 471, "Zoya Developments": 386,
        "Evera Real Estate Development": 467, "77 Shades of Green": 448, "BNH Real Estate Developer": 429,
        "Oksa Developer": 475, "Alhelal Al zahaby": 452, "Kingdom Properties": 456, "Aark Developers": 26,
        "Januss Developers": 447, "Grovy Real Estate": 210, "Range Developments": 479, "Matrix developments": 483,
        "Shoumous": 261, "Lucky Aeon": 66, "Meydan": 422, "Pantheon Development": 78, "DMCC": 388,
        "Arista Properties": 321, "DHG Properties": 295, "World Of Wonders": 291, "PMR Property": 450,
        "Major Development’s": 292, "Takmeel Real Estate": 314, "Urban Properties": 385, "Emerald Palace Group": 51,
        "Metac Properties L.L.C": 23, "Skyline Builders": 285, "Prescott": 357, "Vantage Ventures": 490,
        "Zane Development": 481, "Yas Developers": 463, "Amirah Developments": 482, "Elysian Properties": 454,
        "Nexus Developer": 449, "Hayaat Developments": 512, "Lincoln Star Real Estate": 466, "Arsenal East": 473,
        "Laraix Developers": 511, "Aqaar": 305, "Baraka Development": 304, "Keymavens development": 345,
        "The 100": 359, "Manam Real Estate Development": 438, "Almarina Holding": 474, "Dia Properties": 518,
        "Iraz Developments": 335, "Seven Tides": 89, "Albait Alduwaliy Real Estate": 355,
        "Palladium Development": 356, "Tabeer Developments": 98, "Lacasa Living": 477, "Wow Resorts": 405,
        "Revolution": 342, "ABA Group": 336, "Cirrera Development": 516, "SOHO Development": 344,
        "Signature Developers": 426, "Pinnacle Developers": 437, "BAMX Development": 519, "Mered": 288,
        "AiZN Development": 404, "Octa Properties": 277, "Premier Choice": 520
    }

    # تهیه لیست نام شرکت‌ها و مناطق برای پرامپت
    developer_names = ", ".join(developer_mapping.keys())
    district_names = ", ".join(district_mapping.keys())

    prompt = f"""
    کاربر به دنبال یک ملک در دبی است. از پیام زیر جزئیات مرتبط را استخراج کن:

    "{user_message}"


    **🔹 اطلاعات قبلی کاربر درباره جستجوی ملک:**
    ```json
    {json.dumps(previous_filters, ensure_ascii=False)}
    ```

    **📌 قوانین پردازش:**
    - 🚨 غلط‌های املایی رایج را اصلاح کن. اما اگر کلمه‌ای به صورت صحیح نام یک شرکت یا منطقه باشد، آن را تغییر نده.
    - 🚨 درک غلط‌های املایی و تایپی را به صورت خودکار انجام بده. اگر کلمه‌ای نادرست نوشته شده ولی معنی جمله واضح است، آن را به درستی تفسیر کن.

    - **🚨 مهم:** اگر معنی کلی جمله با وجود غلط املایی قابل فهم است، متن را به صورت صحیح پردازش کن.
    - **🚨 نکته:** اگر غلط املایی معنی جمله را تغییر دهد، سعی کن معنی درست را حدس بزنی


    - 🚨 اگر یکی از موارد max_price: حداکثر بودجه، bedrooms: تعداد اتاق‌خواب در پیام کاربر یا در اطلاعات قبلی کاربر موجود نیست مقدار "search_ready": false قرا بده و سؤالات پیشنهادی را که اطلاعاتش توسط کاربر داده نشده را بپرس.
    - اگر `district`, `city`, یا `property_type` جدیدی داده شده که با مقدار قبلی **فرق دارد**، مقدار `"new_search"` را `true` تنظیم کن.
    - 🚨 **اگر کلمه "منطقه" بدون ذکر نام خاصی آمده باشد (مثل "همین منطقه")، مقدار `district` را تغییر نده و `new_search` را `false` بگذار.**  
    - **اگر کاربر از کلماتی مانند "قیمت بالاتر"، "گرون‌تر"، "بالای X" استفاده کند، مقدار `min_price` را تنظیم کن.**
    - **اگر کاربر از کلماتی مانند "قیمت پایین‌تر"، "ارزون‌تر"، "زیر X" استفاده کند، مقدار `max_price` را تنظیم کن .**
    - اگر `min_price` و `max_price` جدید داده نشده، مقدار قبلی را نگه دار.
    - اگر اسامی مناطق یا نوع property به فارسی نوشته شد اول انگلیسیش کن بعد ذخیره کن
    - اگر مقدار `search_ready` قبلاً `false` بوده، ولی اطلاعات کافی اضافه شده باشد، مقدار `new_search` را `false` بگذار و `search_ready` را `true` تنظیم کن.
    - 🚨 اگر کاربر درباره یا `bedrooms` چیزی نگفت یا عباراتی با مفهوم "برام فرقی نداره"، "هرچند اتاق باشه اوکیه"، "مهم نیست چندتا اتاق داشته باشه" را گفت، مقدار `bedrooms` را `null` قرار بده و آن را در فیلتر لحاظ نکن.
    - 🚨 اگر کاربر درباره یا `max_price` چیزی نگفت یا عباراتی با مفهوم "برام فرقی نداره" را گفت، مقدار `max_price` را `null` قرار بده و آن را در فیلتر لحاظ نکن.
    - 🚨 اگر کاربر درباره `bedrooms` چیزی نگفت یا عباراتی مانند "فرقی نداره"، "هرچند اتاق باشه اوکیه"، "مهم نیست چندتا اتاق داشته باشه" را گفت، مقدار `bedrooms` را `null` قرار بده، و **نباید در `questions_needed` قرار بگیرد.**
    - وقتی کاربر بودجه میگه منظور max_price است
    - اگر کاربر گفت فرقی نداره یا براش مهم نیست مقدار 'search_ready' رو 'true' قرا بده
    - اگر کابر در پیامش گفت که قیمت براش مهم نیست درمورد بودجه کاربر سوال نپرس
    - اگر پیام کاربر فقط اطلاعات تکمیلی (مثلاً قیمت، منطقه یا تعداد اتاق) را اضافه کرده باشد و تغییری در موارد قبلی نداده باشد، مقدار `"new_search"` را `false` بگذار.
    - **🚨 مهم:** `questions_needed` را فقط برای اطلاعاتی که هنوز موجود نیستند برگردان، نه برای اطلاعاتی که قبلاً داده شده‌اند.
    - **🚨 اگر کاربر منطقه جدیدی گفته و `district` تغییر کرده، حتماً مقدار جدید را جایگزین مقدار قبلی کن.**
    - **🚨 تو تشخیص 'district' دقت کن که مناطق گفته شده در امارات هست **
    - **🚨 تو سوالاتی که میپرسی دقت کن که اگر مقدریش چه قبلا چه الان داده شده درمورد اون سوال نپرس **
    - ** فقط اطلاعاتی را که در پیام جدید کاربر **نیامده است و در اطلاعات قبلی نیز وجود ندارد**، در `questions_needed` قرار بده.** 
    -  اگر بودجه یا تعداد اتاق خواب مشخص نشده بود سوال متناسب با آنرا از ** questions_needed انتخاب و خروجی بده**
    -  اگر نام منطقه 'district' در پیام کاربر وجود دارد ولی واژه‌ی "منطقه" در کنار آن نیامده، همچنان آن را به‌عنوان منطقه تشخیص بده.
    - اگر کاربر گفت "اقساط بعد از تحویل" مقدار 'post_delivery' را 'Yes' بذار و اگر گفت نداشته باشه مقدارش را 'No' بذار.
    - اگر کاربر گفت برنامه پرداخت داشته باشه مقدار 'payment_plan' را 'Yes' بذار و اگر گفت نداشته باشه مقدارش را 'No' بذار.

    تعیین مقدار `payment_plan`:
        - اگر کاربر عباراتی مانند موارد زیر را استفاده کرده باشد:
        - "قسطی"، "اقساطی"، "شرایطی"، "شرایط اقساطی"، "شرایط قسطی"
        - "خانه با اقساط"، "پرداخت اقساطی"، "خرید اقساطی"، "امکان قسطی"
        - "پلن قسطی"، "برنامه پرداخت بلندمدت"، "اقساط بلندمدت"، "پرداخت بلندمدت"

        و **هیچ اشاره‌ای به نخواستن برنامه پرداخت نکرده باشد**:

        - مقدار `payment_plan` را `Yes` قرار بده.

        - اگر کاربر به‌وضوح گفته باشد که ملک را **بدون اقساط** یا با **پرداخت نقدی** می‌خواهد، و از عبارت‌هایی مانند موارد زیر استفاده کرده باشد:
        - "پرداخت نقدی"، "می‌خوام نقدی بخرم"، "بدون اقساط"، "بدون برنامه پرداخت"، "قیمت کامل پرداخت کنم"

        - مقدار `payment_plan` را `No` قرار بده.

    تعیین مقدار `post_delivery`:
        - اگر کاربر به‌وضوح گفته باشد:
        - "اقساط بعد از تحویل" یا "قسط بعد از تحویل" ➤ `post_delivery = "Yes"`
        - "اقساط قبل از تحویل" یا "قسط قبل از تحویل" ➤ `post_delivery = "No"`
        
        - اگر هیچ اشاره‌ای به اقساط یا شرایط پرداخت نکرده باشد:
            - مقدار `post_delivery` را `null` قرار بده.

        - اگر کاربر گفت فرقی نداره یا مهم نیست یا مفهومی شبیه بهش باید:
            - مقدار `post_delivery` را `All` قرار بده.



    - اگر کاربر گفت گارانتی اجاره داشته باشه مقدار 'guarantee_rental_guarantee' را 'Yes' بذار و اگر گفت نداشته باشه مقدارش را 'No' بذار.
    - 🚨 **نکته:** اگر کاربر فقط "اقساط" گفت و اشاره‌ای به برنامه پرداخت نکرد، مقدار `payment_plan` را به اشتباه 'yes' نکن!  
    - 🚨 **نکته:** اگر کاربر فقط "برنامه پرداخت" گفت و اشاره‌ای به پرداخت بعد از تحویل نکرد، مقدار `post_delivery` را به اشتباه 'yes' نکن!  
    - **قیمت‌ها (`min_price`, `max_price`) باید همیشه به عنوان `عدد` (`int`) برگردانده شوند، نه `string`**.
    - اسم شرکت ها رو به انگلیسی ذخیره کن. اگر به فارسی نوشته شده با توجه به اطلاعاتت اسم شرکت رو ذخیره کن یا چیزی نزدیک به آن را
    - امکانات گفته شده رو به انگلیسی ذخیره کن
    - اگر کاربر نوشته باشد "ی خابه"، منظور او "یک خوابه" است. این یک غلط املایی رایج است. مقدار `bedrooms` را `1` قرار بده.
    - "استودیو می‌خوام" یا "واحد استودیو" → مقدار bedrooms را "studio" قرار بده.

    - اگر کاربر فقط عبارت "مسکونی" یا "تجاری" را گفته باشد (حتی بدون ذکر جزئیات دیگر)، مقدار `property_type` را بر اساس آن تنظیم کن:
        - اگر گفت "مسکونی" یا عباراتی مثل "ملک مسکونی"، مقدار `property_type` را `"Residential"` قرار بده.
        - اگر گفت "تجاری" یا عباراتی مثل "ملک تجاری"، مقدار `property_type` را `"Commercial"` قرار بده.

    - وقتی پیام کاربر فقط یک عدد تک‌رقمی باشد (مثلاً "۲"، "دو"، "3"، "سه")، این عدد را به عدد انگلیسی به عنوان تعداد اتاق خواب (`bedrooms`) در نظر بگیر.

    - اگر کاربر گفت **"قیمت برام مهم نیست"**، در مورد بودجه کاربر سوال نپرس.
    - اگر کاربر گفت که **"قیمت مهم نیست"** یا **"فرقی نداره"**، مقدار `max_price` و `min_price` را `null` بگذار و دیگر درباره قیمت سوال نپرس.
    - اگر نام شهر توسط کاربر گفته نشده مقدار 'city' را null .بزار و فقط وقتی نام شهر گفته شد خروجی شده شهر های گفت شده یا دوبی است یا ابوظبی
    - اگر کاربر گفت 'با حدود X میلیون خونه میخوام' یا 'با X میلیون خونه میخوام' یا 'واحد x میلیونی میخوام'، مقدار X را به عدد تبدیل کن و برای فیلدهای `min_price` و `max_price` به‌صورت زیر مقداردهی کن:
        - مقدار `max_price` را ده درصد  بیشتر از مقدار گفته‌شده قرار بده.
        - مقدار `min_price` را ده درصد  کمتر از مقدار گفته‌شده تنظیم کن.
        - اگر کاربر قیمت گفته هر دو مقدار 'max_price'و 'min_price' رو مقدار دهی کن همانطور که بهت گفتم
    
    - اگر کاربر عباراتی مانند "بین X تا Y میلیون"، "از X تا Y میلیون"، یا "X تا Y میلیون" را گفت — چه به‌صورت عددی (مثلاً "2 تا 4 میلیون")، چه به‌صورت حروف فارسی (مثل "بین سه تا شش میلیون"):
        - هر دو عدد را تشخیص بده .
        - عدد کوچکتر را به عنوان `min_price` و عدد بزرگ‌تر را به عنوان `max_price` تنظیم کن.
        - این مقادیر را **دقیقاً به‌صورت همان عدد گفته‌شده توسط کاربر (بدون ±۱۰٪)** استفاده کن.
        - اگر اعداد به‌صورت فارسی نوشته شده باشند، آن‌ها را به عدد انگلیسی (int) تبدیل کن.

    - اگر کاربر عباراتی مانند "زیر X میلیون"، "کمتر از X میلیون"، "حداکثر X میلیون"، "تا X میلیون" گفت:
        - فقط مقدار `max_price` را با عدد گفته شده تنظیم کن.
        - مقدار `min_price` را **null** قرار بده یا آن را **حذف کن** حتی اگر قبلاً تنظیم شده باشد.

    - نام مناطق ممکن است **به صورت مستقیم** در جمله ظاهر شوند، حتی اگر واژه‌های "منطقه" یا "در" وجود نداشته باشد.  
      - مثال‌ها:  
        - "تو بیزینس بی واحد سه خوابه میخوام" ➡️ منطقه: "Business Bay" 
        - "تو بیزینس بی معرفی کن" 

    - برای تشخیص 'district' و 'developer_company' دقت کن از بین لیست شرکت‌ها و مناطق زیر، **نزدیک‌ترین نام** به آنچه کاربر گفته است را انتخاب کن:
        - 🏢 **لیست شرکت‌ها:** {developer_names}
        - 🗺️ **لیست مناطق:** {district_names}
    - اگر نام شرکت یا منطقه به صورت فارسی یا با غلط املایی نوشته شده باشد، آن را به نام صحیح انگلیسی تبدیل کن.
    - **در صورت یافتن نزدیک‌ترین نام، آن را در فیلتر به صورت صحیح وارد کن.**
    - اگر اطلاعات ناقص است، لیست سؤالات موردنیاز برای تکمیل را بده.

    - اگر تو اطلاعات قبلی کاربر 'previous_type' برابر با 'district_search' است اصلا سوال خروجی نده و نپرس چون
    - اگر تو اطلاعات قبلی کاربر 'previous_type' برابر با 'district_search' است اصلا و الان گفته شده به طور مثال "تو جمیرا خونه معرفی کن" اسم منطقه رو بفهم و خروجی بده

    - اگر کاربر فقط عبارت "مسکونی" یا "تجاری" را گفته باشد (حتی بدون ذکر جزئیات دیگر)، مقدار `property_type` را بر اساس آن تنظیم کن:
        - اگر گفت "مسکونی" یا عباراتی مثل "ملک مسکونی"، مقدار `property_type` را `"Residential"` قرار بده.
        - اگر گفت "تجاری" یا عباراتی مثل "ملک تجاری"، مقدار `property_type` را `"Commercial"` قرار بده.

    - اگر کاربر مستقیماً عبارت "مسکونی" یا "تجاری" را در پیامش نوشته بود، فقط در این صورت مقدار `property_type` را به ترتیب "Residential" یا "Commercial" تنظیم کن.  
    - در غیر این صورت مقدار `property_type` را `null` بگذار حتی اگر جمله به طور ضمنی به آن اشاره دارد.

    - 🚨 اگر کاربر توی پیامش حتی به صورت محاوره‌ای یا غیررسمی منطقه‌ای رو گفته (مثل "تو بیزینس بی چی داری؟")، **حتماً اون کلمه رو بررسی کن و اگر واژه انگلیسیش به نزدیک‌ترین منطقه در لیست `district_names` شباهت بیش از 70 درصد داره، به عنوان `district` ثبت کن.**
    - 🚨 :اگر کاربر در پیام خود منطقه‌ای را بیان کرده، حتی اگر با غلط املایی یا به فارسی/فینگلیش مناطق دو کلمه‌ای (مثل "پالم جمیرا"، "دبی ایلند") باشد، حتماً آن را بررسی کن.
        - برای تشخیص `district`، از لیست `district_names` استفاده کن و با fuzzy match بررسی کن:
            - اگر **شباهت به یک منطقه خاص بیشتر از 70٪** بود و نسبت به بقیه گزینه‌ها **واضح‌ترین گزینه بود**، همان را به عنوان `district` ثبت کن.


    
    - اگر کاربر عباراتی مانند "آپارتمان X متری"، "خانه X متری"، "واحد X متری"، "ملک X متری"، "متراژ X"، "X متر مربع"، "یه X متری"، "دنبال خونه X متری هستم"، "می‌خوام یه خونه X متری بخرم"، یا سایر فرم‌های مشابه را گفته باشد حتی اگر به‌صورت محاوره‌ای و غیررسمی باشد این را به‌عنوان اشاره به متراژ در نظر بگیر و X را استخراج کن.
        - عدد X (و Y اگر وجود داشت) را استخراج کن. این عدد می‌تواند به‌صورت:
            - عدد فارسی یا انگلیسی باشد (مثلاً "صد متر"، "100 متر")

    - **اگر فقط یک عدد داده شده** (مثلاً "100 متری"، "آپارتمان 75 متری"):
        - فرض کن این مقدار متوسط متراژ مدنظر کاربر است.
        - مقداردهی کن:
            - `min_area = int(X × 0.8)`
            - `max_area = int(X × 1.2)`

    - **اگر گفته شده باشد "زیر X متر"، "حداکثر X متر"، "تا X متر"، "متراژ کمتر از X":**
        - فقط `max_area` را مقدار بده:
            - `max_area = int(X)`
            - `min_area = null`

    - **اگر گفته باشد "بالای X متر"، "بیشتر از X متر"، "حداقل X متر"، "متراژ از X متر به بالا":**
        - فقط `min_area` را مقدار بده:
            - `min_area = int(X)`
            - `max_area = null`

    - **اگر گفته شده باشد "بین X تا Y متر"، "از X تا Y متر"، "بین صد تا صد و بیست متر":**
        - هر دو عدد را استخراج و مقداردهی کن:
            - `min_area = int(X)`
            - `max_area = int(Y)`

    ✅ **نکته‌ها:**
    - اگر متراژ ذکر شده ولی مشخص نیست از چه نوعه (مثلاً فقط "۸۰ متری")، همچنان حالت 20٪ بالا و پایین را در نظر بگیر.

    - **اگر اطلاعات ناقص است، لیست سؤالات موردنیاز برای تکمیل را بده.**

    خروجی باید یک شیء JSON باشد که شامل فیلدهای زیر باشد:
    - "new_search": true | false
    - "search_ready": true | false
    - "questions_needed": ["بودجه شما چقدر است؟", "پرداخت قبل از تحویل باشد یا بعد از تحویل؟", "چند اتاق خواب مدنظرتان است؟"]
    - "city" (اگر اشاره شده به انگلیسی خروجی بده)
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
    - "post_delivery" (اگر کاربر گفت "بعد از تحویل" مقدارش را 'Yes' بزار، اگر گفت "قبل از تحویل" مقدارش را 'No' بزار، اگر گفت "قسطی" یا "اقساطی" یا "شرایطی" و زمان پرداخت را مشخص نکرد، مقدارش را 'question' بزار. اگر هیچ اشاره‌ای به اقساط نبود، مقدارش را 'null' بزار.)
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
        # logging.info(f"extracted from user message: {response_content}")
        extracted_data = json.loads(response_content)
                # حفظ فیلترهای قبلی اگر مقدار جدیدی ارائه نشده باشد

        # if not extracted_data.get("search_ready"):
        #     missing_questions = extracted_data.get("questions_needed", [])
        #     if missing_questions:
        #         return "❓ برای جستجو، لطفاً این اطلاعات را مشخص کنید: " + "، ".join(missing_questions)

        # بررسی اگر `bedrooms`, `max_price`, `district` مقدار داشته باشند، `search_ready` را `true` کن
        # , "developer_company", "post_delivery", "facilities_name", "guarantee_rental_guarantee", "payment_plan"
        # essential_keys = ["bedrooms", "max_price"]
        # # essential_keys = ["bedrooms", "max_price", "min_price"]
        #----------------------------------------------------------
        # essential_keys = ["bedrooms", "max_price", "min_price", "max_area", "min_area"]
        
        # for key in essential_keys:
        #     if extracted_data.get(key) is None and memory_state.get(key) is not None:
        #         extracted_data[key] = memory_state[key]  # ✅ مقدار قبلی را نگه دار
        #----------------------------------------------------------
        essential_keys = [
            "bedrooms", "min_price", "max_price", "district", "city", "property_type",
            "apartmentType", "payment_plan", "post_delivery", "developer_company",
            "delivery_date", "guarantee_rental_guarantee", "facilities_name",
            "sales_status", "min_area", "max_area"
        ]
        
        for key in essential_keys:
            if extracted_data.get(key) is None and memory_state.get(key) is not None:
                extracted_data[key] = memory_state[key]  # ✅ مقدار قبلی را نگه دار

        # بررسی وجود قیمت و تعداد اتاق
        if extracted_data.get("bedrooms") is not None:
            if "چند اتاق خواب مدنظرتان است؟" in extracted_data.get("questions_needed", []):
                extracted_data["questions_needed"].remove("چند اتاق خواب مدنظرتان است؟")

        # اگر bedrooms داده نشده، سوال مناسبش رو بپرس
        if extracted_data.get("bedrooms") is None:
            if "چند اتاق خواب مدنظرتان است؟" not in extracted_data["questions_needed"]:
                extracted_data["questions_needed"].append("چند اتاق خواب مدنظرتان است؟")

        if extracted_data.get("max_price") is not None:
            if "بودجه شما چقدر است؟" in extracted_data.get("questions_needed", []):
                extracted_data["questions_needed"].remove("بودجه شما چقدر است؟")

        if memory_state.get("post_delivery") == "Yes":
            extracted_data["post_delivery"] = "Yes"
        elif memory_state.get("post_delivery") == "No":
            extracted_data["post_delivery"] = "No"

        if extracted_data.get("payment_plan") == "Yes":
            if extracted_data.get("post_delivery") not in ["Yes", "No", "All"]:
                extracted_data["post_delivery"] = "question"


        if extracted_data["payment_plan"] == "Yes":
            if extracted_data["post_delivery"] == "All":
                extracted_data["post_delivery"] = "DC"

        
        if extracted_data.get("post_delivery") != "question":
            if "پرداخت قبل از تحویل باشد یا بعد از تحویل؟" in extracted_data.get("questions_needed", []):
                extracted_data["questions_needed"].remove("پرداخت قبل از تحویل باشد یا بعد از تحویل؟")

        if extracted_data.get("post_delivery") == "question":
            if "پرداخت قبل از تحویل باشد یا بعد از تحویل؟" not in extracted_data["questions_needed"]:
                extracted_data["questions_needed"].append("پرداخت قبل از تحویل باشد یا بعد از تحویل؟")


        # ✅ بررسی پاسخ کاربر به سوال post_delivery
        if memory_state.get("post_delivery") == "question":
            if any(phrase in user_message for phrase in ["قبل تحویل","قبل از تحویل", "پیش از تحویل", "قبل"]):
                extracted_data["post_delivery"] = "No"
                if "پرداخت قبل از تحویل باشد یا بعد از تحویل؟" in extracted_data.get("questions_needed", []):
                    extracted_data["questions_needed"].remove("پرداخت قبل از تحویل باشد یا بعد از تحویل؟")
            elif any(phrase in user_message for phrase in ["بعد تحویل","بعد از تحویل", "پس از تحویل", "بعد"]):
                extracted_data["post_delivery"] = "Yes"
                if "پرداخت قبل از تحویل باشد یا بعد از تحویل؟" in extracted_data.get("questions_needed", []):
                    extracted_data["questions_needed"].remove("پرداخت قبل از تحویل باشد یا بعد از تحویل؟")

        # اگر هیچ مقدار جدید برای post_delivery نیومده ولی تو حافظه بوده که باید سوال پرسیده شه، نگهش دار
        if extracted_data.get("post_delivery") is None and memory_state.get("post_delivery") == "question":
            extracted_data["post_delivery"] = "question"
            if "پرداخت قبل از تحویل باشد یا بعد از تحویل؟" not in extracted_data["questions_needed"]:
                extracted_data["questions_needed"].append("پرداخت قبل از تحویل باشد یا بعد از تحویل؟")

        if extracted_data.get("bedrooms") is not None and extracted_data.get("max_price") is not None and extracted_data.get("post_delivery") != "question":
            extracted_data["search_ready"] = True  # ✅ اطلاعات کافی است، `search_ready` را `true` کن
            extracted_data["questions_needed"] = []
        else:
            if extracted_data["search_ready"] == True:
                extracted_data["questions_needed"] = []


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

        print("🔹 خروجی در تابع:",extracted_data)

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


def sort_properties_by_developer_popularity(properties):
    # لیست محبوب‌ترین توسعه‌دهنده‌ها
    developers_by_popularity = [

        # Tier 1: بسیار معروف و پیشرو
        "EMAAR", "Damac", "Aldar", "Nakheel", "Dubai Properties", "Meraas", "Sobha", "Ellington Properties",
        "Omniyat", "Select Group", "Wasl", "Azizi", "Binghatti", "Danube Properties", "Tiger Properties",

        # Tier 2: شناخته‌شده و معتبر
        "Arada Properties", "The Heart of Europe", "Samana Developers", "MAG", "Nshama", "Deyaar",
        "IFA Hotels & Resorts", "RAK Properties", "Bloom Holding", "Imkan", "Reportage",
        "Majid Al Futtaim Group", "Meydan", "Five Holdings", "Arenco Real Estate",
        "Almazaya Holding", "Shapoorji Pallonji", "London Gate", "Riviera Group",

        # Tier 3: در حال رشد و نوظهور
        "Burtville Developments", "Confident Group", "Iman Developers", "Rijas Aces Property", "GFH",
        "Expo City", "AYS Developments", "Imtiaz", "Park Group", "Prestige One", "AG Properties",
        "Swank Development", "Divine One Group", "Emirates properties", "Dubai South", "Pearlshire Developments",
        "Gulf Land", "Radiant", "Modon Properties", "Oro24", "Alzorah Development", "Algouta Properties",
        "Naseeb Group", "GJ Properties", "Amwaj Development", "Grid properties", "Aqua Properties",
        "SRG Holding", "Roya Lifestyle Developments", "Aqasa Developers", "Zimaya Properties", "Amali Properties",
        "Credo", "AAF Development", "Dalands Developer", "HRE Development", "Lootah", "AJ Gargash Real Estate",
        "Townx Real Estate", "Symbolic", "Nabni developments", "Citi Developers", "Mashriq Elite",
        "Q Properties", "ARAS Real Estate", "East & West Properties", "H&H", "Laya", "Leos", "Empire Development",
        "Object 1", "KASCO Development", "Esnad Management", "Signature D T", "Sol Properties", "Luxe Developer",
        "Dugasta", "Avelon Developments", "Rokane", "LMD Real Estate", "Source of Fate", "Vision developments",
        "Peace Homes Development", "JRP Development", "Durar", "Meraki Developers", "Uniestate Properties",
        "Eagle Hills", "IRTH", "Amaya Properties LLC", "Ajmal Makan", "Siroya Ventures Realty L.L.C", "HMB",
        "Enso Development", "Marquis Point", "Meteora", "Vincitore", "Taraf", "ADE Properties", "Baccarat",
        "Condor Group", "Rabdan", "Pure Gold", "Saas Properties", "Dubai Invesment", "Swiss Properties",
        "Beyond", "Green Group", "Mubadala", "Main Realty", "Ambs Real Estate", "MeDoRe", "Heilbronn Properties",
        "Maaia Developments", "Ginco Properties", "Qube Development", "Orange", "Alseeb Real Estate Development",
        "Peak Summit Real Estate Development", "Regent Developers", "Mr. Eight Development", "BnW Developments",
        "Tuscany Real Estate Development", "Siadah International Real Estate", "One Development", "AHS Properties",
        "ARIB Developments", "Segrex", "DIFC", "DarGlobal", "Fortune 5", "Green Yard Properties",
        "Ahmadyar Developments", "Sankari Properties", "Alta Real Estate Development", "Sama Ezdan",
        "Stamn Development", "Kamdar developments", "BT Properties", "IGO", "Orra Real Estate", "Karma",
        "Almarwan Developments", "Khamas Group Of Investment Co's", "LAPIS Properties", "Liv Developers",
        "S&S Real Estate", "Fakhruddin Properties", "Saba Property Developers", "Majid Developments",
        "HVM Living", "Golden Wood", "EL Prime Properties", "Wellcube.life",
        "Mubarak Al Beshara Real Estate Development", "Dar Alkarama", "Palma Holding", "Vantage Properties",
        "Shurooq Development", "Vakson Real Estate", "Tasmeer Indigo Properties", "Acube Developments",
        "Mada'in", "Anax Developments", "API", "Alhamra", "AB Developers", "Tarrad Real Estate", "Esnaad",
        "4 Direction Developers", "Alzarooni Development", "Alma Developments", "Reef Luxury Development",
        "Blanco Thornton Properties", "Amaal", "Wahat Al Zaweya", "Alef Group", "One Yard", "AAA Development",
        "Ohana Developments", "Forum Real Estate", "Nine Development", "Nine Yards Development", "Mira Developments",
        "MAK Developers", "MS Homes", "Crystal Bay Development", "Galaxy", "Advanced Properties",
        "City View Developments", "Svarn", "Centurion Developers", "Union Properties", "Wellington Developments",
        "Seven Mayfair Real Estate", "DV8 Developers", "Zenith Group", "AlMadar Investment L.L.C",
        "Abou Eid Real Estate", "Asak Real Estate", "Alhabtoor Group", "Mill Hill Developer",
        "Alaia Developments", "True Future Development", "ARTE Development", "Time Properties",
        "GFS Builders & Developers", "Zoya Developments", "Evera Real Estate Development", "77 Shades of Green",
        "BNH Real Estate Developer", "Oksa Developer", "Alhelal Al zahaby", "Kingdom Properties",
        "Aark Developers", "Januss Developers", "Grovy Real Estate", "Range Developments", "Matrix developments",
        "Shoumous", "Lucky Aeon", "Pantheon Development", "DMCC", "Arista Properties", "DHG Properties",
        "World Of Wonders", "PMR Property", "Major Development’s", "Takmeel Real Estate", "Urban Properties",
        "Emerald Palace Group", "Metac Properties L.L.C", "Skyline Builders", "Prescott", "Vantage Ventures",
        "Zane Development", "Yas Developers", "Amirah Developments", "Elysian Properties", "Nexus Developer",
        "Hayaat Developments", "Lincoln Star Real Estate", "Arsenal East", "Laraix Developers", "Aqaar",
        "Baraka Development", "Keymavens development", "The 100", "Manam Real Estate Development",
        "Almarina Holding", "Dia Properties", "Iraz Developments", "Seven Tides", "Albait Alduwaliy Real Estate",
        "Palladium Development", "Tabeer Developments", "Lacasa Living", "Wow Resorts", "Revolution",
        "ABA Group", "Cirrera Development", "SOHO Development", "Signature Developers", "Pinnacle Developers",
        "BAMX Development", "Mered", "AiZN Development", "Octa Properties", "Premier Choice"
    ]

    # تبدیل لیست به دیکشنری {نام شرکت کوچک‌شده: رتبه}
    developer_rank = {name.lower(): rank for rank, name in enumerate(developers_by_popularity)}

    def get_rank(property_item):
        developer_name = (
            property_item.get("developer_company", {}).get("name", "").lower()
        )
        return developer_rank.get(developer_name, float("inf"))  # اگر پیدا نشد، ته لیست

    return sorted(properties, key=get_rank)


async def generate_ai_summary(properties, start_index=0):
    """ ارائه خلاصه کوتاه از املاک پیشنهادی به صورت تدریجی """

    global last_properties_list, current_property_index, selected_properties, property_name_to_id, comp_properties
    number_property = 3

    if not properties:
        return "متأسفانه هیچ ملکی با این مشخصات پیدا نشد. لطفاً بازه قیمتی یا تعداد اتاق خواب را تغییر دهید یا منطقه دیگری انتخاب کنید."

    # properties = sort_properties_by_developer_popularity(properties)


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
        <p style="margin: 0;">برای مشاهده اطلاعات بیشتر درباره هر ملک، میتوانید عبارت <b>'پروژه [نام پروژه] را بیشتر توضیح بده'</b> را بنویسید.</p>
        <p style="margin-top: 5px;">اگر به املاک بیشتری نیاز دارید، بگویید: <b>'املاک بیشتری نشان بده'</b>.</p>
    </div>
    """

    formatted_output += """
    <div style="text-align: right; direction: rtl; padding: 10px; width: 100%;">
        <p style="margin-bottom: 8px;">همچنین میتوانید برای دریافت اطلاعات بیشتر یا خرید هر یک از این املاک، با کارشناسان ما در شرکت ترونست تماس بگیرید:</p>
        <p style="margin: 0;"><b>📞 شماره تلفن:</b> 0097143639825</p>
        <p style="margin: 0;"><b>📱 شماره همراه:</b> 00971569939796</p>
        <p style="margin: 0;"><b>💬 واتساپ:</b> <a href="https://wa.me/00971569939796">تماس با واتساپ</a></p>
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
            print(f"⚠️ خطا در جستجو با DDGS: {str(e)}. ادامه فقط با اطلاعات GPT.")  # هندل کردن تایم‌اوت و سایر خطاهای احتمالی


        prompt = f"""
        کاربز این سوال رو پرسیده :

        "{search_query}"

        همچنین این اطلاعات از اینترنت گرفته شده : 
        "{search_summary if search_summary else 'هیچ نتیجه‌ای از اینترنت دریافت نشد.'}"


        **🔹 لطفاً یک پاسخ دقیق، کوتاه و مفید در ۳ الی ۴ جمله به زبان فارسی  با توجه به اطلاعات خودت که میتونی به پیام کاربر جواب بدی و همچنین اطلاعاتی که از اینترنت گرفته شده بده و ارائه بده.**
        - لحن پاسخ باید حرفه‌ای و کمک‌کننده باشد.
        - اگر اطلاعات کافی نیست، جمله‌ای مانند "لطفاً به وب‌سایت‌های رسمی مراجعه کنید" اضافه کن.
        - متن توضیحی را داخل `<p>` قرار بده تا با اندازه عادی باشد.
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
            print(f"⚠️ خطا در جستجو با DDGS: {str(e)}. ادامه فقط با اطلاعات GPT.")  # هندل کردن تایم‌اوت و سایر خطاهای احتمالی


        # ✅ ارسال اطلاعات به GPT برای تولید خلاصه فارسی
        response_prompt = f"""
        کاربز این سوال رو پرسیده :

        "{search_query}"

        همچنین این اطلاعات از اینترنت گرفته شده : 
        "{search_summary if search_summary else 'هیچ نتیجه‌ای از اینترنت دریافت نشد.'}"


        **🔹 لطفاً یک پاسخ دقیق، کوتاه و مفید در ۳ الی ۴ جمله به زبان فارسی  با توجه به اطلاعات خودت که میتونی به پیام کاربر جواب بدی و همچنین اطلاعاتی که از اینترنت گرفته شده بده و ارائه بده.**
        -  تو مشاور املاک شرکت ترونست هستی که شرکت معتبری توی املاک امارات هست و برای اینکه به کاربر شرکتی رو خواستی معرفی کنی فقط شرکت ترونست رو معرفی کن
        - اگر کاربر درمورد مناطق پرسید با توجه به دانشت به سوالش پاسخ بده و مناطقی که به خواستش نزدیکه براش معرفی کن
        - لحن پاسخ باید حرفه‌ای و کمک‌کننده باشد.
        - اگر اطلاعات کافی نیست، جمله‌ای مانند "لطفاً به کارشناسان شرکت ترونست مراجعه کنید" اضافه کن. 
        - متن توضیحی را داخل `<p>` قرار بده تا با اندازه عادی باشد.

        """
        ai_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": response_prompt}],
            max_tokens=150
        )

        # ✅ اضافه کردن اطلاعات تماس به انتهای پاسخ
        contact_info = """
        <div style="text-align: right; direction: rtl; padding: 10px; width: 100%;">
            <p style="margin: 0;"><b>📞 شماره تلفن:</b> 0097143639825</p>
            <p style="margin: 0;"><b>📱 شماره همراه:</b> 00971569939796</p>
            <p style="margin: 0;"><b>💬 واتساپ:</b> <a href="https://wa.me/00971569939796">تماس با واتساپ</a></p>
        </div>
        """

        return ai_response.choices[0].message.content.strip() + contact_info

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
        user_property_names = re.findall(r'([A-Za-z0-9\-]+(?:\s[A-Za-z0-9\-]+)*)', user_message)  # پیدا کردن نام‌های املاک از متن کاربر
        print(user_property_names)

        for user_prop in user_property_names:
            user_prop = user_prop.strip().lower()
            if user_prop in property_name_to_id:  # ✅ **اگر نام ملک قبلاً معرفی شده باشد**
                if user_prop not in dict(mentioned_properties):  # جلوگیری از تکراری شدن
                    mentioned_properties.append((user_prop, property_name_to_id[user_prop]))
            else:
                # ✅ **بررسی شباهت فقط برای املاک قبلاً معرفی‌شده**
                best_match, score = process.extractOne(user_prop, property_name_to_id.keys()) if property_name_to_id else (None, 0)
                print(f"📌 بهترین تطابق fuzzy: {best_match} (امتیاز: {score})")

                if score > 75:  # **اگر شباهت بالای ۷۵٪ بود، این ملک را در نظر بگیر**
                    mentioned_properties.append((best_match, property_name_to_id[best_match]))


    # ✅ **بررسی تعداد املاک شناسایی شده**
    if len(mentioned_properties) < 2:
        # mentioned_names = re.findall(r'\b[A-Za-z0-9\-]+\b', user_message)  # پیدا کردن نام املاک از متن
        mentioned_names = re.findall(r'([A-Za-z0-9\-]+(?:\s[A-Za-z0-9\-]+)*)', user_message)  # پیدا کردن نام املاک از متن

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
    - 💲 **قیمت کل ملک و روش‌های پرداخت**  
    - 💲 **مبلغ پیش‌پرداخت و شرایط اقساط**  
    - **تخفیف‌های احتمالی یا پیشنهادات ویژه**  
    - **مراحل رسمی خرید این ملک در دبی**  
    - 🔗 لینک مشاهده اطلاعات کامل ملک در سایت رسمی **[سایت Trunest](https://www.trunest.ae/property/{property_id})**

    - 💡 برای دریافت اطلاعات بیشتر و راهنمایی‌های دقیق، حتماً با **کارشناسان شرکت ترونست** تماس بگیرید.  
    - 📞 **شماره تلفن:** 0097143639825  
    - 📱 **شماره همراه:** 00971569939796  
    - 🌐 **وب‌سایت:** <a href="https://trunest.ae">trunest.ae</a>  
    - 📱 **اینستاگرام:** <a href="https://instagram.com/trunest.ae">@trunest.ae</a>  
    - 💬 **واتساپ:** <a href="https://wa.me/00971569939796">تماس با واتساپ</a>   

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



# def find_districts_by_budget(max_price, bedrooms=None, apartment_typ=None, min_price=None):
def find_districts_by_budget(max_price=None, min_price=None, max_area= None, min_area = None, bedrooms=None, apartment_typ=None, facilities=None, developer_company=None, delivery_date=None, post_delivery=None, payment_plan=None, guarantee_rental=None):

    """جستجوی مناطق مناسب با توجه به بودجه و تعداد اتاق‌خواب"""
    filters = {}


    if max_price is not None:
        filters["max_price"] = max_price

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
        filters["apartmentType"] = [apartment_type_mapping.get(apartment_typ, apartment_typ)]

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

    if facilities is not None:
        facilities_list = facilities  # دریافت امکانات از `extracted_data`

        # **بررسی و تبدیل `facilities` به لیست در صورت نیاز**
        if isinstance(facilities_list, str):
            # facilities_list = [facilities_list]  # تبدیل رشته به لیست تک‌عضوی
            facilities_list = [x.strip() for x in facilities_list.split(",") if x.strip()]
        
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


    if developer_company is not None:
        developer_list = developer_company  # دریافت نام شرکت توسعه‌دهنده

        # **بررسی و تبدیل `developer_company` به لیست در صورت نیاز**
        if isinstance(developer_list, str):
            developer_list = [developer_list]  # تبدیل رشته به لیست تک‌عضوی

        developer_mapping = {
            "Burtville Developments": 330, "Sobha": 3, "Tiger Properties": 103, "Azizi": 37, "Meraas": 70,
            "Dubai Properties": 258, "Confident Group": 308, "Iman Developers": 61, "EMAAR": 2, "Shapoorji Pallonji": 91,
            "Arada Properties": 35, "Ellington Properties": 50, "Select Group": 85, "Nshama": 76, "Arenco Real Estate": 398,
            "Rijas Aces Property": 233, "Wasl": 109, "London Gate": 264, "Nakheel": 74, "GFH": 60,
            "Expo City": 54, "AYS Developments": 36, "Imtiaz": 87, "Park Group": 366, "Prestige One": 80,
            "Almazaya Holding": 68, "Samana Developers": 83, "Aldar": 32, "Bloom Holding": 270, "AG Properties": 317,
            "Swank Development": 393, "Binghatti": 38, "Divine One Group": 311, "Emirates properties": 267,
            "Dubai South": 323, "Pearlshire Developments": 329, "Gulf Land": 239, "Radiant": 269, "Modon Properties": 394,
            "Oro24": 241, "Alzorah Development": 383, "Algouta Properties": 380, "Naseeb Group": 265, "GJ Properties": 326,
            "Amwaj Development": 348, "Grid properties": 296, "Aqua Properties": 34, "SRG Holding": 95,
            "Roya Lifestyle Developments": 338, "Omniyat": 77, "Aqasa Developers": 333, "Zimaya Properties": 392,
            "Amali Properties": 341, "Credo": 324, "AAF Development": 409, "Dalands Developer": 427,
            "The Heart of Europe": 101, "HRE Development": 399, "Lootah": 65, "AJ Gargash Real Estate": 465, "Damac": 318,
            "Townx Real Estate": 105, "Symbolic": 97, "Nabni developments": 294, "Deyaar": 45, "Citi Developers": 283,
            "Mashriq Elite": 332, "IFA Hotels & Resorts": 486, "Q Properties": 408, "ARAS Real Estate": 293,
            "East & West Properties": 49, "H&H": 315, "Laya": 238, "Leos": 240, "Reportage": 232, "Empire Development": 52,
            "Object 1": 237, "KASCO Development": 433, "Esnad Management": 421, "Majid Al Futtaim Group": 111,
            "Signature D T": 203, "Sol Properties": 94, "Luxe Developer": 327, "Dugasta": 276, "Avelon Developments": 287,
            "Rokane": 417, "LMD Real Estate": 227, "Source of Fate": 434, "Vision developments": 390,
            "Peace Homes Development": 250, "JRP Development": 410, "MAG": 242, "Riviera Group": 298, "Durar": 320,
            "Meraki Developers": 71, "Uniestate Properties": 107, "Eagle Hills": 299, "IRTH": 372,
            "Amaya Properties LLC": 413, "Ajmal Makan": 260, "Siroya Ventures Realty L.L.C": 445, "HMB": 247,
            "Enso Development": 403, "Marquis Point": 274, "Meteora": 278, "Vincitore": 108, "Taraf": 100,
            "ADE Properties": 446, "Baccarat": 370, "Condor Group": 41, "Rabdan": 289, "Pure Gold": 256,
            "Saas Properties": 300, "Dubai Invesment": 254, "Swiss Properties": 96, "Beyond": 443, "Green Group": 346,
            "Mubadala": 468, "Main Realty": 334, "Danube Properties": 42, "Ambs Real Estate": 360, "MeDoRe": 255,
            "Heilbronn Properties": 339, "Maaia Developments": 517, "Ginco Properties": 374, "Qube Development": 354,
            "Orange": 303, "Alseeb Real Estate Development": 442, "Peak Summit Real Estate Development": 350,
            "Regent Developers": 501, "Mr. Eight Development": 430, "BnW Developments": 382, "Tuscany Real Estate Development": 396,
            "RAK Properties": 245, "Siadah International Real Estate": 406, "One Development": 425, "AHS Properties": 319,
            "ARIB Developments": 389, "Segrex": 284, "DIFC": 502, "DarGlobal": 44, "Fortune 5": 58,
            "Green Yard Properties": 412, "Ahmadyar Developments": 375, "Sankari Properties": 310, "Alta Real Estate Development": 491,
            "Sama Ezdan": 205, "Stamn Development": 440, "Kamdar developments": 470, "BT Properties": 507, "IGO": 259,
            "Orra Real Estate": 204, "Five Holdings": 56, "Karma": 62, "Almarwan Developments": 458,
            "Khamas Group Of Investment Co's": 363, "Imkan": 371, "LAPIS Properties": 419, "Liv Developers": 64,
            "S&S Real Estate": 499, "Fakhruddin Properties": 55, "Saba Property Developers": 416, "Majid Developments": 401,
            "HVM Living": 484, "Golden Wood": 407, "EL Prime Properties": 431, "Wellcube.life": 395,
            "Mubarak Al Beshara Real Estate Development": 420, "Dar Alkarama": 43, "Palma Holding": 340,
            "Vantage Properties": 469, "Shurooq Development": 435, "Vakson Real Estate": 358, "Tasmeer Indigo Properties": 352,
            "Acube Developments": 309, "Mada'in": 154, "Anax Developments": 301, "API": 455, "Alhamra": 351,
            "AB Developers": 367, "Tarrad Real Estate": 451, "Esnaad": 302, "4 Direction Developers": 508,
            "Alzarooni Development": 444, "Alma Developments": 500, "Reef Luxury Development": 424,
            "Blanco Thornton Properties": 402, "Amaal": 498, "Wahat Al Zaweya": 397, "Alef Group": 273,
            "One Yard": 200, "AAA Development": 441, "Ohana Developments": 369, "Forum Real Estate": 387,
            "Nine Development": 411, "Nine Yards Development": 494, "Mira Developments": 282, "MAK Developers": 415,
            "MS Homes": 376, "Crystal Bay Development": 377, "Galaxy": 379, "Advanced Properties": 268,
            "City View Developments": 391, "Svarn": 368, "Centurion Developers": 464, "Union Properties": 364,
            "Wellington Developments": 497, "Seven Mayfair Real Estate": 515, "DV8 Developers": 423, "Zenith Group": 513,
            "AlMadar Investment L.L.C": 428, "Abou Eid Real Estate": 252, "Asak Real Estate": 485,
            "Alhabtoor Group": 28, "Mill Hill Developer": 488, "Alaia Developments": 505, "True Future Development": 495,
            "ARTE Development": 432, "Time Properties": 104, "GFS Builders & Developers": 471, "Zoya Developments": 386,
            "Evera Real Estate Development": 467, "77 Shades of Green": 448, "BNH Real Estate Developer": 429,
            "Oksa Developer": 475, "Alhelal Al zahaby": 452, "Kingdom Properties": 456, "Aark Developers": 26,
            "Januss Developers": 447, "Grovy Real Estate": 210, "Range Developments": 479, "Matrix developments": 483,
            "Shoumous": 261, "Lucky Aeon": 66, "Meydan": 422, "Pantheon Development": 78, "DMCC": 388,
            "Arista Properties": 321, "DHG Properties": 295, "World Of Wonders": 291, "PMR Property": 450,
            "Major Development’s": 292, "Takmeel Real Estate": 314, "Urban Properties": 385, "Emerald Palace Group": 51,
            "Metac Properties L.L.C": 23, "Skyline Builders": 285, "Prescott": 357, "Vantage Ventures": 490,
            "Zane Development": 481, "Yas Developers": 463, "Amirah Developments": 482, "Elysian Properties": 454,
            "Nexus Developer": 449, "Hayaat Developments": 512, "Lincoln Star Real Estate": 466, "Arsenal East": 473,
            "Laraix Developers": 511, "Aqaar": 305, "Baraka Development": 304, "Keymavens development": 345,
            "The 100": 359, "Manam Real Estate Development": 438, "Almarina Holding": 474, "Dia Properties": 518,
            "Iraz Developments": 335, "Seven Tides": 89, "Albait Alduwaliy Real Estate": 355,
            "Palladium Development": 356, "Tabeer Developments": 98, "Lacasa Living": 477, "Wow Resorts": 405,
            "Revolution": 342, "ABA Group": 336, "Cirrera Development": 516, "SOHO Development": 344,
            "Signature Developers": 426, "Pinnacle Developers": 437, "BAMX Development": 519, "Mered": 288,
            "AiZN Development": 404, "Octa Properties": 277, "Premier Choice": 520
        }

        if isinstance(developer_list, list):  # بررسی اینکه ورودی یک لیست باشد
            mapped_developers = []

            for developer in developer_list:
                best_match, score = process.extractOne(developer.strip(), developer_mapping.keys())

                if score > 70:  # **فقط اگر دقت بالای ۷۰٪ بود، مقدار را قبول کن**
                    mapped_developers.append(developer_mapping[best_match])

            if mapped_developers:  # **اگر شرکت‌هایی پیدا شدند، به `filters` اضافه شود**
                filters["developer_company_id"] = mapped_developers

    if post_delivery is not None:
        if post_delivery in ["Yes", "1"]:
            filters["post_delivery"] = 1
        elif post_delivery in ["No", "0"]:
            filters["post_delivery"] = 0

    if payment_plan is not None:
        if payment_plan in ["Yes", "1"]:
            filters["payment_plan"] = 1
        elif payment_plan in ["No", "0"]:
            filters["payment_plan"] = 0

    if guarantee_rental is not None:
        if guarantee_rental in ["Yes", "1"]:
            filters["guarantee_rental_guarantee"] = 1
        elif guarantee_rental in ["No", "0"]:
            filters["guarantee_rental_guarantee"] = 0


    # if guarantee_rental is not None:
    #     filters["guarantee_rental_guarantee"] = 1 if guarantee_rental in ["Yes", "1"] else 0

    filters["property_status"] = 'Off Plan'
    filters["sales_status"] = [1]

    print(filters)
    # logging.info(f"filter district: {filters}")

    response = requests.post(f"{ESTATY_API_URL}/filter", json=filters, headers=HEADERS)

    print(response)
    if response.status_code != 200:
        return "❌ خطا در دریافت اطلاعات مناطق. لطفاً دوباره امتحان کنید."

    data = response.json()
    properties = data.get("properties", [])

    if delivery_date is not None:
        try:
            user_date = delivery_date.strip()

            # استخراج فقط سال از فرمت YYYY-MM
            match = re.match(r"^(\d{4})-(\d{2})$", user_date)
            if match:
                year = match.group(1)  # فقط سال را بگیر
                delivery_date = int(year)  # ذخیره فقط سال
            elif len(user_date) == 4 and user_date.isdigit():  # اگر فقط سال داده شده باشد
                delivery_date = int(user_date)  # ذخیره فقط سال
            else:
                print("❌ فرمت تاریخ نامعتبر است! مقدار را نادیده می‌گیریم.")
                delivery_date = None  

        except Exception as e:
            print(f"❌ خطا در پردازش تاریخ: {e}")
            delivery_date = None

    if delivery_date is not None:
        target_year = delivery_date  # سال موردنظر کاربر
        start_of_year = int(datetime(target_year, 1, 1).timestamp())  # تبدیل به یونیکس (ژانویه)
        end_of_year = int(datetime(target_year, 12, 31, 23, 59, 59).timestamp())  # تبدیل به یونیکس (دسامبر)

        properties = [
            prop for prop in properties
            if "delivery_date" in prop and prop["delivery_date"].isdigit() and 
            start_of_year <= int(prop["delivery_date"]) <= end_of_year
        ]

        print(f"🔍 بعد از فیلتر بر اساس سال تحویل ({target_year}): {len(properties)}")

    if min_area is not None or max_area is not None:
        min_val = min_area if min_area is not None else 0
        max_val = max_area if max_area is not None else float("inf")

        properties = [
            prop for prop in properties
            if "min_area" in prop and prop["min_area"] is not None and isinstance(prop["min_area"], (int, float)) and
            (min_val * 10.7639) <= float(prop["min_area"]) <= (max_val * 10.7639)
        ]

        print(f"📐 بعد از فیلتر بر اساس مساحت پروژه (sqft) بین {min_val * 10.7639} تا {max_val * 10.7639}: {len(properties)}")

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
    # response_text = "**📍 مناطقی که با بودجه شما مناسب هستند:**\n"
    response_text = """
    <div style="text-align: right; direction: rtl;">
    <p>بر اساس فیلترهایی که انتخاب کرده‌اید، مناطقی که بیشترین تعداد ملک را دارند به شرح زیر است:</p>
    <ul>
    """
    top_districts = []
    for district, count in sorted_districts[:5]:  # نمایش ۵ منطقه برتر
        # response_text += f"- **{district}** ({count} ملک موجود)\n"
        # response_text += f"• در منطقه {district}، {count} ملک در دسترس است.\n"
        # response_text += f"<li>در منطقه <b>{district}</b>، {count} ملک در دسترس است.</li>\n"
        # response_text += f"<li>در منطقه <b>{district}</b>، <b>{count}</b> ملک در دسترس است.</li>\n"
        response_text += f"<li>در منطقه <span dir='ltr'><b>{district}</b></span>، <b>{count}</b> ملک در دسترس است.</li>\n"

        top_districts.append(district)
    memory_district["suggested_districts"] = top_districts

    response_text += """
    </ul>
    <p style="text-align: right; direction: rtl;">
    در صورت تمایل می‌تونم املاک این مناطق رو بهتون معرفی کنم – فقط کافیه اسم منطقه‌ای که نظرتون رو جلب کرده رو بفرمایید 🌟
    </p>
    """

    return response_text


def find_price(district=None, bedrooms=None, apartment_typ=None, max_area= None, min_area = None, facilities=None, developer_company=None, delivery_date=None, post_delivery=None, payment_plan=None, guarantee_rental=None):

    """جستجوی مناطق مناسب با توجه به بودجه و تعداد اتاق‌خواب"""
    filters = {}

    if bedrooms is not None:
        bedrooms_count = str(bedrooms).strip().title()  # مقدار را به رشته تبدیل کن

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
        filters["apartmentType"] = [apartment_type_mapping.get(apartment_typ, apartment_typ)]

    if district is not None:
        district_i = str(district).strip().title()  # مقدار را به رشته تبدیل کن

        district_mapping = {
            'Masdar City': 340, 'Meydan': 133, 'Wadi AlSafa 2': 146, 'Wadi AlSafa 5': 246, 'Alamerah': 279,
            'JVC': 243, 'Remraam': 284, 'Aljadaf': 122, 'Liwan': 294, 'Arjan': 201, 'Dubai Creek Harbour': 152,
            'Damac Lagoons': 259, 'Dubai Downtown': 143, 'Muwaileh': 304, 'Palm Jumeirah': 134, 'Business Bay': 252,
            'City Walk': 228, 'Emaar South': 354, 'Dubai Production City': 217, 'Nadd Al Shiba': 355, 'Dubai Hills': 241,
            'Jabal Ali Industrial Second': 131, 'AlYelayiss 2': 162, 'Town Square Dubai': 275, 'Majan': 231, 'Ramhan Island': 315,
            'AlKifaf': 167, 'Alyasmeen': 310, 'Sports City': 203, 'Mbr District One': 319, 'Alraha': 352, 'Damac Hills 2': 213,
            'Wadi AlSafa 4': 189, 'Expo City': 292, 'Almarjan Island': 297, 'Zaabeel Second': 120, 'Yas Island': 303,
            'Zayed City': 295, 'Port Rashid': 378, 'Alhamra Island': 278, 'Jabal Ali First': 130, 'Dubai Land Residence Complex': 307,
            'Reem Island': 298, 'Dubai Investment Park': 156, 'The Oasis': 363, 'Alheliow1': 311, 'Dubai South': 328, 'The Valley': 361,
            'JVT': 244, 'Rashid Yachts and Marina': 383, 'Golf City': 266, 'Jebel Ali Village': 345, 'Alhudayriyat Island': 365,
            'Damac Hills': 210, 'Alzorah': 364, 'Alfurjan': 346, 'Discovery Gardens': 235, 'Dubai Islands': 233, 'Alsatwa': 273,
            'Dubai Motor City': 124, 'Palm Jabal Ali': 161, 'Saadiyat Island': 296, 'Dubai Marina': 239, 'Dubai Industrial City': 308,
            'Mina Alarab': 293, 'Sobha Hartland': 332, 'Alwasl': 141, 'Bluewaters Bay': 286, 'JLT': 212, 'World Islands': 247,
            'Mirdif': 163, 'Jumeirah Island One': 150, 'City Of Arabia': 236, 'Alreem Island': 264, 'Almaryah': 337,
            'Albarsha South': 341, 'Aljada': 327, 'International City Phase (2)': 309, 'Alshamkha': 362, 'Ghaf Woods': 389,
            'Hamriya West': 353, 'Al Yelayiss 1': 397, 'Al Tay': 343, 'Studio City': 316, 'Maryam Island': 314, 'Rukan Community': 414,
            'Madinat Jumeirah Living': 285, 'Dubai Maritime City': 216, 'Wadi Al Safa 7': 261, 'Alzahya': 312, 'Jumeirah Park': 317,
            'Bukadra': 349, 'Alsafouh Second': 407, 'Dubai Sports City': 342, 'Al Barsha South Second': 409, 'Mohammed Bin Rashid City': 318,
            'Jumeirah 2': 334, 'Uptown, AlThanyah Fifth': 220, 'Wadi AlSafa 3': 187, 'Jumeirah Heights': 402, 'Dubai Silicon Oasis': 245,
            'Dubai Design District': 230, 'Tilal AlGhaf': 199, 'Albelaida': 280, 'Jumeirah Beach Residence': 375, 'Dubai International Financial Centre (DIFC)': 333,
            'Dubai Water Canal': 387, 'Al Barsha 1': 400, 'Alwadi Desert': 406, 'Jumeirah Golf Estates': 291, 'Warsan Fourth': 249,
            'Meydan D11': 404, 'Nad Alsheba 1': 413, 'Aljurf': 359, 'MBR City D11': 368, 'International City': 248,
            'Alrashidiya 1': 386, 'Free Zone': 367, 'Dubai Internet City': 398, 'Khalifa City': 357, 'Ghantoot': 358,
            'Alnuaimia 1': 392, 'Alhamriyah': 415, 'Barsha Heights': 385, 'Ajmal Makan City': 276, 'Motor City': 326,
            'Legends': 412, 'Sharm': 374, 'AlSafouh First': 125, 'Barashi': 305, 'Al Maryah Island': 399, 'Jumeirah Garden City': 356,
            'Dubai Investment Park 2': 366, 'Sheikh Zayed Road, Alsafa': 263, 'Dubai Land': 417, 'Madinat Almataar': 250,
            'Emaar Beachfront': 391, 'Dubai Harbour': 242, 'Alheliow2': 313, 'Alsuyoh Suburb': 324, 'Tilal': 325,
            'Almuntazah': 339, 'Alrashidiya 3': 321, 'Alsafa': 268, 'Almamzar': 306, 'Sobha Hartland 2': 408, 'Siniya Island': 360,
            'Ras AlKhor Ind. First': 257, 'Albarari': 418, 'Alwaha': 416, 'Dubai Science Park': 351, 'Ain Al Fayda': 369,
            'Marina': 336, 'Dubai Healthcare City': 238, 'Trade Center First': 148, 'Damac Islands': 394,
            'The Heights Country Club': 396, 'Al Yelayiss 5': 411, 'Hayat Islands': 283, 'Mina AlArab, Hayat Islands': 282,
            'Dubai Media City': 258, 'Al Khalidiya': 382, 'AlBarsha South Fourth': 301, 'Alrahmaniya': 390, 'AlBarsha South Fifth': 123,
            "AlFaqa'": 329, 'Raha Island': 347
            
        }

        best_match, score = process.extractOne(district_i, district_mapping.keys())
        print(f"📌 بهترین تطابق fuzzy: {best_match} (امتیاز: {score})")  # نمایش اطلاعات برای دیباگ
            
        if score > 70:  # **اگر دقت بالای ۷۰٪ بود، مقدار را قبول کن**
            filters["district"] = best_match  # ✅ **ذخیره نام منطقه به جای ID**

    if facilities is not None:
        facilities_list = facilities  # دریافت امکانات از `extracted_data`

        # **بررسی و تبدیل `facilities` به لیست در صورت نیاز**
        if isinstance(facilities_list, str):
            # facilities_list = [facilities_list]  # تبدیل رشته به لیست تک‌عضوی
            facilities_list = [x.strip() for x in facilities_list.split(",") if x.strip()]
        
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


    if developer_company is not None:
        developer_list = developer_company  # دریافت نام شرکت توسعه‌دهنده

        # **بررسی و تبدیل `developer_company` به لیست در صورت نیاز**
        if isinstance(developer_list, str):
            developer_list = [developer_list]  # تبدیل رشته به لیست تک‌عضوی

        developer_mapping = {
            "Burtville Developments": 330, "Sobha": 3, "Tiger Properties": 103, "Azizi": 37, "Meraas": 70,
            "Dubai Properties": 258, "Confident Group": 308, "Iman Developers": 61, "EMAAR": 2, "Shapoorji Pallonji": 91,
            "Arada Properties": 35, "Ellington Properties": 50, "Select Group": 85, "Nshama": 76, "Arenco Real Estate": 398,
            "Rijas Aces Property": 233, "Wasl": 109, "London Gate": 264, "Nakheel": 74, "GFH": 60,
            "Expo City": 54, "AYS Developments": 36, "Imtiaz": 87, "Park Group": 366, "Prestige One": 80,
            "Almazaya Holding": 68, "Samana Developers": 83, "Aldar": 32, "Bloom Holding": 270, "AG Properties": 317,
            "Swank Development": 393, "Binghatti": 38, "Divine One Group": 311, "Emirates properties": 267,
            "Dubai South": 323, "Pearlshire Developments": 329, "Gulf Land": 239, "Radiant": 269, "Modon Properties": 394,
            "Oro24": 241, "Alzorah Development": 383, "Algouta Properties": 380, "Naseeb Group": 265, "GJ Properties": 326,
            "Amwaj Development": 348, "Grid properties": 296, "Aqua Properties": 34, "SRG Holding": 95,
            "Roya Lifestyle Developments": 338, "Omniyat": 77, "Aqasa Developers": 333, "Zimaya Properties": 392,
            "Amali Properties": 341, "Credo": 324, "AAF Development": 409, "Dalands Developer": 427,
            "The Heart of Europe": 101, "HRE Development": 399, "Lootah": 65, "AJ Gargash Real Estate": 465, "Damac": 318,
            "Townx Real Estate": 105, "Symbolic": 97, "Nabni developments": 294, "Deyaar": 45, "Citi Developers": 283,
            "Mashriq Elite": 332, "IFA Hotels & Resorts": 486, "Q Properties": 408, "ARAS Real Estate": 293,
            "East & West Properties": 49, "H&H": 315, "Laya": 238, "Leos": 240, "Reportage": 232, "Empire Development": 52,
            "Object 1": 237, "KASCO Development": 433, "Esnad Management": 421, "Majid Al Futtaim Group": 111,
            "Signature D T": 203, "Sol Properties": 94, "Luxe Developer": 327, "Dugasta": 276, "Avelon Developments": 287,
            "Rokane": 417, "LMD Real Estate": 227, "Source of Fate": 434, "Vision developments": 390,
            "Peace Homes Development": 250, "JRP Development": 410, "MAG": 242, "Riviera Group": 298, "Durar": 320,
            "Meraki Developers": 71, "Uniestate Properties": 107, "Eagle Hills": 299, "IRTH": 372,
            "Amaya Properties LLC": 413, "Ajmal Makan": 260, "Siroya Ventures Realty L.L.C": 445, "HMB": 247,
            "Enso Development": 403, "Marquis Point": 274, "Meteora": 278, "Vincitore": 108, "Taraf": 100,
            "ADE Properties": 446, "Baccarat": 370, "Condor Group": 41, "Rabdan": 289, "Pure Gold": 256,
            "Saas Properties": 300, "Dubai Invesment": 254, "Swiss Properties": 96, "Beyond": 443, "Green Group": 346,
            "Mubadala": 468, "Main Realty": 334, "Danube Properties": 42, "Ambs Real Estate": 360, "MeDoRe": 255,
            "Heilbronn Properties": 339, "Maaia Developments": 517, "Ginco Properties": 374, "Qube Development": 354,
            "Orange": 303, "Alseeb Real Estate Development": 442, "Peak Summit Real Estate Development": 350,
            "Regent Developers": 501, "Mr. Eight Development": 430, "BnW Developments": 382, "Tuscany Real Estate Development": 396,
            "RAK Properties": 245, "Siadah International Real Estate": 406, "One Development": 425, "AHS Properties": 319,
            "ARIB Developments": 389, "Segrex": 284, "DIFC": 502, "DarGlobal": 44, "Fortune 5": 58,
            "Green Yard Properties": 412, "Ahmadyar Developments": 375, "Sankari Properties": 310, "Alta Real Estate Development": 491,
            "Sama Ezdan": 205, "Stamn Development": 440, "Kamdar developments": 470, "BT Properties": 507, "IGO": 259,
            "Orra Real Estate": 204, "Five Holdings": 56, "Karma": 62, "Almarwan Developments": 458,
            "Khamas Group Of Investment Co's": 363, "Imkan": 371, "LAPIS Properties": 419, "Liv Developers": 64,
            "S&S Real Estate": 499, "Fakhruddin Properties": 55, "Saba Property Developers": 416, "Majid Developments": 401,
            "HVM Living": 484, "Golden Wood": 407, "EL Prime Properties": 431, "Wellcube.life": 395,
            "Mubarak Al Beshara Real Estate Development": 420, "Dar Alkarama": 43, "Palma Holding": 340,
            "Vantage Properties": 469, "Shurooq Development": 435, "Vakson Real Estate": 358, "Tasmeer Indigo Properties": 352,
            "Acube Developments": 309, "Mada'in": 154, "Anax Developments": 301, "API": 455, "Alhamra": 351,
            "AB Developers": 367, "Tarrad Real Estate": 451, "Esnaad": 302, "4 Direction Developers": 508,
            "Alzarooni Development": 444, "Alma Developments": 500, "Reef Luxury Development": 424,
            "Blanco Thornton Properties": 402, "Amaal": 498, "Wahat Al Zaweya": 397, "Alef Group": 273,
            "One Yard": 200, "AAA Development": 441, "Ohana Developments": 369, "Forum Real Estate": 387,
            "Nine Development": 411, "Nine Yards Development": 494, "Mira Developments": 282, "MAK Developers": 415,
            "MS Homes": 376, "Crystal Bay Development": 377, "Galaxy": 379, "Advanced Properties": 268,
            "City View Developments": 391, "Svarn": 368, "Centurion Developers": 464, "Union Properties": 364,
            "Wellington Developments": 497, "Seven Mayfair Real Estate": 515, "DV8 Developers": 423, "Zenith Group": 513,
            "AlMadar Investment L.L.C": 428, "Abou Eid Real Estate": 252, "Asak Real Estate": 485,
            "Alhabtoor Group": 28, "Mill Hill Developer": 488, "Alaia Developments": 505, "True Future Development": 495,
            "ARTE Development": 432, "Time Properties": 104, "GFS Builders & Developers": 471, "Zoya Developments": 386,
            "Evera Real Estate Development": 467, "77 Shades of Green": 448, "BNH Real Estate Developer": 429,
            "Oksa Developer": 475, "Alhelal Al zahaby": 452, "Kingdom Properties": 456, "Aark Developers": 26,
            "Januss Developers": 447, "Grovy Real Estate": 210, "Range Developments": 479, "Matrix developments": 483,
            "Shoumous": 261, "Lucky Aeon": 66, "Meydan": 422, "Pantheon Development": 78, "DMCC": 388,
            "Arista Properties": 321, "DHG Properties": 295, "World Of Wonders": 291, "PMR Property": 450,
            "Major Development’s": 292, "Takmeel Real Estate": 314, "Urban Properties": 385, "Emerald Palace Group": 51,
            "Metac Properties L.L.C": 23, "Skyline Builders": 285, "Prescott": 357, "Vantage Ventures": 490,
            "Zane Development": 481, "Yas Developers": 463, "Amirah Developments": 482, "Elysian Properties": 454,
            "Nexus Developer": 449, "Hayaat Developments": 512, "Lincoln Star Real Estate": 466, "Arsenal East": 473,
            "Laraix Developers": 511, "Aqaar": 305, "Baraka Development": 304, "Keymavens development": 345,
            "The 100": 359, "Manam Real Estate Development": 438, "Almarina Holding": 474, "Dia Properties": 518,
            "Iraz Developments": 335, "Seven Tides": 89, "Albait Alduwaliy Real Estate": 355,
            "Palladium Development": 356, "Tabeer Developments": 98, "Lacasa Living": 477, "Wow Resorts": 405,
            "Revolution": 342, "ABA Group": 336, "Cirrera Development": 516, "SOHO Development": 344,
            "Signature Developers": 426, "Pinnacle Developers": 437, "BAMX Development": 519, "Mered": 288,
            "AiZN Development": 404, "Octa Properties": 277, "Premier Choice": 520
        }

        if isinstance(developer_list, list):  # بررسی اینکه ورودی یک لیست باشد
            mapped_developers = []

            for developer in developer_list:
                best_match, score = process.extractOne(developer.strip(), developer_mapping.keys())

                if score > 70:  # **فقط اگر دقت بالای ۷۰٪ بود، مقدار را قبول کن**
                    mapped_developers.append(developer_mapping[best_match])

            if mapped_developers:  # **اگر شرکت‌هایی پیدا شدند، به `filters` اضافه شود**
                filters["developer_company_id"] = mapped_developers

    if post_delivery is not None:
        if post_delivery in ["Yes", "1"]:
            filters["post_delivery"] = 1
        elif post_delivery in ["No", "0"]:
            filters["post_delivery"] = 0

    if payment_plan is not None:
        if payment_plan in ["Yes", "1"]:
            filters["payment_plan"] = 1
        elif payment_plan in ["No", "0"]:
            filters["payment_plan"] = 0

    if guarantee_rental is not None:
        if guarantee_rental in ["Yes", "1"]:
            filters["guarantee_rental_guarantee"] = 1
        elif guarantee_rental in ["No", "0"]:
            filters["guarantee_rental_guarantee"] = 0

    # if payment_plan is not None:
    #     filters["payment_plan"] = 1 if payment_plan in ["Yes", "1"] else 0

    # if guarantee_rental is not None:
    #     filters["guarantee_rental_guarantee"] = 1 if guarantee_rental in ["Yes", "1"] else 0

    filters["property_status"] = 'Off Plan'

    filters["sales_status"] = [1]

    print(filters)
    # logging.info(f"filter find price: {filters}")
    # اضافه کردن فیلتر برای قیمت
    properties = filter_properties(filters)

    if delivery_date is not None:
        try:
            user_date = delivery_date.strip()

            # استخراج فقط سال از فرمت YYYY-MM
            match = re.match(r"^(\d{4})-(\d{2})$", user_date)
            if match:
                year = match.group(1)  # فقط سال را بگیر
                delivery_date = int(year)  # ذخیره فقط سال
            elif len(user_date) == 4 and user_date.isdigit():  # اگر فقط سال داده شده باشد
                delivery_date = int(user_date)  # ذخیره فقط سال
            else:
                print("❌ فرمت تاریخ نامعتبر است! مقدار را نادیده می‌گیریم.")
                delivery_date = None  

        except Exception as e:
            print(f"❌ خطا در پردازش تاریخ: {e}")
            delivery_date = None  

    if delivery_date is not None:
        target_year = delivery_date  # سال موردنظر کاربر
        start_of_year = int(datetime(target_year, 1, 1).timestamp())  # تبدیل به یونیکس (ژانویه)
        end_of_year = int(datetime(target_year, 12, 31, 23, 59, 59).timestamp())  # تبدیل به یونیکس (دسامبر)

        properties = [
            prop for prop in properties
            if "delivery_date" in prop and prop["delivery_date"].isdigit() and 
            start_of_year <= int(prop["delivery_date"]) <= end_of_year
        ]

        print(f"🔍 بعد از فیلتر بر اساس سال تحویل ({target_year}): {len(properties)}")


    if min_area is not None or max_area is not None:
        min_val = min_area if min_area is not None else 0
        max_val = max_area if max_area is not None else float("inf")

        properties = [
            prop for prop in properties
            if "min_area" in prop and prop["min_area"] is not None and isinstance(prop["min_area"], (int, float)) and
            (min_val * 10.7639) <= float(prop["min_area"]) <= (max_val * 10.7639)
        ]

        print(f"📐 بعد از فیلتر بر اساس مساحت پروژه (sqft) بین {min_val * 10.7639} تا {max_val * 10.7639}: {len(properties)}")

    if not properties:
        return f"❌ متأسفانه هیچ ملکی پیدا نشد."

    # ✅ محاسبه رنج قیمت
    prices = [prop.get("low_price", 0) for prop in properties if prop.get("low_price") is not None]
        
    if not prices:
        return f"❌ متأسفانه اطلاعات قیمت موجود نیست."

    min_price = min(prices)
    max_price = max(prices)

    response = f"💰 رنج قیمت املاک با این مشخصات:\n- کمترین قیمت: {min_price} درهم\n- بیشترین قیمت: {max_price} درهم"

    return response



def clear_filter_memory(memory_state):
    filter_keys = [
        "bedrooms", "min_price", "max_price", "district", "city", "property_type",
        "apartmentType", "payment_plan", "post_delivery", "developer_company",
        "delivery_date", "guarantee_rental_guarantee", "facilities_name",
        "sales_status", "min_area", "max_area", "new_search", "search_ready", "questions_needed"
    ]
    for key in filter_keys:
        memory_state.pop(key, None)  # پاک کن اگه هست

just_answered_questions = True

async def real_estate_chatbot(user_message: str) -> str:
    """ بررسی نوع پیام و ارائه پاسخ مناسب با تشخیص هوشمند """

    print(f"📌  user message : {user_message}")
    # logging.info(f"user_message: {user_message}")

    global last_properties_list, current_property_index, memory_state, developer_mapping, facilities_mapping, just_answered_questions

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

    **📌 لیست مناطقی که قبلاً به کاربر پیشنهاد شده‌اند:**
    {memory_district.get("suggested_districts", [])}

    **لطفاً مشخص کنید که پیام کاربر به کدام یک از این دسته‌ها تعلق دارد:**


    ### **۱. `search` - درخواست جستجوی ملک**  
    ✅ وقتی کاربر **به دنبال پیدا کردن یک ملک است **، مثلاً:  
    - "خانه‌ای در جمیرا می‌خوام"  
    - "یه آپارتمان با قیمت کمتر از دو میلیون درهم می‌خوام"  
    - "بهترین پروژه‌های سرمایه‌گذاری رو معرفی کن"  
    - "واحد یک خوابه میخوام که بشه اقساطی خریدش"


    ❌ **این دسته را انتخاب نکنید اگر کاربر درباره روند خرید ملک در دبی سؤال کرده باشد.** 
    ❌ **این دسته را انتخاب کن اگر کاربر نوع پیام قبلیش 'search' بود و پیام جدیدش کامل کننده پیام قبلیش مثل قیمت یا منطقه یا تعداد اتاق خواب بود**  
    ✅ وقتی پیام کاربر فقط یک عدد تک رقمی باشد (مثلاً "1"، "2"، "3") و در سوال قبلی از او تعداد اتاق پرسیده شده باشد این حالت رو انتخاب کن.
    ✅ اگر پیام قبلی کاربر `search` بود و الان اطلاعات تکمیلی مثل منطقه، قیمت، امکانات یا تعداد اتاق داده، همچنان `search` باقی بمونه.
    ✅ اگر کاربر در پیامش از عباراتی مثل "چی داری؟"، "ملکی هست؟"، "موردی داری؟" استفاده کرده و در کنارش نام منطقه یا پروژه هم گفته شده، این حالت را `search` انتخاب کن.
    ✅ اگر کاربر از عباراتی مثل "چی داری؟"، "موردی هست؟"، "ملکی داری؟" استفاده کرده و در کنارش نام یک **منطقه**، **محله** هم آمده، این حالت را `search` انتخاب کن.
    - اگر حالت قبلی پیام 'search' بود بعد الان کاربر فیلتر جدیدی مثل منطقه اضافه کرده این حالت رو انتخاب کن یعنی الان هم حالت رو 'search' قرار بده
    - اگر نوع پیام قبلی 'district_search' بود و بعدش کاربر منطقه ای را نوشت حالت رو الان 'search' قرار بده
    ✅ اگر پیام قبلی کاربر از نوع `district_search` یا `search` بود و در پیام جدید **فقط نام یک منطقه (مثلاً "تو المرجان آیلند معرفی کن")** آمده بود، این حالت را `search` در نظر بگیر.
    ✅ اگر پیام قبلی `search` بوده و پیام جدید فقط اطلاعاتی مثل بودجه یا اتاق خواب اضافه کرده، این پیام نیز `search` باقی بماند.
    ✅ اگر پیام کاربر شامل نام یک منطقه (مثل "بی‌زینس بی") و ویژگی ملک مانند قیمت یا نوع ملک (مثل "دو میلیونی"، "آپارتمان") بود، و پیام به وضوح هدفش دیدن املاک آن منطقه بود، این دسته را `search` انتخاب کن، حتی اگر برخی جزئیات مثل تعداد اتاق ذکر نشده باشد.

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

    ❌ اگر کاربر به دنبال ملک در منطقه یا پروژه خاصی است و از عباراتی مثل "چی داری؟" یا "موردی هست؟" استفاده می‌کند، این حالت را انتخاب نکن.

    ---

    ### **۵. `buying_guide` - سوال درباره نحوه خرید ملک در دبی یا راهنمای مناطق مناسب برای خرید**  
    ✅ وقتی کاربر **درباره روند خرید ملک، قوانین، ویزا یا اقامت یا مالیات یا درباره مناطق** بدون گفتن نام ملک سؤال می‌کند، یا **می‌خواهد راهنمایی کلی درباره مناطق مناسب برای خرید خانه یا سرمایه‌گذاری دریافت کند** مثلاً:  
    - "چطور در دبی خانه بخرم؟"  
    - "آیا خارجی‌ها می‌توانند در دبی ملک بخرند؟"
    - "چه مناطقی برای خرید خانه برای گرفتن اقامت طلایی مناسب است؟"    
    - "شرایط دریافت ویزای سرمایه‌گذاری چیه؟"  
    - "برای خرید ملک تو دبی باید مالیات بدم؟"  

    ❌ **این دسته را انتخاب نکنید اگر کاربر دنبال پیدا کردن یک خانه خاص باشد.**  
    ❌ اگر کاربر به دنبال ملک در منطقه یا پروژه خاصی است و از عباراتی مثل "چی داری؟" یا "موردی هست؟" استفاده می‌کند، این حالت را انتخاب نکن.

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

    ❌ **اگر کاربر فقط درباره قوانین خرید یا نحوه کلی خرید بدون ذکر ملک خاصی بپرسد، این دسته را انتخاب نکن و `buying_guide` را انتخاب کن.**

    🚨 **اگر نام پروژه یا ملک در جمله ذکر شده بود، حتماً دسته‌بندی `purchase` را انتخاب کن.**  
    ---

    ### **۱۰. `district_search` - جستجو منطقه با یا بدون بودجه**
    ✅ وقتی کاربر **به دنبال مناطقی است که متناسب با بودجه یا مشخصات خاصی باشند**، این حالت را انتخاب کن.  
    - این حالت باید نه تنها در مواردی که بودجه مشخص است، بلکه در مواردی که کاربر فقط مشخصات (مثل تعداد اتاق یا امکانات) می‌خواهد نیز انتخاب شود.  
    - اگر کاربر **بودجه‌ای مشخص نکرده باشد**، باز هم می‌تواند از این حالت استفاده کند، مشروط بر اینکه به دنبال **منطقه‌ی مناسب بر اساس سایر ویژگی‌ها** باشد.  
    مثلاً:
    - "توی چه منطقه‌ای می‌تونم با ۱ میلیون درهم خانه دو خوابه بخرم؟"
    - "کجا آپارتمان یک‌خوابه زیر ۲ میلیون درهم پیدا می‌کنم؟"
    - "خونه با قیمت دو میلیون تو کدوم منطقه میشه پیدا کرد؟"
    - "بهترین مناطق برای خرید ویلا با بودجه ۵ میلیون درهم کجا هستند؟"

    -اگر سوال کاربر مفهموش این ست که تو چه منطقه هایی میشه خانه با مشخصاتی که کاربر میگه پیدا کرد این حالت رو انتخاب کن
    ✅ اگر کاربر بپرسد "در کدام منطقه میشه پیدا کرد؟" یا از عبارات مشابه مثل "تو کدوم منطقه پیدا میشه؟"، "کجا میشه پیدا کرد؟" استفاده کند و در جمله ویژگی‌هایی مثل قیمت، امکانات یا نوع ملک وجود داشته باشد، این دسته را `district_search` انتخاب کن.
    
    🚨 اگر کاربر فقط عدد (مثلاً بودجه) نوشته و پیام قبلی `search` بوده، این پیام را به اشتباه `district_search` انتخاب نکن. در این حالت هم باید `search` بماند.
    🚨 **این حالت را انتخاب نکن اگر:**  کاربر قبلاً جستجوی ملک انجام داده و فقط بودجه را اضافه کرده است. (در این صورت `search` را انتخاب کن.)
    🚨 **این حالت را انتخاب نکن اگر کاربر مستقیماً درخواست جستجوی ملک داده باشد (در این صورت `search` را انتخاب کن).** 

    ---

    ### **۱۱. `search_no_bedroom` - جستجوی ملک بدون توجه به تعداد اتاق خواب**  
    ✅ وقتی کاربر **به‌طور خاص می‌گوید "فرقی ندارد"، "مهم نیست"، "هر چقدر باشه اوکیه"** در مورد تعداد اتاق خواب،  

    🚨 **در این حالت، مقدار `bedrooms` را `null` قرار بده و در خروجی JSON نوع پیام را `search` بگذار.** 

    ---
    ### **۱۲. `property_price` - قیمت ملک بر اساس ویژگی‌ها**  
    ✅ این حالت را انتخاب کن وقتی کاربر می‌پرسد **"قیمت یک ملک با ویژگی‌هایی خاص چقدر است؟"**، یعنی دنبال جستجو یا معرفی پروژه نیست بلکه می‌خواهد **محدوده قیمت رو بدونه**.  

    - معمولاً کلمات کلیدی مثل "در چه رنجی"، "چقدره" وجود داره.  
    - ممکنه ویژگی‌هایی مثل **تعداد اتاق، منطقه، امکانات** گفته بشه، ولی سؤال درباره محدوده قیمته نه معرفی ملک.  
    - "قیمت ملک تو بیزینس بی چنده؟"  
    - "قیمت واحد یک‌خوابه تو بیزینس بی چنده؟" 
    - "قیمت واحد دوخوابه با استخر تو چه رنجی است؟"  
    - "آپارتمان تو مارینا چند درمیاد؟"  
    - "قیمت واحد در جمیرا چقدره؟"  

    ❌ **اگر سوال درباره قیمت یک ملک مشخص باشد (نه منطقه)، حالت `details` را انتخاب کن.**  
    ✅ اگر کاربر فقط درباره قیمت ملک با ویژگی‌هایی مثل "تعداد اتاق"، "امکانات"، یا "منطقه" پرسیده بود، اما به‌دنبال جستجوی ملک نبود، این حالت را انتخاب کن.

    ---
    ### **۱۳. `availability_check` - بررسی موجود بودن ملک با ویژگی‌های خاص**  
    ✅ این حالت را انتخاب کن وقتی کاربر **سؤال می‌پرسد** که آیا ملکی با ویژگی‌های خاص **موجود هست یا نه** — نه اینکه مستقیماً بخواهد ملک معرفی شود.

    🔹 معمولا سؤال‌های این دسته به صورت زیر هستند:
    - یا **آیا... وجود دارد؟**
    - یا شامل عبارت‌هایی مثل **موجود هست؟**، **هست؟**، **موجوده؟**


    📌 مثال‌ها:
    - "آیا آپارتمان x متری با دو اتاق در دبی با اقساط بلندمدت موجود است؟"
    - "ویلا 200 متری با چهار اتاق خواب و پلن پرداخت اقساطی دارید؟"
    - "واحد تجاری 80 متری با پرداخت نقدی موجوده؟"
    - "خانه‌ای با متراژ حدود ۱۰۰ متر و سه اتاق، الان برای فروش هست؟"

    ⚠️ نکات مهم:
    - اگر سؤال کاربر **با "آیا" یا "دارید؟" شروع یا تمام شده** باشد و درون جمله **ویژگی‌هایی مثل متراژ، تعداد اتاق، قیمت یا نوع پرداخت** آمده باشد، این حالت را انتخاب کن.
    - اگر کاربر **به‌صورت غیرمستقیم ولی با لحن سؤال** می‌پرسد (مثلاً "واحد دو خوابه ۷۵ متری الان هست؟")، این حالت را انتخاب کن.
    - اگر پیام کاربر ترکیبی از یک درخواست و یک سؤال باشد (مثلاً: "دنبال آپارتمان ۱۰۰ متری هستم، آیا پرداخت اقساطی دارد؟") و سؤال مربوط به **وجود ویژگی خاص** باشد (مانند اقساطی بودن، تحویل فوری، یا متراژ خاص)، باز هم این حالت را `availability_check` در نظر بگیر، چون هدف نهایی **بررسی وجود یا عدم وجود ویژگی خاص در املاک** است، نه صرف معرفی ملک.

    - اگر جمله شامل "آیا" باشد و کاربر در همان جمله ویژگی‌هایی مثل "متراژ"، "تعداد اتاق"، "پرداخت اقساطی"، "نوع ملک" یا "شهر" را ذکر کرده باشد:
        - نوع پیام را `availability_check` قرار بده.

    ❌ این دسته را انتخاب نکن اگر:
    - کاربر به دنبال معرفی ملک باشد (مثلاً "ملکی داری؟" یا "پیشنهاد بده" یا "معرفی کن")
    - یا جمله‌اش حالت دستوری یا درخواستی داشته باشد (مثلاً "واحد معرفی کن" یا "خونه می‌خوام")

    📌 تشخیص این حالت وابسته به **قصد کاربر برای فهمیدن وضعیت موجود بودن است، نه جستجوی مستقیم.**
    ---

    **🔹 قوانین تشخیص بین حالت 'purchase' و 'details':**  
    ✅ اگر کاربر از عباراتی مانند **"می‌خوام بخرم"**، **"چطور بخرم؟"**، **"برای خرید این ملک راهنمایی کن"**، یا اسم ملک و به همراه خرید میگه، نوع پیام را `purchase` قرار بده.  
    ✅ اگر کاربر فقط اطلاعات بیشتری در مورد **امکانات، قیمت یا ویژگی‌های ملک** خواست، نوع پیام را `details` قرار بده.  

    
    - اگر پیام کاربر فقط شامل عبارات کوتاهی مانند "فرقی نداره"، "تفاوتی نداره"، "مهم نیست"، "هر دو خوبه"، و... باشد:
        - و نوع پیام قبلی `availability_check` بوده، 'type' این پیام را هم `availability_check` قرار بده.
        - مخصوصاً اگر سوال قبلی مربوط به زمان پرداخت (قبل از تحویل یا بعد از تحویل) بوده، و الان کاربر گفته "فرقی نداره"، پیام فعلی را همچنان ادامه همان حالت قبلی (`availability_check` یا `search`) در نظر بگیر و فقط مقدار `post_delivery` را `null` بگذار.

        📌 هدف این است که با شنیدن "فرقی نداره"، نوع پیام نباید تغییر کند.

    ### **⏳ مهم:**  
    اگر پیام کاربر **نامشخص** بود یا **ممکن بود چند دسته را شامل شود**، **قبل از تصمیم‌گیری، بیشتر بررسی کن و عجله نکن.**  
    اگر پیام قبلی کاربر ** search **بوده و الان اطلاعات تکمیلی داده برام حالت رو همان قرار بده
    ** اگر نوع پیام قبلی کاربر budget_search بود در پیام جدید search قرار بده**
    - اگر تاریخ تحویل در پیام داده شده حالت را 'search' قرار بده
    - اگر پیام قبلی `search` بود و الان کاربر فقط ویژگی جدیدی اضافه کرده، همون `search` باقی بمونه.
    📌 نکته مهم: اگر در پیام کاربر نام یکی از **مناطق یا پروژه‌های معروف دبی یا امارات** (مثل "بیزینس بی"، "جمیرا"، "داون‌تاون"، "دبی مارینا" و...) آمده باشد، حتی اگر کاربر نگفته باشد "منطقه‌ی..." یا "محله‌ی..."، آن را به عنوان منطقه در نظر بگیر و با توجه به آن دسته‌بندی مناسب (`search` یا `district_search`) را انتخاب کن.
    - اگر پیام جدید کاربر حاوی نام منطقه‌ای از امارات بود (مثل "در بیزینس بی"، "تو المرجان آیلند") حتی بدون عبارت‌هایی مثل "در کدام منطقه"، و پیام قبلی کاربر از نوع `district_search` یا `search` بود، پیام جدید را نیز `search` در نظر بگیر.
    - اگر پیام حاوی فقط یک منطقه بود ولی بدون درخواست مشخص برای ملک، و پیام قبلی `district_search` بود، فرض کن کاربر قصد دارد در آن منطقه ملک ببیند.
    - اگر پیام قبلی کاربر `district_search` بوده و پیام جدید شامل یکی از مناطقی است که در `suggested_districts` آمده (چه به انگلیسی و چه ترجمه‌ی فارسی آن)، نوع پیام را `search` قرار بده چون کاربر داره در ادامه‌ی جستجو، یکی از مناطق قبلی را انتخاب می‌کنه.
    ✅ اگر پیام قبلی `search` بوده و پیام جدید فقط اطلاعاتی مثل بودجه یا تعداد اتاق خواب اضافه کرده، این پیام نیز `search` باقی بماند.
    - اگر پیام جدید فقط شامل عدد (مثلاً بودجه) و پیام قبلی `search` بوده، همچنان `search` باقی بماند و تغییر نده.
    ✅ به خصوص اگر نوع پیام قبلی 'search' بوده و کاربر حالا فقط نوشته باشد "قبل از تحویل" یا "بعد از تحویل" یا "فرقی نداره" یا چیزی شبیه به اینها، این پیام را به عنوان ادامه‌ی `search` پردازش کن، نه `buying_guide`.
    ✅ به خصوص اگر نوع پیام قبلی 'availability_check' بوده و کاربر حالا فقط نوشته باشد "قبل از تحویل" یا "بعد از تحویل" یا "فرقی نداره" یا چیزی شبیه به اینها، این پیام را به عنوان ادامه‌ی `availability_check` پردازش کن.
    



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
    # logging.info(f"message type: {response_content}")

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
    # آپدیتش کن
    types["previous_type"] = types.get("current_type")
    types["current_type"] = response_type

    #---------------------------
    message_type = response_type  # از پاسخ مدل استخراج شده
    print("message_type:", message_type)

    # ✅ حالت‌هایی که نیازمند بررسی ادامه یا ریست هستند
    sensitive_types = ["search", "availability_check", "district_search", "property_price"]
    important_keys = [
        "bedrooms", "min_price", "max_price", "district", "city", "property_type",
        "apartmentType", "payment_plan", "post_delivery", "developer_company",
        "delivery_date", "guarantee_rental_guarantee", "facilities_name",
        "sales_status", "min_area", "max_area"
    ]

    if memory_state.get("pending_message"):
        if reset_requested:
            message_type = types["previous_type"]

    # ✅ بررسی پاسخ کاربر برای ریست یا ادامه
    if memory_state.get("pending_message"):
        if message_type in sensitive_types:
            if reset_requested:
                print("🔄 کاربر درخواست ریست داده است. پاک‌سازی حافظه و ادامه...")
                clear_filter_memory(memory_state)
                response_type = types["previous_type"]
                user_message = memory_state["pending_message"]
            

            # elif "ادامه بده" in user_message:
            elif any(phrase in user_message.strip().lower() for phrase in ["ادامه بده", "ادامه", "با همین ادامه بده"]):
                print("ادامه")


    has_active_filters = any(memory_state.get(k) is not None for k in important_keys)
    print("active_filer:", has_active_filters)
    print("current_message", user_message)

    # if user_message.strip() in ["ادامه بده", "ادامه", "با همین ادامه بده"] and memory_state.get("pending_message_for_reset"):
    if any(phrase in user_message for phrase in ["ادامه بده", "ادامه", "با همین ادامه بده"]) and memory_state.get("pending_message"):
        user_message = memory_state["pending_message"]
        print("edame")
        print("memory_edame", memory_state)


    #----------------------------------------- memory newest logic   
    print("message_type_ghable_soal", message_type)
    print("has_active_filters", has_active_filters)
    print("just_answered_questions", just_answered_questions)
    # ✅ اگر یکی از این حالت‌ها بود و هیچ سوالی باقی نیست، بررسی ادامه یا ریست
    if message_type in sensitive_types and has_active_filters and not just_answered_questions:
        if not memory_state.get("pending_message"):
            memory_state["pending_message"] = user_message  # ذخیره پیام فعلی
            print("memory_soal", memory_state)
            return "<p>❓ آیا می‌خواهید با همین فیلترها ادامه بدهیم یا از اول جستجو کنیم؟ (عبارت <b>ادامه بده</b> یا <b>ریست کن</b> را وارد کنید)</p>"


    print("memory_ghable_reset", memory_state)

    if not memory_state.get("pending_message"):
        if reset_requested:
            print("🔄 کاربر درخواست ریست داده است. پاک‌سازی حافظه...")
            clear_filter_memory(memory_state)
            # memory_state.clear()  # 🚀 حافظه را ریست کن
            return "✅ فیلترهای قبلی حذف شدند. لطفاً جستجوی جدیدی را شروع کنید. 😊"



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
    
    if "district_search" in response_type.lower():
        extracted_data = extract_filters(user_message, memory_state)

        if extracted_data.get("questions_needed"):
            memory_state["asked_questions"] = extracted_data["questions_needed"] 
        just_answered_questions = memory_state.get("asked_questions") and not extracted_data.get("questions_needed")
        if just_answered_questions:
            memory_state.pop("asked_questions", None)

        memory_state.update(extracted_data)
        max_price = extracted_data.get("max_price")
        min_price = extracted_data.get("min_price")
        max_area = extracted_data.get("max_area")
        min_area = extracted_data.get("min_area")
        apartment_typ = extracted_data.get("apartmentType")
        bedrooms = extracted_data.get("bedrooms")
        facilities = extracted_data.get("facilities_name")
        developer_company = extracted_data.get("developer_company")
        delivery_date = extracted_data.get("delivery_date")
        post_delivery = extracted_data.get("post_delivery")
        payment_plan = extracted_data.get("payment_plan")
        guarantee_rental = extracted_data.get("guarantee_rental_guarantee")


        return find_districts_by_budget(
        max_price=max_price, 
        min_price=min_price, 
        min_area=min_area,
        max_area=max_area,
        bedrooms=bedrooms, 
        apartment_typ=apartment_typ, 
        facilities=facilities, 
        developer_company=developer_company,
        delivery_date=delivery_date,
        post_delivery=post_delivery,
        payment_plan=payment_plan,
        guarantee_rental=guarantee_rental
        )



    if "more" in response_type.lower():
        return await generate_ai_summary(last_properties_list, start_index=current_property_index)
    
    if "buying_guide" in response_type.lower():
        return await fetch_real_estate_buying_guide(user_message)
    

    # ✅ قسمت 2: در کد اصلی چک کردن نوع availability_check
    if "availability_check" in response_type.lower():
        extracted_data = extract_filters(user_message, memory_state)  # تابعی که فیلترها رو از پیام درمیاره
        
        if "questions_needed" in extracted_data:
            payment_question = "پرداخت قبل از تحویل باشد یا بعد از تحویل؟"
            if extracted_data["post_delivery"] == "question":
                return f"❓ {payment_question}"
            

        if extracted_data.get("questions_needed"):
            memory_state["asked_questions"] = extracted_data["questions_needed"] 
        just_answered_questions = memory_state.get("asked_questions") and not extracted_data.get("questions_needed")
        if just_answered_questions:
            memory_state.pop("asked_questions", None)

        
        # بررسی مقدار `extracted_data`
        print("🔹 داده‌های استخراج‌شده از پیام کاربر:", extracted_data)

        if not extracted_data:
            return "❌ OpenAI نتوانست اطلاعاتی را از پیام شما استخراج کند."

        memory_state.update(extracted_data)

        filters = {}
        filters_date = {}
        filters_area = {}

        if extracted_data.get("city"):
            memory_state["city"] = extracted_data.get("city")


        if extracted_data.get("city") is not None:
            city_id = extracted_data["city"]  # مقدار را به رشته تبدیل کن

            city_mapping = {
            "Dubai": 6,
            "Abu Dhabi": 9
        }

            filters["city_id"] = [city_mapping.get(city_id, city_id)]

        if extracted_data.get("district"):
            district_i = str(extracted_data["district"]).strip().title()  # مقدار را به رشته تبدیل کن

            district_mapping = {
            'Masdar City': 340, 'Meydan': 133, 'Wadi AlSafa 2': 146, 'Wadi AlSafa 5': 246, 'Alamerah': 279,
            'JVC': 243, 'Remraam': 284, 'Aljadaf': 122, 'Liwan': 294, 'Arjan': 201, 'Dubai Creek Harbour': 152,
            'Damac Lagoons': 259, 'Dubai Downtown': 143, 'Muwaileh': 304, 'Palm Jumeirah': 134, 'Business Bay': 252,
            'City Walk': 228, 'Emaar South': 354, 'Dubai Production City': 217, 'Nadd Al Shiba': 355, 'Dubai Hills': 241,
            'Jabal Ali Industrial Second': 131, 'AlYelayiss 2': 162, 'Town Square Dubai': 275, 'Majan': 231, 'Ramhan Island': 315,
            'AlKifaf': 167, 'Alyasmeen': 310, 'Sports City': 203, 'Mbr District One': 319, 'Alraha': 352, 'Damac Hills 2': 213,
            'Wadi AlSafa 4': 189, 'Expo City': 292, 'Almarjan Island': 297, 'Zaabeel Second': 120, 'Yas Island': 303,
            'Zayed City': 295, 'Port Rashid': 378, 'Alhamra Island': 278, 'Jabal Ali First': 130, 'Dubai Land Residence Complex': 307,
            'Reem Island': 298, 'Dubai Investment Park': 156, 'The Oasis': 363, 'Alheliow1': 311, 'Dubai South': 328, 'The Valley': 361,
            'JVT': 244, 'Rashid Yachts and Marina': 383, 'Golf City': 266, 'Jebel Ali Village': 345, 'Alhudayriyat Island': 365,
            'Damac Hills': 210, 'Alzorah': 364, 'Alfurjan': 346, 'Discovery Gardens': 235, 'Dubai Islands': 233, 'Alsatwa': 273,
            'Dubai Motor City': 124, 'Palm Jabal Ali': 161, 'Saadiyat Island': 296, 'Dubai Marina': 239, 'Dubai Industrial City': 308,
            'Mina Alarab': 293, 'Sobha Hartland': 332, 'Alwasl': 141, 'Bluewaters Bay': 286, 'JLT': 212, 'World Islands': 247,
            'Mirdif': 163, 'Jumeirah Island One': 150, 'City Of Arabia': 236, 'Alreem Island': 264, 'Almaryah': 337,
            'Albarsha South': 341, 'Aljada': 327, 'International City Phase (2)': 309, 'Alshamkha': 362, 'Ghaf Woods': 389,
            'Hamriya West': 353, 'Al Yelayiss 1': 397, 'Al Tay': 343, 'Studio City': 316, 'Maryam Island': 314, 'Rukan Community': 414,
            'Madinat Jumeirah Living': 285, 'Dubai Maritime City': 216, 'Wadi Al Safa 7': 261, 'Alzahya': 312, 'Jumeirah Park': 317,
            'Bukadra': 349, 'Alsafouh Second': 407, 'Dubai Sports City': 342, 'Al Barsha South Second': 409, 'Mohammed Bin Rashid City': 318,
            'Jumeirah 2': 334, 'Uptown, AlThanyah Fifth': 220, 'Wadi AlSafa 3': 187, 'Jumeirah Heights': 402, 'Dubai Silicon Oasis': 245,
            'Dubai Design District': 230, 'Tilal AlGhaf': 199, 'Albelaida': 280, 'Jumeirah Beach Residence': 375, 'Dubai International Financial Centre (DIFC)': 333,
            'Dubai Water Canal': 387, 'Al Barsha 1': 400, 'Alwadi Desert': 406, 'Jumeirah Golf Estates': 291, 'Warsan Fourth': 249,
            'Meydan D11': 404, 'Nad Alsheba 1': 413, 'Aljurf': 359, 'MBR City D11': 368, 'International City': 248,
            'Alrashidiya 1': 386, 'Free Zone': 367, 'Dubai Internet City': 398, 'Khalifa City': 357, 'Ghantoot': 358,
            'Alnuaimia 1': 392, 'Alhamriyah': 415, 'Barsha Heights': 385, 'Ajmal Makan City': 276, 'Motor City': 326,
            'Legends': 412, 'Sharm': 374, 'AlSafouh First': 125, 'Barashi': 305, 'Al Maryah Island': 399, 'Jumeirah Garden City': 356,
            'Dubai Investment Park 2': 366, 'Sheikh Zayed Road, Alsafa': 263, 'Dubai Land': 417, 'Madinat Almataar': 250,
            'Emaar Beachfront': 391, 'Dubai Harbour': 242, 'Alheliow2': 313, 'Alsuyoh Suburb': 324, 'Tilal': 325,
            'Almuntazah': 339, 'Alrashidiya 3': 321, 'Alsafa': 268, 'Almamzar': 306, 'Sobha Hartland 2': 408, 'Siniya Island': 360,
            'Ras AlKhor Ind. First': 257, 'Albarari': 418, 'Alwaha': 416, 'Dubai Science Park': 351, 'Ain Al Fayda': 369,
            'Marina': 336, 'Dubai Healthcare City': 238, 'Trade Center First': 148, 'Damac Islands': 394,
            'The Heights Country Club': 396, 'Al Yelayiss 5': 411, 'Hayat Islands': 283, 'Mina AlArab, Hayat Islands': 282,
            'Dubai Media City': 258, 'Al Khalidiya': 382, 'AlBarsha South Fourth': 301, 'Alrahmaniya': 390, 'AlBarsha South Fifth': 123,
            "AlFaqa'": 329, 'Raha Island': 347
            
        }

            best_match, score = process.extractOne(district_i, district_mapping.keys())
            print(f"📌 بهترین تطابق fuzzy: {best_match} (امتیاز: {score})")  # نمایش اطلاعات برای دیباگ
            
            if score > 70:  # **اگر دقت بالای ۷۰٪ بود، مقدار را قبول کن**
                filters["district"] = best_match  # ✅ **ذخیره نام منطقه به جای ID**
            # else:
            #     filters["district"] = district_i  # اگر تطابق نداشت، همان مقدار ورودی کاربر را نگه دار

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
            filters_area["min_area"] = extracted_data.get("min_area")

        if extracted_data.get("max_area") is not None:
            filters_area["max_area"] = extracted_data.get("max_area")

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
            filters["apartmentType"] = [apartment_type_mapping.get(apartment_type, apartment_type)]



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
                "Burtville Developments": 330, "Sobha": 3, "Tiger Properties": 103, "Azizi": 37, "Meraas": 70,
                "Dubai Properties": 258, "Confident Group": 308, "Iman Developers": 61, "EMAAR": 2, "Shapoorji Pallonji": 91,
                "Arada Properties": 35, "Ellington Properties": 50, "Select Group": 85, "Nshama": 76, "Arenco Real Estate": 398,
                "Rijas Aces Property": 233, "Wasl": 109, "London Gate": 264, "Nakheel": 74, "GFH": 60,
                "Expo City": 54, "AYS Developments": 36, "Imtiaz": 87, "Park Group": 366, "Prestige One": 80,
                "Almazaya Holding": 68, "Samana Developers": 83, "Aldar": 32, "Bloom Holding": 270, "AG Properties": 317,
                "Swank Development": 393, "Binghatti": 38, "Divine One Group": 311, "Emirates properties": 267,
                "Dubai South": 323, "Pearlshire Developments": 329, "Gulf Land": 239, "Radiant": 269, "Modon Properties": 394,
                "Oro24": 241, "Alzorah Development": 383, "Algouta Properties": 380, "Naseeb Group": 265, "GJ Properties": 326,
                "Amwaj Development": 348, "Grid properties": 296, "Aqua Properties": 34, "SRG Holding": 95,
                "Roya Lifestyle Developments": 338, "Omniyat": 77, "Aqasa Developers": 333, "Zimaya Properties": 392,
                "Amali Properties": 341, "Credo": 324, "AAF Development": 409, "Dalands Developer": 427,
                "The Heart of Europe": 101, "HRE Development": 399, "Lootah": 65, "AJ Gargash Real Estate": 465, "Damac": 318,
                "Townx Real Estate": 105, "Symbolic": 97, "Nabni developments": 294, "Deyaar": 45, "Citi Developers": 283,
                "Mashriq Elite": 332, "IFA Hotels & Resorts": 486, "Q Properties": 408, "ARAS Real Estate": 293,
                "East & West Properties": 49, "H&H": 315, "Laya": 238, "Leos": 240, "Reportage": 232, "Empire Development": 52,
                "Object 1": 237, "KASCO Development": 433, "Esnad Management": 421, "Majid Al Futtaim Group": 111,
                "Signature D T": 203, "Sol Properties": 94, "Luxe Developer": 327, "Dugasta": 276, "Avelon Developments": 287,
                "Rokane": 417, "LMD Real Estate": 227, "Source of Fate": 434, "Vision developments": 390,
                "Peace Homes Development": 250, "JRP Development": 410, "MAG": 242, "Riviera Group": 298, "Durar": 320,
                "Meraki Developers": 71, "Uniestate Properties": 107, "Eagle Hills": 299, "IRTH": 372,
                "Amaya Properties LLC": 413, "Ajmal Makan": 260, "Siroya Ventures Realty L.L.C": 445, "HMB": 247,
                "Enso Development": 403, "Marquis Point": 274, "Meteora": 278, "Vincitore": 108, "Taraf": 100,
                "ADE Properties": 446, "Baccarat": 370, "Condor Group": 41, "Rabdan": 289, "Pure Gold": 256,
                "Saas Properties": 300, "Dubai Invesment": 254, "Swiss Properties": 96, "Beyond": 443, "Green Group": 346,
                "Mubadala": 468, "Main Realty": 334, "Danube Properties": 42, "Ambs Real Estate": 360, "MeDoRe": 255,
                "Heilbronn Properties": 339, "Maaia Developments": 517, "Ginco Properties": 374, "Qube Development": 354,
                "Orange": 303, "Alseeb Real Estate Development": 442, "Peak Summit Real Estate Development": 350,
                "Regent Developers": 501, "Mr. Eight Development": 430, "BnW Developments": 382, "Tuscany Real Estate Development": 396,
                "RAK Properties": 245, "Siadah International Real Estate": 406, "One Development": 425, "AHS Properties": 319,
                "ARIB Developments": 389, "Segrex": 284, "DIFC": 502, "DarGlobal": 44, "Fortune 5": 58,
                "Green Yard Properties": 412, "Ahmadyar Developments": 375, "Sankari Properties": 310, "Alta Real Estate Development": 491,
                "Sama Ezdan": 205, "Stamn Development": 440, "Kamdar developments": 470, "BT Properties": 507, "IGO": 259,
                "Orra Real Estate": 204, "Five Holdings": 56, "Karma": 62, "Almarwan Developments": 458,
                "Khamas Group Of Investment Co's": 363, "Imkan": 371, "LAPIS Properties": 419, "Liv Developers": 64,
                "S&S Real Estate": 499, "Fakhruddin Properties": 55, "Saba Property Developers": 416, "Majid Developments": 401,
                "HVM Living": 484, "Golden Wood": 407, "EL Prime Properties": 431, "Wellcube.life": 395,
                "Mubarak Al Beshara Real Estate Development": 420, "Dar Alkarama": 43, "Palma Holding": 340,
                "Vantage Properties": 469, "Shurooq Development": 435, "Vakson Real Estate": 358, "Tasmeer Indigo Properties": 352,
                "Acube Developments": 309, "Mada'in": 154, "Anax Developments": 301, "API": 455, "Alhamra": 351,
                "AB Developers": 367, "Tarrad Real Estate": 451, "Esnaad": 302, "4 Direction Developers": 508,
                "Alzarooni Development": 444, "Alma Developments": 500, "Reef Luxury Development": 424,
                "Blanco Thornton Properties": 402, "Amaal": 498, "Wahat Al Zaweya": 397, "Alef Group": 273,
                "One Yard": 200, "AAA Development": 441, "Ohana Developments": 369, "Forum Real Estate": 387,
                "Nine Development": 411, "Nine Yards Development": 494, "Mira Developments": 282, "MAK Developers": 415,
                "MS Homes": 376, "Crystal Bay Development": 377, "Galaxy": 379, "Advanced Properties": 268,
                "City View Developments": 391, "Svarn": 368, "Centurion Developers": 464, "Union Properties": 364,
                "Wellington Developments": 497, "Seven Mayfair Real Estate": 515, "DV8 Developers": 423, "Zenith Group": 513,
                "AlMadar Investment L.L.C": 428, "Abou Eid Real Estate": 252, "Asak Real Estate": 485,
                "Alhabtoor Group": 28, "Mill Hill Developer": 488, "Alaia Developments": 505, "True Future Development": 495,
                "ARTE Development": 432, "Time Properties": 104, "GFS Builders & Developers": 471, "Zoya Developments": 386,
                "Evera Real Estate Development": 467, "77 Shades of Green": 448, "BNH Real Estate Developer": 429,
                "Oksa Developer": 475, "Alhelal Al zahaby": 452, "Kingdom Properties": 456, "Aark Developers": 26,
                "Januss Developers": 447, "Grovy Real Estate": 210, "Range Developments": 479, "Matrix developments": 483,
                "Shoumous": 261, "Lucky Aeon": 66, "Meydan": 422, "Pantheon Development": 78, "DMCC": 388,
                "Arista Properties": 321, "DHG Properties": 295, "World Of Wonders": 291, "PMR Property": 450,
                "Major Development’s": 292, "Takmeel Real Estate": 314, "Urban Properties": 385, "Emerald Palace Group": 51,
                "Metac Properties L.L.C": 23, "Skyline Builders": 285, "Prescott": 357, "Vantage Ventures": 490,
                "Zane Development": 481, "Yas Developers": 463, "Amirah Developments": 482, "Elysian Properties": 454,
                "Nexus Developer": 449, "Hayaat Developments": 512, "Lincoln Star Real Estate": 466, "Arsenal East": 473,
                "Laraix Developers": 511, "Aqaar": 305, "Baraka Development": 304, "Keymavens development": 345,
                "The 100": 359, "Manam Real Estate Development": 438, "Almarina Holding": 474, "Dia Properties": 518,
                "Iraz Developments": 335, "Seven Tides": 89, "Albait Alduwaliy Real Estate": 355,
                "Palladium Development": 356, "Tabeer Developments": 98, "Lacasa Living": 477, "Wow Resorts": 405,
                "Revolution": 342, "ABA Group": 336, "Cirrera Development": 516, "SOHO Development": 344,
                "Signature Developers": 426, "Pinnacle Developers": 437, "BAMX Development": 519, "Mered": 288,
                "AiZN Development": 404, "Octa Properties": 277, "Premier Choice": 520
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
                # facilities_list = [facilities_list]  # تبدیل رشته به لیست تک‌عضوی
                facilities_list = [x.strip() for x in facilities_list.split(",") if x.strip()]
            
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
        # logging.info(f"extracted filters: {filters}")

        memory_state = filters.copy()

        if "delivery_date" in memory_state:
            del memory_state["delivery_date"]

        if "max_area" in memory_state:
            del memory_state["max_area"]

        if "min_area" in memory_state:
            del memory_state["min_area"]

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

        print(f"🔹 تعداد املاک دریافت‌شده از API: {len(properties)}")

        # ✅ فیلتر مساحت (براساس min_area موجود در property اصلی)
        if filters_area.get("min_area") is not None or filters_area.get("max_area") is not None:
            min_area = filters_area.get("min_area", 0)
            max_area = filters_area.get("max_area", float("inf"))

            properties = [
                prop for prop in properties
                if "min_area" in prop and prop["min_area"] is not None and isinstance(prop["min_area"], (int, float)) and
                (min_area * 10.7639) <= float(prop["min_area"]) <= (max_area * 10.7639)
            ]

            print(f"📐 بعد از فیلتر بر اساس مساحت پروژه (sqft) بین {min_area * 10.7639} تا {max_area * 10.7639}: {len(properties)}")


        if "max_area" in filters_area:
            memory_state["max_area"] = filters_area["max_area"]

        if "min_area" in filters_area:
            memory_state["min_area"] = filters_area["min_area"]

        if "bedrooms" in extracted_data:
            memory_state["bedrooms"] = extracted_data.get("bedrooms")

        if "developer_company" in extracted_data:
            memory_state["developer_company"] = extracted_data.get("developer_company")
            
        if "facilities_name" in extracted_data:
            memory_state["facilities_name"] = extracted_data.get("facilities_name")

        if "apartmentType" in extracted_data:
            memory_state["apartmentType"] = extracted_data.get("apartmentType")



        print("🔹 memory:", memory_state)
        # logging.info(f"memory: {memory_state}")


        print(f"🔹 تعداد املاک نهایی دریافت‌شده از API: {len(properties)}")
        properties = sort_properties_by_developer_popularity(properties)

        # if len(properties) > 0:
        #     message = f"🔎 بله، {len(properties)} مورد با این مشخصات پیدا شد که الان جندتاشو معرفی میکنم."
        #     response = await generate_ai_summary(properties)
        #     return message + "\n" + response
        # else:
        #     return "❌ ملکی با این مشخصات در حال حاضر موجود نیست."
        

        if len(properties) > 0:
            response = await generate_ai_summary(properties)

            if len(properties) > 1:
                message_html = f"""
                <div style="text-align: right; direction: rtl; padding: 10px; width: 100%;">
                    <h3 style="color: black;">🔎 بله، {len(properties)} مورد با این مشخصات پیدا شد که الان چندتاشو معرفی می‌کنم:</h3>
                </div>
                """
            elif len(properties) == 1:
                message_html = f"""
                <div style="text-align: right; direction: rtl; padding: 10px; width: 100%;">
                    <h3 style="color: black;">🔎 بله، {len(properties)} مورد با این مشخصات پیدا شد که الان همون یکی رو معرفی می‌کنم:</h3>
                </div>
                """

            # message_html = f"""
            # <div style="text-align: right; direction: rtl; padding: 10px; width: 100%;">
            #     <h3 style="color: black;">🔎 بله، {len(properties)} مورد با این مشخصات پیدا شد که الان چندتاشو معرفی می‌کنم:</h3>
            # </div>
            # """

            return message_html + response
        else:
            return """
            <div style="text-align: right; direction: rtl; padding: 10px; width: 100%;">
                <p>❌ ملکی با این مشخصات در حال حاضر موجود نیست.</p>
            </div>
            """
        # print(properties[:3])

        # response = generate_ai_summary(properties)
        

    
    if "property_price" in response_type.lower():
        extracted_data = extract_filters(user_message, memory_state)

        if extracted_data.get("questions_needed"):
            memory_state["asked_questions"] = extracted_data["questions_needed"] 
        just_answered_questions = memory_state.get("asked_questions") and not extracted_data.get("questions_needed")
        if just_answered_questions:
            memory_state.pop("asked_questions", None)

        district = extracted_data.get("district")
        apartment_typ = extracted_data.get("apartmentType")
        bedrooms = extracted_data.get("bedrooms")
        facilities = extracted_data.get("facilities_name")
        developer_company = extracted_data.get("developer_company")
        delivery_date = extracted_data.get("delivery_date")
        post_delivery = extracted_data.get("post_delivery")
        payment_plan = extracted_data.get("payment_plan")
        guarantee_rental = extracted_data.get("guarantee_rental_guarantee")
        max_area = extracted_data.get("max_area")
        min_area = extracted_data.get("min_area")


        return find_price(
        min_area=min_area,
        max_area=max_area,
        district=district, 
        bedrooms=bedrooms, 
        apartment_typ=apartment_typ, 
        facilities=facilities, 
        developer_company=developer_company,
        delivery_date=delivery_date,
        post_delivery=post_delivery,
        payment_plan=payment_plan,
        guarantee_rental=guarantee_rental
        )



    if "search" in response_type.lower():
        print("✅ تابع extract_filters در حال اجرا است...")
        print("🔹 memory", memory_state)

        extracted_data = extract_filters(user_message, memory_state)


        if "questions_needed" in extracted_data and len(extracted_data["questions_needed"]) > 0:
            # print("❓ اطلاعات ناقص است، سوالات لازم: ", extracted_data["questions_needed"])

            # # 🚀 ذخیره فقط `bedrooms`, `max_price`, `district` در `memory_state`
            # essential_keys = ["bedrooms", "max_price", "post_delivery"]
            # for key in essential_keys:
            #     if extracted_data.get(key) is not None and extracted_data.get(key) != "question":
            #         memory_state[key] = extracted_data[key]  # مقدار جدید را ذخیره کن

            # print("✅ اطلاعات ضروری از extracted_data در memory_state ذخیره شد:", memory_state)

            return "❓ " + "، ".join(extracted_data["questions_needed"])

        if "questions_needed" in extracted_data:
            payment_question = "پرداخت قبل از تحویل باشد یا بعد از تحویل؟"
            if extracted_data["post_delivery"] == "question":
                return f"❓ {payment_question}"
            
        # previous_questions = set(memory_state.get("asked_questions", []))
        # current_questions = set(extracted_data.get("questions_needed", []))
        # just_answered_questions = previous_questions and not current_questions.intersection(previous_questions)

        

        if extracted_data.get("questions_needed"):
            memory_state["asked_questions"] = extracted_data["questions_needed"] 
        just_answered_questions = memory_state.get("asked_questions") and not extracted_data.get("questions_needed")
        if just_answered_questions:
            memory_state.pop("asked_questions", None)
        
        # بررسی مقدار `extracted_data`
        print("🔹 داده‌های استخراج‌شده از پیام کاربر:", extracted_data)

        if not extracted_data:
            return "❌ OpenAI نتوانست اطلاعاتی را از پیام شما استخراج کند."

        memory_state.update(extracted_data)

        filters = {}
        filters_date = {}
        filters_area = {}

        if extracted_data.get("city"):
            memory_state["city"] = extracted_data.get("city")


        if extracted_data.get("city") is not None:
            city_id = extracted_data["city"]  # مقدار را به رشته تبدیل کن

            city_mapping = {
            "Dubai": 6,
            "Abu Dhabi": 9
        }

            filters["city_id"] = [city_mapping.get(city_id, city_id)]

        if extracted_data.get("district"):
            district_i = str(extracted_data["district"]).strip().title()  # مقدار را به رشته تبدیل کن

            district_mapping = {
            'Masdar City': 340, 'Meydan': 133, 'Wadi AlSafa 2': 146, 'Wadi AlSafa 5': 246, 'Alamerah': 279,
            'JVC': 243, 'Remraam': 284, 'Aljadaf': 122, 'Liwan': 294, 'Arjan': 201, 'Dubai Creek Harbour': 152,
            'Damac Lagoons': 259, 'Dubai Downtown': 143, 'Muwaileh': 304, 'Palm Jumeirah': 134, 'Business Bay': 252,
            'City Walk': 228, 'Emaar South': 354, 'Dubai Production City': 217, 'Nadd Al Shiba': 355, 'Dubai Hills': 241,
            'Jabal Ali Industrial Second': 131, 'AlYelayiss 2': 162, 'Town Square Dubai': 275, 'Majan': 231, 'Ramhan Island': 315,
            'AlKifaf': 167, 'Alyasmeen': 310, 'Sports City': 203, 'Mbr District One': 319, 'Alraha': 352, 'Damac Hills 2': 213,
            'Wadi AlSafa 4': 189, 'Expo City': 292, 'Almarjan Island': 297, 'Zaabeel Second': 120, 'Yas Island': 303,
            'Zayed City': 295, 'Port Rashid': 378, 'Alhamra Island': 278, 'Jabal Ali First': 130, 'Dubai Land Residence Complex': 307,
            'Reem Island': 298, 'Dubai Investment Park': 156, 'The Oasis': 363, 'Alheliow1': 311, 'Dubai South': 328, 'The Valley': 361,
            'JVT': 244, 'Rashid Yachts and Marina': 383, 'Golf City': 266, 'Jebel Ali Village': 345, 'Alhudayriyat Island': 365,
            'Damac Hills': 210, 'Alzorah': 364, 'Alfurjan': 346, 'Discovery Gardens': 235, 'Dubai Islands': 233, 'Alsatwa': 273,
            'Dubai Motor City': 124, 'Palm Jabal Ali': 161, 'Saadiyat Island': 296, 'Dubai Marina': 239, 'Dubai Industrial City': 308,
            'Mina Alarab': 293, 'Sobha Hartland': 332, 'Alwasl': 141, 'Bluewaters Bay': 286, 'JLT': 212, 'World Islands': 247,
            'Mirdif': 163, 'Jumeirah Island One': 150, 'City Of Arabia': 236, 'Alreem Island': 264, 'Almaryah': 337,
            'Albarsha South': 341, 'Aljada': 327, 'International City Phase (2)': 309, 'Alshamkha': 362, 'Ghaf Woods': 389,
            'Hamriya West': 353, 'Al Yelayiss 1': 397, 'Al Tay': 343, 'Studio City': 316, 'Maryam Island': 314, 'Rukan Community': 414,
            'Madinat Jumeirah Living': 285, 'Dubai Maritime City': 216, 'Wadi Al Safa 7': 261, 'Alzahya': 312, 'Jumeirah Park': 317,
            'Bukadra': 349, 'Alsafouh Second': 407, 'Dubai Sports City': 342, 'Al Barsha South Second': 409, 'Mohammed Bin Rashid City': 318,
            'Jumeirah 2': 334, 'Uptown, AlThanyah Fifth': 220, 'Wadi AlSafa 3': 187, 'Jumeirah Heights': 402, 'Dubai Silicon Oasis': 245,
            'Dubai Design District': 230, 'Tilal AlGhaf': 199, 'Albelaida': 280, 'Jumeirah Beach Residence': 375, 'Dubai International Financial Centre (DIFC)': 333,
            'Dubai Water Canal': 387, 'Al Barsha 1': 400, 'Alwadi Desert': 406, 'Jumeirah Golf Estates': 291, 'Warsan Fourth': 249,
            'Meydan D11': 404, 'Nad Alsheba 1': 413, 'Aljurf': 359, 'MBR City D11': 368, 'International City': 248,
            'Alrashidiya 1': 386, 'Free Zone': 367, 'Dubai Internet City': 398, 'Khalifa City': 357, 'Ghantoot': 358,
            'Alnuaimia 1': 392, 'Alhamriyah': 415, 'Barsha Heights': 385, 'Ajmal Makan City': 276, 'Motor City': 326,
            'Legends': 412, 'Sharm': 374, 'AlSafouh First': 125, 'Barashi': 305, 'Al Maryah Island': 399, 'Jumeirah Garden City': 356,
            'Dubai Investment Park 2': 366, 'Sheikh Zayed Road, Alsafa': 263, 'Dubai Land': 417, 'Madinat Almataar': 250,
            'Emaar Beachfront': 391, 'Dubai Harbour': 242, 'Alheliow2': 313, 'Alsuyoh Suburb': 324, 'Tilal': 325,
            'Almuntazah': 339, 'Alrashidiya 3': 321, 'Alsafa': 268, 'Almamzar': 306, 'Sobha Hartland 2': 408, 'Siniya Island': 360,
            'Ras AlKhor Ind. First': 257, 'Albarari': 418, 'Alwaha': 416, 'Dubai Science Park': 351, 'Ain Al Fayda': 369,
            'Marina': 336, 'Dubai Healthcare City': 238, 'Trade Center First': 148, 'Damac Islands': 394,
            'The Heights Country Club': 396, 'Al Yelayiss 5': 411, 'Hayat Islands': 283, 'Mina AlArab, Hayat Islands': 282,
            'Dubai Media City': 258, 'Al Khalidiya': 382, 'AlBarsha South Fourth': 301, 'Alrahmaniya': 390, 'AlBarsha South Fifth': 123,
            "AlFaqa'": 329, 'Raha Island': 347
            
        }

            best_match, score = process.extractOne(district_i, district_mapping.keys())
            print(f"📌 بهترین تطابق fuzzy: {best_match} (امتیاز: {score})")  # نمایش اطلاعات برای دیباگ
            
            if score > 70:  # **اگر دقت بالای ۷۰٪ بود، مقدار را قبول کن**
                filters["district"] = best_match  # ✅ **ذخیره نام منطقه به جای ID**
            # else:
            #     filters["district"] = district_i  # اگر تطابق نداشت، همان مقدار ورودی کاربر را نگه دار

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
            filters_area["min_area"] = extracted_data.get("min_area")

        if extracted_data.get("max_area") is not None:
            filters_area["max_area"] = extracted_data.get("max_area")

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
            filters["apartmentType"] = [apartment_type_mapping.get(apartment_type, apartment_type)]



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
                "Burtville Developments": 330, "Sobha": 3, "Tiger Properties": 103, "Azizi": 37, "Meraas": 70,
                "Dubai Properties": 258, "Confident Group": 308, "Iman Developers": 61, "EMAAR": 2, "Shapoorji Pallonji": 91,
                "Arada Properties": 35, "Ellington Properties": 50, "Select Group": 85, "Nshama": 76, "Arenco Real Estate": 398,
                "Rijas Aces Property": 233, "Wasl": 109, "London Gate": 264, "Nakheel": 74, "GFH": 60,
                "Expo City": 54, "AYS Developments": 36, "Imtiaz": 87, "Park Group": 366, "Prestige One": 80,
                "Almazaya Holding": 68, "Samana Developers": 83, "Aldar": 32, "Bloom Holding": 270, "AG Properties": 317,
                "Swank Development": 393, "Binghatti": 38, "Divine One Group": 311, "Emirates properties": 267,
                "Dubai South": 323, "Pearlshire Developments": 329, "Gulf Land": 239, "Radiant": 269, "Modon Properties": 394,
                "Oro24": 241, "Alzorah Development": 383, "Algouta Properties": 380, "Naseeb Group": 265, "GJ Properties": 326,
                "Amwaj Development": 348, "Grid properties": 296, "Aqua Properties": 34, "SRG Holding": 95,
                "Roya Lifestyle Developments": 338, "Omniyat": 77, "Aqasa Developers": 333, "Zimaya Properties": 392,
                "Amali Properties": 341, "Credo": 324, "AAF Development": 409, "Dalands Developer": 427,
                "The Heart of Europe": 101, "HRE Development": 399, "Lootah": 65, "AJ Gargash Real Estate": 465, "Damac": 318,
                "Townx Real Estate": 105, "Symbolic": 97, "Nabni developments": 294, "Deyaar": 45, "Citi Developers": 283,
                "Mashriq Elite": 332, "IFA Hotels & Resorts": 486, "Q Properties": 408, "ARAS Real Estate": 293,
                "East & West Properties": 49, "H&H": 315, "Laya": 238, "Leos": 240, "Reportage": 232, "Empire Development": 52,
                "Object 1": 237, "KASCO Development": 433, "Esnad Management": 421, "Majid Al Futtaim Group": 111,
                "Signature D T": 203, "Sol Properties": 94, "Luxe Developer": 327, "Dugasta": 276, "Avelon Developments": 287,
                "Rokane": 417, "LMD Real Estate": 227, "Source of Fate": 434, "Vision developments": 390,
                "Peace Homes Development": 250, "JRP Development": 410, "MAG": 242, "Riviera Group": 298, "Durar": 320,
                "Meraki Developers": 71, "Uniestate Properties": 107, "Eagle Hills": 299, "IRTH": 372,
                "Amaya Properties LLC": 413, "Ajmal Makan": 260, "Siroya Ventures Realty L.L.C": 445, "HMB": 247,
                "Enso Development": 403, "Marquis Point": 274, "Meteora": 278, "Vincitore": 108, "Taraf": 100,
                "ADE Properties": 446, "Baccarat": 370, "Condor Group": 41, "Rabdan": 289, "Pure Gold": 256,
                "Saas Properties": 300, "Dubai Invesment": 254, "Swiss Properties": 96, "Beyond": 443, "Green Group": 346,
                "Mubadala": 468, "Main Realty": 334, "Danube Properties": 42, "Ambs Real Estate": 360, "MeDoRe": 255,
                "Heilbronn Properties": 339, "Maaia Developments": 517, "Ginco Properties": 374, "Qube Development": 354,
                "Orange": 303, "Alseeb Real Estate Development": 442, "Peak Summit Real Estate Development": 350,
                "Regent Developers": 501, "Mr. Eight Development": 430, "BnW Developments": 382, "Tuscany Real Estate Development": 396,
                "RAK Properties": 245, "Siadah International Real Estate": 406, "One Development": 425, "AHS Properties": 319,
                "ARIB Developments": 389, "Segrex": 284, "DIFC": 502, "DarGlobal": 44, "Fortune 5": 58,
                "Green Yard Properties": 412, "Ahmadyar Developments": 375, "Sankari Properties": 310, "Alta Real Estate Development": 491,
                "Sama Ezdan": 205, "Stamn Development": 440, "Kamdar developments": 470, "BT Properties": 507, "IGO": 259,
                "Orra Real Estate": 204, "Five Holdings": 56, "Karma": 62, "Almarwan Developments": 458,
                "Khamas Group Of Investment Co's": 363, "Imkan": 371, "LAPIS Properties": 419, "Liv Developers": 64,
                "S&S Real Estate": 499, "Fakhruddin Properties": 55, "Saba Property Developers": 416, "Majid Developments": 401,
                "HVM Living": 484, "Golden Wood": 407, "EL Prime Properties": 431, "Wellcube.life": 395,
                "Mubarak Al Beshara Real Estate Development": 420, "Dar Alkarama": 43, "Palma Holding": 340,
                "Vantage Properties": 469, "Shurooq Development": 435, "Vakson Real Estate": 358, "Tasmeer Indigo Properties": 352,
                "Acube Developments": 309, "Mada'in": 154, "Anax Developments": 301, "API": 455, "Alhamra": 351,
                "AB Developers": 367, "Tarrad Real Estate": 451, "Esnaad": 302, "4 Direction Developers": 508,
                "Alzarooni Development": 444, "Alma Developments": 500, "Reef Luxury Development": 424,
                "Blanco Thornton Properties": 402, "Amaal": 498, "Wahat Al Zaweya": 397, "Alef Group": 273,
                "One Yard": 200, "AAA Development": 441, "Ohana Developments": 369, "Forum Real Estate": 387,
                "Nine Development": 411, "Nine Yards Development": 494, "Mira Developments": 282, "MAK Developers": 415,
                "MS Homes": 376, "Crystal Bay Development": 377, "Galaxy": 379, "Advanced Properties": 268,
                "City View Developments": 391, "Svarn": 368, "Centurion Developers": 464, "Union Properties": 364,
                "Wellington Developments": 497, "Seven Mayfair Real Estate": 515, "DV8 Developers": 423, "Zenith Group": 513,
                "AlMadar Investment L.L.C": 428, "Abou Eid Real Estate": 252, "Asak Real Estate": 485,
                "Alhabtoor Group": 28, "Mill Hill Developer": 488, "Alaia Developments": 505, "True Future Development": 495,
                "ARTE Development": 432, "Time Properties": 104, "GFS Builders & Developers": 471, "Zoya Developments": 386,
                "Evera Real Estate Development": 467, "77 Shades of Green": 448, "BNH Real Estate Developer": 429,
                "Oksa Developer": 475, "Alhelal Al zahaby": 452, "Kingdom Properties": 456, "Aark Developers": 26,
                "Januss Developers": 447, "Grovy Real Estate": 210, "Range Developments": 479, "Matrix developments": 483,
                "Shoumous": 261, "Lucky Aeon": 66, "Meydan": 422, "Pantheon Development": 78, "DMCC": 388,
                "Arista Properties": 321, "DHG Properties": 295, "World Of Wonders": 291, "PMR Property": 450,
                "Major Development’s": 292, "Takmeel Real Estate": 314, "Urban Properties": 385, "Emerald Palace Group": 51,
                "Metac Properties L.L.C": 23, "Skyline Builders": 285, "Prescott": 357, "Vantage Ventures": 490,
                "Zane Development": 481, "Yas Developers": 463, "Amirah Developments": 482, "Elysian Properties": 454,
                "Nexus Developer": 449, "Hayaat Developments": 512, "Lincoln Star Real Estate": 466, "Arsenal East": 473,
                "Laraix Developers": 511, "Aqaar": 305, "Baraka Development": 304, "Keymavens development": 345,
                "The 100": 359, "Manam Real Estate Development": 438, "Almarina Holding": 474, "Dia Properties": 518,
                "Iraz Developments": 335, "Seven Tides": 89, "Albait Alduwaliy Real Estate": 355,
                "Palladium Development": 356, "Tabeer Developments": 98, "Lacasa Living": 477, "Wow Resorts": 405,
                "Revolution": 342, "ABA Group": 336, "Cirrera Development": 516, "SOHO Development": 344,
                "Signature Developers": 426, "Pinnacle Developers": 437, "BAMX Development": 519, "Mered": 288,
                "AiZN Development": 404, "Octa Properties": 277, "Premier Choice": 520
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
                # facilities_list = [facilities_list]  # تبدیل رشته به لیست تک‌عضوی
                facilities_list = [x.strip() for x in facilities_list.split(",") if x.strip()]
            
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
        # logging.info(f"extracted filters: {filters}")

        memory_state = filters.copy()

        if "delivery_date" in memory_state:
            del memory_state["delivery_date"]


        if "max_area" in memory_state:
            del memory_state["max_area"]

        if "min_area" in memory_state:
            del memory_state["min_area"]

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

        print(f"🔹 تعداد املاک دریافت‌شده از API: {len(properties)}")

        # ✅ فیلتر مساحت (براساس min_area موجود در property اصلی)
        if filters_area.get("min_area") is not None or filters_area.get("max_area") is not None:
            min_area = filters_area.get("min_area", 0)
            max_area = filters_area.get("max_area", float("inf"))

            properties = [
                prop for prop in properties
                if "min_area" in prop and prop["min_area"] is not None and isinstance(prop["min_area"], (int, float)) and
                (min_area * 10.7639) <= float(prop["min_area"]) <= (max_area * 10.7639)
            ]

            print(f"📐 بعد از فیلتر بر اساس مساحت پروژه (sqft) بین {min_area * 10.7639} تا {max_area * 10.7639}: {len(properties)}")


        if "max_area" in filters_area:
            memory_state["max_area"] = filters_area["max_area"]

        if "min_area" in filters_area:
            memory_state["min_area"] = filters_area["min_area"]

        if "bedrooms" in extracted_data:
            memory_state["bedrooms"] = extracted_data.get("bedrooms")

        if "developer_company" in extracted_data:
            memory_state["developer_company"] = extracted_data.get("developer_company")
            
        if "facilities_name" in extracted_data:
            memory_state["facilities_name"] = extracted_data.get("facilities_name")

        if "apartmentType" in extracted_data:
            memory_state["apartmentType"] = extracted_data.get("apartmentType")


        print("🔹 memory:", memory_state)
        # logging.info(f"memory: {memory_state}")


        print(f"🔹 تعداد املاک نهایی دریافت‌شده از API: {len(properties)}")
        # print(properties[:3])

        properties = sort_properties_by_developer_popularity(properties)

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
            <div style="text-align: right; direction: rtl; background-color: #e6f7ff; padding: 12px; border-radius: 10px; border: 1px solid #b3d8ff;">
                <p style="margin-top: 0; font-weight: bold; font-size: 16px;">👋 به چت‌بات مشاور املاک <span style="color: #000000;">شرکت ترونست</span> خوش آمدید!</p>
                <p style="margin: 6px 0;">من اینجا هستم تا به شما در پیدا کردن <b>بهترین املاک در دبی</b> کمک کنم. 🏡✨</p>
                <hr style="border-top: 1px solid #ccc;">
                <p style="margin-bottom: 0;"><b>چطور می‌توانم کمکتان کنم؟</b></p>
            </div>
            """
        # welcome_message = """
        # 👋 **به چت‌بات مشاور املاک شرکت ترونست خوش آمدید!**  
        # من اینجا هستم تا به شما در پیدا کردن **بهترین املاک در دبی** کمک کنم. 🏡✨  

        # **چطور می‌توانم کمکتان کنم؟**  
        # """
        return {"response": welcome_message}


    """ دریافت پیام کاربر و ارسال پاسخ از طریق هوش مصنوعی """
    bot_response = await real_estate_chatbot(request.message)
    # logging.info(f"bot_response: {bot_response}")
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
