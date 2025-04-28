from fastapi import APIRouter, Depends, HTTPException, Request
from app.functions import auth_functions
from app.utils.jwt_handler import verify_token

router = APIRouter()

@router.post("/register")
async def register(request: Request):
    data = await request.json()
    required_fields = ["user_type", "first_name", "last_name", "email", "password"]
    
    for field in required_fields:
        if not data.get(field):
            raise HTTPException(status_code=400, detail=f"{field} is required")
        
    if data["user_type"] not in ["job_seeker", "employer"]:
        raise HTTPException(status_code=400, detail="Invalid user type")  
    
    if auth_functions.is_email_registered(data["email"]):
        raise HTTPException(status_code=400, detail="Email is already registered")

    return auth_functions.register_user(data)

@router.post("/login")
async def login(request: Request):
    data = await request.json()
    
    if not data.get("email") or not data.get("password"):
        raise HTTPException(status_code=400, detail="Email and password are required")
    
    result = auth_functions.login_user(data["email"], data["password"])
    
    if not result:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    return result


@router.post("/onboarding")
async def onboarding(request: Request):
    data = await request.json()
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    
    token = auth_header.split("Bearer ")[1]
    user_data = verify_token(token)
    print(data)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    
    result = auth_functions.onboard_user(user_data, data)
    
    if not result:
        raise HTTPException(status_code=401, detail="Could not complete onboarding")
    
    return result