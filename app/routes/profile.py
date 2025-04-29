from fastapi import APIRouter, Request, HTTPException, Header, UploadFile, File, Response
from app.functions import auth_functions
from app.utils.jwt_handler import verify_token
from app.db import db
from gridfs import GridFS
from bson import ObjectId

router = APIRouter()
gfs = GridFS(db)

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

@router.put("/upload_cover_photo")
async def upload_cover_photo(authorization: str = Header(None), file: UploadFile = File(...)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user_email = payload.get("email")
    if not user_email:
        raise HTTPException(status_code=400, detail="Could not retrieve user email from token")
    user = db.users.find_one({"email": user_email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # Remove old cover photo if exists
    if user.get("cover_photo_id"):
        try:
            gfs.delete(ObjectId(user["cover_photo_id"]))
        except Exception:
            pass
    file_bytes = await file.read()
    file_id = gfs.put(file_bytes, filename=file.filename, content_type=file.content_type)
    db.users.update_one({"email": user_email}, {"$set": {"cover_photo_id": str(file_id)}})
    return {"msg": "Cover photo uploaded", "cover_photo_id": str(file_id)}

@router.get("/cover_photo")
async def get_cover_photo(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user_email = payload.get("email")
    if not user_email:
        raise HTTPException(status_code=400, detail="Could not retrieve user email from token")
    user = db.users.find_one({"email": user_email})
    if not user or not user.get("cover_photo_id"):
        raise HTTPException(status_code=404, detail="Cover photo not found")
    file_id = user["cover_photo_id"]
    file = gfs.get(ObjectId(file_id))
    return Response(content=file.read(), media_type=file.content_type, headers={"Content-Disposition": f"inline; filename={file.filename}"})

@router.put("/upload_profile_photo")
async def upload_profile_photo(authorization: str = Header(None), file: UploadFile = File(...)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user_email = payload.get("email")
    if not user_email:
        raise HTTPException(status_code=400, detail="Could not retrieve user email from token")
    user = db.users.find_one({"email": user_email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # Remove old profile photo if exists
    if user.get("profile_photo_id"):
        try:
            gfs.delete(ObjectId(user["profile_photo_id"]))
        except Exception:
            pass
    file_bytes = await file.read()
    file_id = gfs.put(file_bytes, filename=file.filename, content_type=file.content_type)
    db.users.update_one({"email": user_email}, {"$set": {"profile_photo_id": str(file_id)}})
    return {"msg": "Profile photo uploaded", "profile_photo_id": str(file_id)}

@router.get("/profile_photo")
async def get_profile_photo(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user_email = payload.get("email")
    if not user_email:
        raise HTTPException(status_code=400, detail="Could not retrieve user email from token")
    user = db.users.find_one({"email": user_email})
    if not user or not user.get("profile_photo_id"):
        raise HTTPException(status_code=404, detail="Profile photo not found")
    file_id = user["profile_photo_id"]
    file = gfs.get(ObjectId(file_id))
    return Response(content=file.read(), media_type=file.content_type, headers={"Content-Disposition": f"inline; filename={file.filename}"})
