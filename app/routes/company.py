from fastapi import APIRouter, Request, HTTPException, Depends, Response, Form
from app.functions import company_functions, auth_functions
from app.utils.jwt_handler import verify_token
from gridfs import GridFS
from bson import ObjectId
from app.db import db
from fastapi import UploadFile, File
from datetime import datetime

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
    
@router.put("/edit")
async def edit_company_details(
    request: Request,
    company_name: str = Form(None),
    company_email: str = Form(None),
    company_phone: str = Form(None),
    description: str = Form(None),
    founded_year: str = Form(None),
    employee_count: str = Form(None),
    location: str = Form(None),
    culture: str = Form(None),
    benefits: str = Form(None),
    industry: str = Form(None),
    logo: UploadFile = File(None),
    user=Depends(get_current_user)
):
    user_data = auth_functions.get_user_by_id(user.get("user_id"))
    company_id = user_data.get("company_id")
    if not company_id:
        raise HTTPException(status_code=403, detail="User not associated with any company")
    company = company_functions.get_company_by_id(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    if user_data.get("user_type") != "employer":
        raise HTTPException(status_code=403, detail="Only employers can edit company details")

    update_data = {}
    # Store the raw markdown content (don't convert to HTML)
    if company_name is not None:
        update_data["company_name"] = company_name
    if company_email is not None:
        update_data["company_email"] = company_email
    if company_phone is not None:
        update_data["company_phone"] = company_phone
    if description is not None:
        update_data["description"] = description  # Store as markdown
    if founded_year is not None:
        update_data["founded_year"] = founded_year
    if employee_count is not None:
        update_data["employee_count"] = employee_count
    if location is not None:
        update_data["location"] = location
    if culture is not None:
        update_data["culture"] = culture  # Store as markdown
    if benefits is not None:
        update_data["benefits"] = benefits  # Store as markdown
    if industry is not None:
        update_data["industry"] = industry

    # Handle logo update
    if logo is not None:
        file_data = await logo.read()
        gfs.delete(ObjectId(company["logo"]))
        new_logo_id = gfs.put(file_data, filename=logo.filename, content_type=logo.content_type)
        update_data["logo"] = str(new_logo_id)

    update_data["latest_edit_at"] = datetime.utcnow().isoformat()
    update_data["latest_edit_by"] = user_data.get("user_id")

    updated_company = company_functions.update_company_by_id(company_id, update_data)
    if not updated_company:
        raise HTTPException(status_code=500, detail="Failed to update company details")
    return updated_company