from fastapi import APIRouter, Depends, HTTPException, Request
from app.utils.jwt_handler import verify_token
from app.db import db
from bson import ObjectId
from app.functions import company_functions

router = APIRouter()

# Helper to extract and verify token
def get_current_user(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    
    token = auth_header.split("Bearer ")[1]
    user_data = verify_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_data

# GET /applications/my-applications
@router.get("/applications/my-applications")
async def get_my_applications(user=Depends(get_current_user)):
    user_id = user.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid user data")
    applications = list(db.applications.find({"user_id": user_id}))
    enriched = []
    for app in applications:
        job = db.jobs.find_one({"job_id": app["job_id"]})
        if not job:
            continue
        employer = db.users.find_one({"user_id": job.get("employer_id")})
        company = company_functions.get_company_by_id(job.get("company_id"))
        
        # Get company logo ID if available
        company_logo_id = None
        if company and company.get("logo"):
            company_logo_id = company.get("logo")
            
        enriched.append({
            "id": str(app["_id"]), 
            "jobTitle": job.get("title"),
            "company": company.get("company_name", "") if company else employer.get("company_name", ""),
            "companyId": job.get("company_id"),  # Add company ID for logo fetching
            "logo": company_logo_id,  # Use company logo ID instead of job logo
            "location": job.get("location"),
            "appliedDate": app["applied_at"].strftime("%b %d, %Y") if app.get("applied_at") else None,
            "status": app.get("status", "Under Review"),
            **{k: v for k, v in app.items() if k != "_id"}  # exclude _id to avoid JSON issues
        })
    return {"applications": enriched}



@router.get("/is-applied/{job_id}")
async def is_applied_for_job(job_id: str, user=Depends(get_current_user)):
    user_id = user.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid user data")
    existing_application = db.applications.find_one({"job_id": job_id, "user_id": user_id})
    return {"is_applied": bool(existing_application)}


@router.get("/applications/active")
async def get_active_applications(user=Depends(get_current_user)):
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

    enriched = []
    for app in active_applications:
        job = db.jobs.find_one({"job_id": app["job_id"]})
        if not job:
            continue
        employer = db.users.find_one({"user_id": job.get("employer_id")})
        company = company_functions.get_company_by_id(job.get("company_id"))
        
        # Get company logo ID if available
        company_logo_id = None
        if company and company.get("logo"):
            company_logo_id = company.get("logo")
            
        company_name = company.get("company_name", "") if company else (employer.get("company_name", "") if employer else "")
        
        enriched.append({
            "jobTitle": job.get("title"),
            "company": company_name,
            "companyId": job.get("company_id"),  # Add company ID for logo fetching
            "logo": company_logo_id,  # Use company logo ID instead of job logo
            "location": job.get("location"),
            "appliedDate": app["applied_at"].strftime("%b %d, %Y") if app.get("applied_at") else None,
            "status": app.get("status", "Under Review"),
            **app
        })

    return {"active_applications": enriched}


