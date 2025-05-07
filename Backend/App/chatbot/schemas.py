"""
Pydantic schemas for data validation.
"""

from pydantic import BaseModel
from typing import Dict, List, Optional, Any

class ChatMessage(BaseModel):
    """Schema for chat message request."""
    message: str

class ChatResponse(BaseModel):
    """Schema for chat response."""
    response: str
    user_id: str
    chat_history: List[Dict[str, str]]

class PropertyFilter(BaseModel):
    """Schema for property filter."""
    district: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    
class Property(BaseModel):
    """Schema for property data."""
    id: str
    title: str
    description: Optional[str] = None
    low_price: Optional[float] = None
    district: Optional[Dict[str, Any]] = None
    sales_status: Optional[Dict[str, Any]] = None
    
class PropertiesResponse(BaseModel):
    """Schema for properties list response."""
    properties: List[Property]
    districts: Dict[str, str]
    property_count: int
    district_count: int 