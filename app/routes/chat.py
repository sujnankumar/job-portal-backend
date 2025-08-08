from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, Header, Response
from app.utils.jwt_handler import verify_token
from app.db import db
from gridfs import GridFS
from bson import ObjectId
from typing import Dict, List
import uuid
from app.utils.timezone_utils import get_ist_now

router = APIRouter()

gfs = GridFS(db)

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
            print("messsage came")
            data = await websocket.receive_json()
            # Save message to DB
            message = {
                "id": str(uuid.uuid4()),
                "sender_id": user_id,
                "recipient_id": recipient_id,
                "text": data["text"],
                "time": get_ist_now().isoformat()
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

@router.get("/chat/profile-photo/{user_id}")
async def get_user_profile_photo(user_id: str):
    """
    Get profile photo for a user (both job seekers and employers) for chat interface
    """
    try:
        # First, get user info to determine their role and profile photo
        user = db.users.find_one({"user_id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        profile_photo_id = None
        
        # Check user role and get appropriate profile photo
        if user.get("user_type") == "employer":
            # For employers, get their company logo as profile photo
            company_id = user.get("company_id")
            if company_id:
                company = db.companies.find_one({"company_id": company_id})
                if company and company.get("logo"):
                    profile_photo_id = company.get("logo")
        else:
            # For job seekers, try different profile photo field names
            profile_photo_id = user.get("profile_photo_id")
    
        # Debug logging
        print(f"User {user_id}: type={user.get('user_type')}, profile_photo_id={profile_photo_id}")
        print(f"User fields: {list(user.keys())}")
        
        # If we have a profile photo ID, fetch it from GridFS
        if profile_photo_id:
            try:
                file = gfs.get(ObjectId(profile_photo_id))
                return Response(
                    content=file.read(), 
                    media_type=file.content_type, 
                    headers={"Content-Disposition": f"inline; filename={file.filename}"}
                )
            except Exception as e:
                print(f"GridFS error for {profile_photo_id}: {e}")
                pass
        
        # Return default profile photo for the user type
        raise HTTPException(status_code=404, detail="Profile photo not found")
            
    except Exception as e:
        print(f"Error in get_user_profile_photo: {e}")
        raise HTTPException(status_code=404, detail="Profile photo not found")
