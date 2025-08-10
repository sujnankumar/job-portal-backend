from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from app.db import db
from app.utils.jwt_handler import verify_token as decode_jwt
from bson import ObjectId
from datetime import datetime, timezone
from typing import List
import asyncio

router = APIRouter()

# Helper to serialize MongoDB notification
def serialize_notification(notification):
    notification["id"] = str(notification["_id"])
    del notification["_id"]
    if "time" in notification and notification["time"]:
        t = notification["time"]
        if isinstance(t, datetime):
            # Assume naive datetimes are UTC
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            # Normalize to UTC and output RFC3339 with Z
            t = t.astimezone(timezone.utc)
            notification["time"] = t.isoformat().replace("+00:00", "Z")
        elif isinstance(t, str):
            # If string lacks timezone info, treat as UTC and append Z
            if not (t.endswith("Z") or "+" in t or t.rfind("-") > 9):
                notification["time"] = t + "Z"
            else:
                notification["time"] = t
        else:
            notification["time"] = None
    else:
        notification["time"] = None
    return notification

# Dependency to get current user from JWT
def get_current_user(token: str):
    try:
        payload = decode_jwt(token)
        return payload
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

@router.get("/", response_model=List[dict])
def get_notifications(token: str):
    user = get_current_user(token)
    notifications = list(db.notifications.find({"user_id": user["user_id"]}).sort("time", -1))
    return [serialize_notification(n) for n in notifications]

@router.post("/mark-read/{notification_id}")
def mark_notification_read(notification_id: str, token: str):
    user = get_current_user(token)
    result = db.notifications.update_one(
        {"_id": ObjectId(notification_id), "user_id": user["user_id"]},
        {"$set": {"read": True}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"success": True}

@router.post("/mark-all-read")
def mark_all_notifications_read(token: str):
    user = get_current_user(token)
    db.notifications.update_many({"user_id": user["user_id"]}, {"$set": {"read": True}})
    return {"success": True}

# --- WebSocket for real-time notifications ---
class NotificationManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: str):
        self.active_connections.pop(user_id, None)

    async def send_notification(self, user_id: str, notification: dict):
        ws = self.active_connections.get(user_id)
        if ws:
            await ws.send_json(notification)

notification_manager = NotificationManager()

@router.websocket("/ws")
async def websocket_notifications(websocket: WebSocket, token: str):
    user = get_current_user(token)
    user_id = user["user_id"]
    await notification_manager.connect(user_id, websocket)
    try:
        while True:
            try:
                # Wait for a message from the client, but don't close if idle
                await asyncio.wait_for(websocket.receive_text(), timeout=60)
            except asyncio.TimeoutError:
                # Send a ping to keep the connection alive
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        notification_manager.disconnect(user_id)
