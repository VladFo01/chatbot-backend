from fastapi import WebSocket, WebSocketDisconnect, Depends, status
from jose import jwt, JWTError
from app.database import get_mongo_db
from app.schemas.chat import ChatMessage
from motor.motor_asyncio import AsyncIOMotorDatabase
import os
from typing import Dict
from datetime import datetime

SECRET_KEY = os.getenv("SECRET_KEY", "secret")
ALGORITHM = "HS256"

active_connections: Dict[str, WebSocket] = {}

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
            message = ChatMessage(sender=user["email"], message=data["message"], timestamp=datetime.utcnow())
            # Store message in MongoDB
            await db["chats"].update_one(
                {"user_id": user_id},
                {"$push": {"messages": message.model_dump()}},
                upsert=True
            )
            # Echo message back (or broadcast, if needed)
            message_dict = message.model_dump()
            # Convert datetime to ISO string for JSON serialization
            message_dict["timestamp"] = message_dict["timestamp"].isoformat()
            await websocket.send_json(message_dict)
    except WebSocketDisconnect:
        active_connections.pop(user_id, None) 