from fastapi import APIRouter, HTTPException, Depends, Path
from app.utils.jwt_handler import verify_token
from app.db import db
from fastapi import Request
from bson import ObjectId
from app.functions import company_functions, auth_functions, resume_functions
import base64
from datetime import datetime, timezone
router = APIRouter()

def get_current_user(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    user_data = verify_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or missing token")
    return user_data

@router.get("/applications/{job_id}")
async def get_applications_for_job(job_id: str = Path(...), user=Depends(get_current_user)):
    if user["user_type"] != "employer":
        raise HTTPException(status_code=403, detail="Only employers can access applications")
    job = db.jobs.find_one({"job_id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["employer_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Not authorized to view applications for this job")
    applications = list(db.applications.find({"job_id": job_id}, {"_id": 0}))
    return {"applications": applications}

from fastapi import APIRouter, HTTPException, Depends, Path
from bson import ObjectId

@router.get("/application/app_id/{app_id}")
async def get_applications_for_id(app_id: str = Path(...), user=Depends(get_current_user)):
    if not ObjectId.is_valid(app_id):
        raise HTTPException(status_code=400, detail="Invalid application ID format")

    application = db.applications.find_one({"_id": ObjectId(app_id)})
    print(application)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    if user["user_id"] != application["user_id"]:
        raise HTTPException(status_code=403, detail="Not authorized to view this application")
    
    
    job = db.jobs.find_one({"job_id": application["job_id"]})
    if not job:
        job = {}
    
    company = company_functions.get_company_by_id(job.get("company_id"))
    if not company:
        company = {}
    
    user_data = auth_functions.get_user_by_id(application["user_id"])
    if not user_data:
        user_data = {}

    print(company)
    salary_str = ""
    if job.get("show_salary", False):
        salary_str = str(job.get("min_salary", 0)) + " - " + str(job.get("max_salary", 0))
    else:
        salary_str = "Not disclosed"

    application["job"] =  {
            "title": job.get("title", ""),
            "company_name": company.get("company_name", ""),
            "description": company.get("description", ""),
            "founded_year": company.get("founded_year"),
            "employee_count": company.get("employee_count"),
            "location": company.get("location"),
            "industry": company.get("industry"),
            "logo": company.get("logo"),
            "expires_at": job.get("expires_at"),
            "employment_type": job.get("employment_type"),
            "salary": salary_str,
            "employer_id": job.get("employer_id"),
        }
    
    application["personalInfo"] = {
        "name": user_data.get("first_name", "") + " " + user.get("last_name", ""),
        "email": user_data.get("email", ""),
        "phone": user_data.get("phone", ""),
        "website": user_data.get("website", "No website added"),
        "linkedin": user_data.get("linkedin", "No LinkedIn Profile added")
    }
    
    file, resume_data = resume_functions.get_resume_by_file_id(application.get("resume_file_id", None))
    
    if file and resume_data:
        application["resume"] = {
            "file": base64.b64encode(file).decode("utf-8") if file else None,
            "filename": resume_data.get("filename", None),
            "upload_date": resume_data.get("upload_date", None)
        }

    application["_id"] = str(application["_id"])

    if "job" in application and "_id" in application["job"]:
        application["job"]["_id"] = str(application["job"]["_id"])

    status_timeline = {}
    if application.get("status") == "Scheduled":
        status_timeline = {
            "status": "schdeduled",
            "date": application.get("interview_date", None),
            "description": "Interview scheduled"
        }
    elif application.get("status") == "Selected":
        status_timeline = {
            "status": "selected",
            "date": application.get("selection_date", None),
            "description": "Application selected"
        }
    elif application.get("status") == "Rejected":
        status_timeline = {
            "status": "rejected",
            "date": application.get("rejection_date", None),
            "description": "Application rejected"
        }
    else:
        status_timeline = {
            "status": "pending",
            "date": application.get("updated_at", datetime.utcnow()),
            "description": "Application under review"
        }
    application['timeline'] = [
        {"status": "applied", "date": application.get("applied_at", None), "description": "Application submitted"},
        status_timeline
    ]
    
    return {"application": application}

@router.get("/application/job_id/{job_id}")
async def get_applications_for_id(job_id: str = Path(...), user=Depends(get_current_user)):
    # No need to check ObjectId validity for job_id since it's a UUID

    application = db.applications.find_one({"job_id": job_id, "user_id": user["user_id"]})
    print(application)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    if user["user_id"] != application["user_id"]:
        raise HTTPException(status_code=403, detail="Not authorized to view this application")
    
    
    job = db.jobs.find_one({"job_id": application["job_id"]})
    if not job:
        job = {}
    
    company = company_functions.get_company_by_id(job.get("company_id"))
    if not company:
        company = {}
    
    user_data = auth_functions.get_user_by_id(application["user_id"])
    if not user_data:
        user_data = {}

    print(company)
    salary_str = ""
    if job.get("show_salary", False):
        salary_str = str(job.get("min_salary", 0)) + " - " + str(job.get("max_salary", 0))
    else:
        salary_str = "Not disclosed"

    application["job"] =  {
            "title": job.get("title", ""),
            "company_name": company.get("company_name", ""),
            "description": company.get("description", ""),
            "founded_year": company.get("founded_year"),
            "employee_count": company.get("employee_count"),
            "location": company.get("location"),
            "industry": company.get("industry"),
            "logo": company.get("logo"),
            "expires_at": job.get("expires_at"),
            "employment_type": job.get("employment_type"),
            "salary": salary_str,
            "employer_id": job.get("employer_id"),
        }
    
    application["personalInfo"] = {
        "name": user_data.get("first_name", "") + " " + user.get("last_name", ""),
        "email": user_data.get("email", ""),
        "phone": user_data.get("phone", ""),
        "website": user_data.get("website", "No website added"),
        "linkedin": user_data.get("linkedin", "No LinkedIn Profile added")
    }
    
    file, resume_data = resume_functions.get_resume_by_file_id(application.get("resume_file_id", None))
    
    if file and resume_data:
        application["resume"] = {
            "file": base64.b64encode(file).decode("utf-8") if file else None,
            "filename": resume_data.get("filename", None),
            "upload_date": resume_data.get("upload_date", None)
        }

    application["_id"] = str(application["_id"])

    if "job" in application and "_id" in application["job"]:
        application["job"]["_id"] = str(application["job"]["_id"])

    status_timeline = {}
    if application.get("status") == "Scheduled":
        status_timeline = {
            "status": "schdeduled",
            "date": application.get("interview_date", None),
            "description": "Interview scheduled"
        }
    elif application.get("status") == "Selected":
        status_timeline = {
            "status": "selected",
            "date": application.get("selection_date", None),
            "description": "Application selected"
        }
    elif application.get("status") == "Rejected":
        status_timeline = {
            "status": "rejected",
            "date": application.get("rejection_date", None),
            "description": "Application rejected"
        }
    else:
        status_timeline = {
            "status": "pending",
            "date": application.get("updated_at", datetime.utcnow()),
            "description": "Application under review"
        }
    application['timeline'] = [
        {"status": "applied", "date": application.get("applied_at", None), "description": "Application submitted"},
        status_timeline
    ]
    
    return {"application": application}