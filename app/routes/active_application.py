from fastapi import APIRouter, Depends, HTTPException, Request
from app.utils.jwt_handler import verify_token
from app.db import db

router = APIRouter()

def get_current_user(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    
    token = auth_header.split("Bearer ")[1]
    user_data = verify_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_data

@router.get("/applications/active")
def get_active_applications(user=Depends(get_current_user)):
    user_id = user.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid user data")

    active_applications = list(db.applications.find(
        {
            "user_id": user_id,
            "status": {"$nin": ["Rejected", "Selected"]}
        },
        {"_id": 0}
    ))

    return {"active_applications": active_applications}
