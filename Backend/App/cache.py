from cachetools import TTLCache
from datetime import timedelta

# Create cache with 12 hour TTL (Time To Live)
CACHE_TTL = timedelta(hours=12).total_seconds()
property_cache = TTLCache(maxsize=100, ttl=CACHE_TTL)

def get_cached_data(cache_key: str):
    """Get data from cache"""
    return property_cache.get(cache_key)

def set_cached_data(cache_key: str, data):
    """Set data in cache"""
    property_cache[cache_key] = data

def clear_cache():
    """Clear all cached data"""
    property_cache.clear()
