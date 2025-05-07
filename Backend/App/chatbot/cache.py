"""
Cache management for the chatbot.
Handles caching of properties and user sessions.
"""

from cachetools import TTLCache
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers import SchedulerAlreadyRunningError
from .property_manager import fetch_all_properties

# Cache configuration with TTL (Time To Live)
property_cache = TTLCache(maxsize=1, ttl=86400)  # 24 hours
properties_cache = TTLCache(maxsize=10000, ttl=3600)  # 1 hour
user_filters_cache = TTLCache(maxsize=10000, ttl=3600)  # 1 hour
chat_session_cache = TTLCache(maxsize=10000, ttl=3600)  # 1 hour
chat_history_session_cache = TTLCache(maxsize=10000, ttl=3600)  # 1 hour

def fetch_and_cache_properties():
    """
    Fetch properties from API and update the cache.
    """
    result = fetch_all_properties()
    property_cache["all"] = result
    print(f"🕓 Property cache updated at {datetime.now()}")
    print(f"✅ {len(result['properties'])} properties cached.")
    print(f"✅ {len(result['districts'])} districts cached.")

scheduler = BackgroundScheduler()

def start_scheduler():
    """
    Start the background scheduler for periodic cache updates.
    
    Now checks if scheduler is already running to avoid SchedulerAlreadyRunningError.
    """
    try:
        if not scheduler.running:
            scheduler.add_job(fetch_and_cache_properties, "interval", hours=24)
            scheduler.start()
            print("📅 Scheduler started - updating property cache every 24h.")
        else:
            print("📅 Scheduler is already running.")
    except SchedulerAlreadyRunningError:
        print("📅 Scheduler is already running.") 