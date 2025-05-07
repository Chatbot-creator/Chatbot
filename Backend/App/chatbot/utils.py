"""
Utility functions for the chatbot.
"""

import uuid
from typing import Dict, List, Any
from fastapi import Request

def get_user_session(request: Request) -> str:
    """
    Get or create user session ID.
    
    Args:
        request: FastAPI request object
        
    Returns:
        User session ID
    """
    if "user_id" not in request.session:
        request.session["user_id"] = str(uuid.uuid4())  # Create a new UUID for the user
    print(f"🔹 User ID: {request.session['user_id']}")
    return request.session["user_id"]

def get_user_memory(request: Request) -> Dict:
    """
    Get or initialize user memory state.
    
    Args:
        request: FastAPI request object
        
    Returns:
        User memory state dictionary
    """
    if "memory_state" not in request.session:
        request.session["memory_state"] = {}
    return request.session["memory_state"]

def prepare_welcome_message() -> str:
    """
    Prepare welcome message for new chat sessions.
    
    Returns:
        Formatted welcome message
    """
    return """
👋 به چت‌بات مشاور املاک شرکت ترونست خوش آمدید!

من اینجا هستم تا به شما در پیدا کردن **بهترین املاک در دبی** کمک کنم. 🏡✨

---

**چطور می‌توانم کمکتان کنم؟**
""" 