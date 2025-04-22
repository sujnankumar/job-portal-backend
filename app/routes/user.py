from fastapi import APIRouter, Depends, Request, HTTPException
from app.utils.jwt_handler import verify_token
from app.db import db

router = APIRouter()

def get_current_user(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    user_data = verify_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or missing token")
    return user_data

@router.get("/me")
def get_me(user=Depends(get_current_user)):
    user_info = db.users.find_one({"email": user["email"]}, {"_id": 0, "password": 0})
    return user_info
