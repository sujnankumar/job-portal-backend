from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from app.functions import auth_functions, company_functions
from app.utils.jwt_handler import verify_token
from app.db import db
from bson import ObjectId
from gridfs import GridFS

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


@router.post("/onboarding/logo")
async def upload_logo(request: Request,file: UploadFile = File(...)):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    
    token = auth_header.split("Bearer ")[1]
    user_data = verify_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    contents = await file.read()
    # Initialize GridFS
    fs = GridFS(db)

    # --- Find and delete the old logo if it exists ---
    # Assume user_data was obtained from the token earlier in the function
    old_logo_id_str = None
    if user_data and user_data.get("user_type") == "employer":
        user_id = user_data.get("user_id")
        if user_id:
            # Find the user document to get the associated company ID
            user = db.users.find_one({"user_id": user_id})
            if user:
                company_id = user.get("company_id") # Assumes user doc has company_id
                if company_id:
                    # Find the company document to get the old logo ID
                    company = db.companies.find_one({"company_id": company_id})
                    if company:
                        old_logo_id_str = company.get("logo") # Assumes company doc has logo field with GridFS ID string

    # If an old logo ID was found, attempt to delete it from GridFS
    if old_logo_id_str:
        try:
            # Convert string ID to ObjectId and delete
            fs.delete(ObjectId(old_logo_id_str))
            # Optional: Log successful deletion
            # print(f"Deleted old logo file: {old_logo_id_str}")
        except Exception as e:
            # Log other potential errors during deletion (e.g., invalid ObjectId format)
            # print(f"Error deleting old logo {old_logo_id_str}: {e}")
            pass # Decide if upload should proceed despite deletion error
    # --- End find and delete ---

    file_id = fs.put(contents, filename=file.filename, content_type=file.content_type)
    return {"logo_file_id": str(file_id)}

@router.post("/onboarding")
async def onboarding(request: Request):
    data = await request.json()
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    token = auth_header.split("Bearer ")[1]
    user_data = verify_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    if user_data["user_type"] == "employer":
        company_data = {
            "company_name": data.get("companyName", ""),
            "company_email": data.get("companyEmail", ""),
            "company_phone": data.get("companyPhone", ""),
            "description": data.get("description", ""),
            "founded_year": data.get("foundedYear"),
            "employee_count": data.get("companySize"),
            "location": data.get("location"),
            "industry": data.get("industry"),
        }
        if "logo_file_id" in data:
            company_data["logo"] = data.get("logo_file_id")

        isNewCompany = data.get("isNewCompany", False)
        if isNewCompany:
            result = company_functions.add_company(company_data)
            company = result["data"]
        else:
            company = company_functions.get_company_by_id(data.get("companyId"))
            if not company:
                raise HTTPException(status_code=404, detail="Company not found")
        result = auth_functions.onboard_user(user_data, data, company)

        if not result:
            raise HTTPException(status_code=401, detail="Could not complete onboarding")
        
        return result
    else:
        return {"message": "Onboarding completed successfully"}