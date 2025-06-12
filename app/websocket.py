from fastapi import WebSocket, WebSocketDisconnect, Depends, status
from jose import jwt, JWTError
from app.database import get_mongo_db
from app.schemas.chat import ChatMessage
from app.services.llm_service import llm_service
from motor.motor_asyncio import AsyncIOMotorDatabase
import os
import logging
from typing import Dict, List
from datetime import datetime

SECRET_KEY = os.getenv("SECRET_KEY", "secret")
ALGORITHM = "HS256"

logger = logging.getLogger(__name__)
active_connections: Dict[str, WebSocket] = {}

# Specific phrases that typically don't need document context
SIMPLE_PHRASES = [
    "hi", "hello", "hey", "thanks", "thank you", "bye", "goodbye", 
    "how are you", "what's up", "good morning", "good afternoon", 
    "good evening", "nice to meet you", "please", "ok", "okay", "yes", "no"
]

async def _should_use_rag(user_message: str, message_type: str) -> bool:
    """
    Intelligently determine whether to use RAG based on the user's message.
    
    Args:
        user_message: The user's input message
        message_type: Explicit type from client ('chat', 'rag', 'no-rag')
        
    Returns:
        bool: True if RAG should be used, False otherwise
    """
    # Explicit override from client
    if message_type == "no-rag":
        return False
    if message_type == "rag":
        return True
        
    # Convert to lowercase for analysis
    message_lower = user_message.lower().strip()
    
    # Skip RAG for very short messages
    if len(message_lower) <= 1:
        return False
    
    # Special case: single question words should still not use RAG
    if message_lower in ["what", "what?", "how", "how?", "why", "why?", "when", "when?", "where", "where?", "who", "who?", "?"]:
        return False
    
    # Skip RAG for common greetings and simple responses (exact matches or at start)
    if (message_lower in SIMPLE_PHRASES or 
        any(message_lower.startswith(phrase) for phrase in SIMPLE_PHRASES)):
        return False
    
    # FIRST: Check for system/architecture questions (these should use RAG)
    system_keywords = ["this system", "the system", "architecture", "features", "deployment", "pipeline"]
    if any(phrase in message_lower for phrase in system_keywords):
        return True
    
    # THEN: Skip RAG for questions about the bot itself (personal identity)
    bot_identity_questions = ["who are you", "what are you", "what can you do", "how do you work"]
    if any(question in message_lower for question in bot_identity_questions):
        return False
    
    # Use RAG for questions (indicated by question words or question marks)
    question_indicators = ["what", "how", "why", "when", "where", "who", "which", "can", "could", "would", "should", "is", "are", "does", "do", "did", "?"]
    if any(indicator in message_lower for indicator in question_indicators):
        return True
    
    # Use RAG for requests for information
    info_requests = ["tell me", "explain", "describe", "show me", "find", "search", "look for", "about"]
    if any(request in message_lower for request in info_requests):
        return True
    
    # Default to using RAG for longer, substantive messages
    if len(message_lower) > 20:
        return True
        
    # Default to no RAG for short, unclear messages
    return False

async def get_current_user(websocket: WebSocket, db: AsyncIOMotorDatabase):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if not email:
            raise JWTError()
        user = await db["users"].find_one({"email": email})
        if not user:
            raise JWTError()
        return user
    except JWTError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None

async def websocket_endpoint(websocket: WebSocket, db: AsyncIOMotorDatabase):
    user = await get_current_user(websocket, db)
    if not user:
        return
    user_id = str(user["_id"])
    await websocket.accept()
    active_connections[user_id] = websocket
    try:
        while True:
            data = await websocket.receive_json()
            user_message = data.get("message", "")
            message_type = data.get("type", "chat")  # chat or rag
            
            # Create user message
            user_chat_message = ChatMessage(
                sender=user["email"], 
                message=user_message, 
                timestamp=datetime.utcnow()
            )
            
            # Store user message in MongoDB
            await db["chats"].update_one(
                {"user_id": user_id},
                {"$push": {"messages": user_chat_message.model_dump()}},
                upsert=True
            )
            
            # Send user message back to confirm receipt
            user_message_dict = user_chat_message.model_dump()
            user_message_dict["timestamp"] = user_message_dict["timestamp"].isoformat()
            await websocket.send_json(user_message_dict)
            
            # Get chat history for context
            chat_doc = await db["chats"].find_one({"user_id": user_id})
            chat_history = chat_doc.get("messages", []) if chat_doc else []
            
            # Generate AI response
            try:
                # Always try RAG first - search for relevant context automatically
                # Only skip RAG if explicitly requested or if it's a greeting/simple response
                should_use_rag = await _should_use_rag(user_message, message_type)
                
                logger.info(f"Processing message: '{user_message[:50]}...' | RAG: {should_use_rag} | Type: {message_type}")
                
                llm_response = await llm_service.generate_response(
                    user_message, 
                    chat_history=chat_history[-20:],  # Last 20 messages for context
                    use_rag=should_use_rag
                )
                
                # Create AI response message
                ai_response_content = llm_response["response"]
                
                # Add context indicator and sources if available
                if should_use_rag and llm_response.get("context_used"):
                    print(llm_response["sources"])
                    if llm_response.get("sources"):
                        ai_response_content += "\n\n📚 **Sources:**\n"
                        for i, source in enumerate(llm_response["sources"][:3], 1):
                            ai_response_content += f"{i}. {source['filename']}\n"
                    else:
                        ai_response_content += "\n\n💡 *I searched your documents but didn't find specific relevant information for this question.*"
                elif should_use_rag and not llm_response.get("context_used"):
                    ai_response_content += "\n\n📄 *No relevant documents found - answering from general knowledge.*"
                
                ai_message = ChatMessage(
                    sender="assistant",
                    message=ai_response_content,
                    timestamp=datetime.utcnow()
                )
                
                # Store AI message in MongoDB
                await db["chats"].update_one(
                    {"user_id": user_id},
                    {"$push": {"messages": ai_message.model_dump()}},
                    upsert=True
                )
                
                # Send AI response
                ai_message_dict = ai_message.model_dump()
                ai_message_dict["timestamp"] = ai_message_dict["timestamp"].isoformat()
                ai_message_dict["llm_metadata"] = {
                    "sources": llm_response.get("sources", []),
                    "context_used": llm_response.get("context_used", False),
                    "model": llm_response.get("model", "unknown")
                }
                await websocket.send_json(ai_message_dict)
                
            except Exception as e:
                logger.error(f"Error generating AI response: {e}")
                error_message = ChatMessage(
                    sender="assistant",
                    message="I apologize, but I encountered an error. Please try again.",
                    timestamp=datetime.utcnow()
                )
                error_dict = error_message.model_dump()
                error_dict["timestamp"] = error_dict["timestamp"].isoformat()
                await websocket.send_json(error_dict)
                
    except WebSocketDisconnect:
        active_connections.pop(user_id, None) 