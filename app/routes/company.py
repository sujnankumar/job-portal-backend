from fastapi import APIRouter, Request, HTTPException, Depends, Response
from app.functions import company_functions, auth_functions
from app.utils.jwt_handler import verify_token
from gridfs import GridFS
from bson import ObjectId
from app.db import db

router = APIRouter()

gfs = GridFS(db)

def get_current_user(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    user_data = verify_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or missing token")
    return user_data

@router.get("/details")
async def get_company_by_user(user=Depends(get_current_user)):
    user_data = auth_functions.get_user_by_id(user.get("user_id"))
    company = company_functions.get_company_by_id(user_data.get("company_id"))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company

@router.get("/all")
async def get_all_companies():
    return company_functions.get_all_companies()

@router.get("/{company_id}")
async def get_company_by_id(company_id: str):
    company = company_functions.get_company_by_id(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company

@router.get("/logo/{logo_id}")
async def get_company_logo(logo_id: str):
    try:
        file = gfs.get(ObjectId(logo_id))
        return Response(content=file.read(), media_type=file.content_type, headers={"Content-Disposition": f"inline; filename={file.filename}"})
    except Exception:
        raise HTTPException(status_code=404, detail="Logo not found")
    
@router.get("/logo/company/{company_id}")
async def get_logo_by_company_id(company_id: str):
    company = company_functions.get_company_by_id(company_id)
    if not company or not company.get("logo"):
        raise HTTPException(status_code=404, detail="Company or logo not found")
    try:
        file = gfs.get(ObjectId(company["logo"]))
        return Response(content=file.read(), media_type=file.content_type, headers={"Content-Disposition": f"inline; filename={file.filename}"})
    except Exception:
        raise HTTPException(status_code=404, detail="Logo not found")