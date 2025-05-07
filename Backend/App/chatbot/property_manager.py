"""
Property data management functions.
Handles fetching and filtering properties from external API.
"""

import os
import requests
from datetime import datetime
from typing import Dict, List, Optional, Any

# API configuration
ESTATY_API_KEY = os.getenv("ESTATY_API_KEY")
ESTATY_API_URL = "https://panel.estaty.app/api/v1"

# Headers for authentication
HEADERS = {
    "App-Key": ESTATY_API_KEY,
    "Content-Type": "application/json"
}

def fetch_all_properties() -> Dict[str, Any]:
    """
    Fetch all properties from the Estaty API.
    Returns a dictionary with properties and districts.
    """
    print("🚀 Starting property fetch from API...")
    all_properties = []
    districts_with_ids = {}  # Dictionary for districts
    page = 1
    limit = 100
    
    while True:
        print(f"📄 Processing page {page}...")
        res = requests.post(
            f"{ESTATY_API_URL}/getProperties", 
            json={"page": page, "limit": limit}, 
            headers=HEADERS
        )
        json_data = res.json()
        current_data = json_data.get("properties", {}).get("data", [])
        
        if not current_data:
            break
            
        all_properties.extend(current_data)
        
        # Extract district name and ID from each property
        for prop in current_data:
            district_info = prop.get("district")
            if district_info and isinstance(district_info, dict):
                name = district_info.get("name", "").strip()
                district_id = district_info.get("id")
                if name and district_id and name not in districts_with_ids:
                    districts_with_ids[name] = district_id
        
        if len(current_data) < limit:
            print("✅ Reached the end of the list.")
            break
            
        page += 1
    
    print(f"✅ Total fetched properties: {len(all_properties)}")
    print(f"✅ Total districts: {len(districts_with_ids)}")
    
    # Return a dictionary containing both
    return {
        "properties": all_properties,
        "districts": districts_with_ids
    }

def filter_properties(filters: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Filter properties based on user criteria.
    
    Args:
        filters: Dictionary containing filter criteria
        
    Returns:
        List of filtered properties
    """
    print("🔹 Filters sent to API:", filters)
    
    # Make request to the API
    response = requests.post(
        f"{ESTATY_API_URL}/filter", 
        json=filters, 
        headers=HEADERS
    )
    response_data = response.json()
    
    # Extract filter parameters
    district_filter = filters.get("district")
    if district_filter:
        district_filter = district_filter.lower()
        
    max_price = filters.get("max_price")
    min_price = filters.get("min_price")
    
    # Filter properties based on sales status, district, and price
    filtered_properties = [
        property for property in response_data.get("properties", [])
        if property.get("sales_status", {}).get("name", "").lower() in ["available"] and
           (district_filter is None or 
            (property.get("district") and property["district"].get("name", "").lower() == district_filter)) and
           (max_price is None or 
            (property.get("low_price") is not None and property["low_price"] <= max_price)) and
           (min_price is None or 
            (property.get("low_price") is not None and property["low_price"] >= min_price))
    ]
    
    print(f"🔹 Number of available properties after filtering: {len(filtered_properties)}")
    return filtered_properties 