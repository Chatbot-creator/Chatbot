"""
Core chatbot functionality.
Handles user interactions and generates responses.
"""

import os
import json
import asyncio
import random
from typing import Dict, List, Any, Optional
from openai import AsyncOpenAI
from dotenv import load_dotenv
from .property_manager import filter_properties

# Load environment variables
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
client = AsyncOpenAI(api_key=api_key)  # Using async OpenAI client

async def real_estate_chatbot(
    user_message: str,
    memory_state: Dict,
    types: Dict,
    last_properties_list: List,
    session: Dict,
    current_property_index: int,
    property_name_to_id: Dict,
    property_ordered_list: List,
    selected_properties: List,
    comp_properties: List,
    just_answered_questions: bool
) -> str:
    """
    Process user message and generate chatbot response.
    
    Args:
        user_message: The message from the user
        memory_state: Storage for conversation context
        types: Types information
        last_properties_list: List of recently shown properties
        session: User session data
        current_property_index: Current index in properties list
        property_name_to_id: Mapping of property names to IDs
        property_ordered_list: Ordered list of properties
        selected_properties: Properties selected by user
        comp_properties: Properties for comparison
        just_answered_questions: Flag indicating if last message was a question
        
    Returns:
        Chatbot response string
    """
    # Check if we need to update memory state
    if "memory_state" not in session:
        session["memory_state"] = {}
    if "types" not in session:
        session["types"] = {}
    if "last_properties_list" not in session:
        session["last_properties_list"] = []
    if "comp_properties" not in session:
        session["comp_properties"] = []
    if "current_property_index" not in session:
        session["current_property_index"] = 0
    if "property_name_to_id" not in session:
        session["property_name_to_id"] = {}
    if "property_ordered_list" not in session:
        session["property_ordered_list"] = []
    if "selected_properties" not in session:
        session["selected_properties"] = []
    if "just_answered_questions" not in session:
        session["just_answered_questions"] = True

    # Default response for now (in a real implementation, would use OpenAI call)
    # This is just a placeholder - the actual implementation would use the OpenAI API
    try:
        # Process user input with OpenAI
        messages = [
            {"role": "system", "content": "You are a helpful real estate assistant for properties in Dubai."},
            {"role": "user", "content": user_message}
        ]
        
        response = await client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            max_tokens=1000,
            temperature=0.7
        )
        
        bot_response = response.choices[0].message.content
        
        # Update session with any changes from processing
        session["memory_state"] = memory_state
        session["types"] = types
        session["last_properties_list"] = last_properties_list
        session["comp_properties"] = comp_properties
        session["current_property_index"] = current_property_index
        session["property_name_to_id"] = property_name_to_id
        session["property_ordered_list"] = property_ordered_list
        session["selected_properties"] = selected_properties
        session["just_answered_questions"] = just_answered_questions
        
        return bot_response
    
    except Exception as e:
        print(f"Error in chatbot: {e}")
        return "متأسفانه مشکلی در پردازش پیام شما رخ داد. لطفاً دوباره تلاش کنید."

def simplify_properties(properties: List[Dict]) -> List[Dict]:
    """
    Simplify property data for safe storage in session.
    
    Args:
        properties: List of property dictionaries
        
    Returns:
        Simplified list with just ID and title
    """
    if isinstance(properties, list):
        return [{"id": p.get("id"), "title": p.get("title")} for p in properties]
    return properties 