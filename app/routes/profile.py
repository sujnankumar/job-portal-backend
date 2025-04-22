from fastapi import APIRouter, Request, HTTPException, Header
from app.functions import auth_functions
from app.utils.jwt_handler import verify_token

router = APIRouter()

@router.put("/update_profile")
async def update_profile(request: Request, authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    data = await request.json()
    user_email = payload.get("email")
    if not user_email:
        raise HTTPException(status_code=400, detail="Could not retrieve user email from token")
    updated_profile = auth_functions.update_user_profile_by_email(user_email, data)
    if not updated_profile:
        raise HTTPException(status_code=404, detail="Profile not found or update failed")
    return updated_profile

