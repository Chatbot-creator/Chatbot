"""
Router for chatbot API endpoints.
"""

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from typing import Dict, List, Any, Optional
import json
from sqlalchemy.orm import Session

from .schemas import ChatMessage, ChatResponse
from .chatbot import real_estate_chatbot, simplify_properties
from .utils import get_user_session, get_user_memory, prepare_welcome_message
from .models import ChatSession, ChatMessage as DBChatMessage, PropertyPreference
from .crud import (
    get_chat_session, create_chat_session, update_chat_session,
    get_chat_messages, create_chat_message,
    get_property_preference, create_or_update_property_preference
)
from App.database import get_db
from .cache import (
    property_cache, 
    chat_session_cache, 
    chat_history_session_cache,
    user_filters_cache,
    fetch_and_cache_properties,
    start_scheduler
)

# Create router
router = APIRouter(prefix="/chatbot", tags=["chatbot"])

@router.get("/properties")
def get_cached_properties():
    """
    Get all cached properties and districts.
    
    Returns:
        JSON with properties, districts, and counts
    """
    data = property_cache.get("all")
    if data is None:
        return JSONResponse(
            content={"detail": "No data cached yet."}, 
            status_code=404
        )
    
    return {
        "properties": data["properties"],
        "districts": data["districts"],
        "property_count": len(data["properties"]),
        "district_count": len(data["districts"])
    }

@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: Request, 
    chat_message: ChatMessage,
    user_id: str = Depends(get_user_session),
    db: Session = Depends(get_db)
):
    """
    Process chat message and return response.
    
    Args:
        request: FastAPI request object
        chat_message: User message
        user_id: User session ID
        db: Database session
        
    Returns:
        Chatbot response and chat history
    """
    # Initialize session data
    session = request.session
    
    # Load cached session if available
    if user_id in chat_session_cache:
        full_cached_session = chat_session_cache[user_id]
        if isinstance(full_cached_session, dict):
            for key, value in full_cached_session.items():
                session[key] = value
            print("✅ Cached session loaded.")
        else:
            print("⚠️ Cached session is not dict, skipping load.")
    else:
        print("ℹ️ No cached session found, starting fresh.")
    
    # Get session data or initialize
    memory_state = session.get("memory_state", {})
    types = session.get("types", {})
    last_properties_list = session.get("last_properties_list", [])
    comp_properties = session.get("comp_properties", [])
    current_property_index = session.get("current_property_index", 0)
    property_name_to_id = session.get("property_name_to_id", {})
    property_ordered_list = session.get("property_ordered_list", [])
    selected_properties = session.get("selected_properties", [])
    just_answered_questions = session.get("just_answered_questions", True)
    
    # Get or initialize chat history
    chat_history = chat_history_session_cache.get(user_id, [])
    if user_id not in chat_history_session_cache:
        chat_history_session_cache[user_id] = []
        print("✅ Chat history cache initialized.")
    
    # Get user message
    user_message = chat_message.message.strip()
    print(f"🔹 User Message: {user_message}")
    
    # Get or create DB chat session
    db_chat_session = get_chat_session(db, user_id)
    if not db_chat_session:
        db_chat_session = create_chat_session(db, user_id, {
            "memory_state": memory_state,
            "types": types
        })
    
    # Handle empty message with welcome response
    if not user_message:
        welcome_message = prepare_welcome_message()
        return {
            "response": welcome_message, 
            "user_id": user_id, 
            "chat_history": chat_history[-10:]
        }
    
    # Save user message to chat history and database
    chat_history.append({"user": user_message})
    create_chat_message(db, db_chat_session.id, user_message, is_user=True)
    
    # Process message and get chatbot response
    bot_response = await real_estate_chatbot(
        user_message,
        memory_state,
        types,
        last_properties_list,
        session,
        current_property_index,
        property_name_to_id,
        property_ordered_list,
        selected_properties,
        comp_properties,
        just_answered_questions
    )
    
    # Add bot response to chat history and database
    chat_history.append({"bot": bot_response})
    create_chat_message(db, db_chat_session.id, bot_response, is_user=False)
    chat_history_session_cache[user_id] = chat_history
    
    # Update database chat session with latest data
    session_data = {
        "memory_state": session.get("memory_state", {}),
        "types": session.get("types", {}),
        "current_property_index": session.get("current_property_index", 0),
        "property_name_to_id": session.get("property_name_to_id", {}),
        "property_ordered_list": session.get("property_ordered_list", []),
        "just_answered_questions": session.get("just_answered_questions", True)
    }
    update_chat_session(db, db_chat_session, session_data)
    
    # Save session data to cache
    chat_session_cache[user_id] = session_data
    
    # Update property preferences in database if available
    filters_user = memory_state
    if filters_user:
        user_filters_cache[user_id] = filters_user
        # Extract relevant property filters
        property_preferences = {}
        for key in ["district", "min_price", "max_price", "bedrooms", "bathrooms", "property_type"]:
            if key in filters_user:
                property_preferences[key] = filters_user[key]
                
        if property_preferences:
            create_or_update_property_preference(db, user_id, property_preferences)
    
    # Create simplified version of session for logging
    safe_session = dict(session)
    
    # Simplify property data in session
    if "selected_properties" in safe_session:
        safe_session["selected_properties"] = simplify_properties(safe_session["selected_properties"])
    if "last_properties_list" in safe_session:
        safe_session["last_properties_list"] = simplify_properties(safe_session["last_properties_list"])
    if "comp_properties" in safe_session:
        safe_session["comp_properties"] = simplify_properties(safe_session["comp_properties"])
    
    print(f"✅ Session Data After Saving (Light): {safe_session}")
    
    # Return response
    return {
        "response": bot_response, 
        "user_id": user_id, 
        "chat_history": chat_history[-10:]
    }

@router.get("/history/{user_id}")
def get_user_chat_history(user_id: str, db: Session = Depends(get_db)):
    """
    Get chat history for a user from database.
    
    Args:
        user_id: User ID
        db: Database session
        
    Returns:
        Chat history from database
    """
    # Get the chat session
    db_chat_session = get_chat_session(db, user_id)
    if not db_chat_session:
        raise HTTPException(status_code=404, detail="Chat history not found")
    
    # Get messages
    messages = get_chat_messages(db, db_chat_session.id)
    
    # Format messages for response
    formatted_messages = []
    for msg in messages:
        if msg.is_user:
            formatted_messages.append({"user": msg.message})
        else:
            formatted_messages.append({"bot": msg.message})
    
    return {
        "user_id": user_id,
        "chat_history": formatted_messages,
        "session_data": db_chat_session.session_data
    }

@router.get("/preferences/{user_id}")
def get_user_preferences(user_id: str, db: Session = Depends(get_db)):
    """
    Get property preferences for a user.
    
    Args:
        user_id: User ID
        db: Database session
        
    Returns:
        User property preferences
    """
    preferences = get_property_preference(db, user_id)
    if not preferences:
        raise HTTPException(status_code=404, detail="No preferences found for this user")
    
    return {
        "user_id": user_id,
        "preferences": {
            "district": preferences.district,
            "min_price": preferences.min_price,
            "max_price": preferences.max_price,
            "bedrooms": preferences.bedrooms,
            "bathrooms": preferences.bathrooms,
            "property_type": preferences.property_type
        }
    } 