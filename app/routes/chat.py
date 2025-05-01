from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, Header
from app.utils.jwt_handler import verify_token
from app.db import db
from typing import Dict, List
import uuid
from datetime import datetime

router = APIRouter()

# In-memory connection manager for demo (use Redis or DB pub/sub for production)
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)

    def disconnect(self, user_id: str, websocket: WebSocket):
        if user_id in self.active_connections:
            self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

    async def send_personal_message(self, user_id: str, message: dict):
        for ws in self.active_connections.get(user_id, []):
            await ws.send_json(message)

    async def broadcast(self, user_ids: List[str], message: dict):
        for user_id in user_ids:
            await self.send_personal_message(user_id, message)

manager = ConnectionManager()

def get_user_id_from_token(token: str):
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload["user_id"]

@router.websocket("/ws/chat/{recipient_id}")
async def websocket_chat(websocket: WebSocket, recipient_id: str, token: str = None):
    # token should be passed as a query param: ws://.../ws/chat/{recipient_id}?token=xxx
    if not token:
        await websocket.close(code=1008)
        return
    try:
        user_id = get_user_id_from_token(token)
    except Exception:
        await websocket.close(code=1008)
        return
    await manager.connect(user_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            # Save message to DB
            message = {
                "id": str(uuid.uuid4()),
                "sender_id": user_id,
                "recipient_id": recipient_id,
                "text": data["text"],
                "time": datetime.utcnow().isoformat()
            }
            db.chats.insert_one(message)
            # Remove _id (ObjectId) before sending to client
            message.pop("_id", None)
            # Send to recipient if online
            await manager.send_personal_message(recipient_id, message)
            # Echo to sender
            await manager.send_personal_message(user_id, message)
    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)

@router.get("/chat/recipients")
async def get_chat_recipients(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1]
    user_id = get_user_id_from_token(token)
    # Find all unique chat partners
    pipeline = [
        {"$match": {"$or": [{"sender_id": user_id}, {"recipient_id": user_id}]}},
        {"$project": {"other": {"$cond": [{"$eq": ["$sender_id", user_id]}, "$recipient_id", "$sender_id"]}}},
        {"$group": {"_id": "$other"}}
    ]
    partners = [doc["_id"] for doc in db.chats.aggregate(pipeline)]
    users = list(db.users.find({"user_id": {"$in": partners}}, {"user_id": 1, "first_name": 1, "last_name": 1, "avatar": 1}))
    result = []
    for u in users:
        last_msg = db.chats.find_one({"$or": [{"sender_id": user_id, "recipient_id": u["user_id"]}, {"sender_id": u["user_id"], "recipient_id": user_id}]}, sort=[("time", -1)])
        result.append({
            "id": u["user_id"],
            "name": f"{u.get('first_name', '')} {u.get('last_name', '')}",
            "avatar": u.get("avatar", "/placeholder-user.jpg"),
            "lastMessage": last_msg["text"] if last_msg else "",
            "lastMessageTime": last_msg["time"][-8:] if last_msg else ""
        })
    return result

@router.get("/chat/messages/{recipient_id}")
async def get_chat_messages(recipient_id: str, authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1]
    user_id = get_user_id_from_token(token)
    # Get all messages between user and recipient
    messages = list(db.chats.find({
        "$or": [
            {"sender_id": user_id, "recipient_id": recipient_id},
            {"sender_id": recipient_id, "recipient_id": user_id}
        ]
    }, {"_id": 0}))
    return messages
