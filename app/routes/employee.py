from fastapi import APIRouter, Header, HTTPException, Response
from app.utils.jwt_handler import verify_token
from app.db import db
from gridfs import GridFS
from bson import ObjectId

gfs = GridFS(db)

router = APIRouter()

@router.get("/company_details")
async def get_company_details(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user_email = payload.get("email")
    if not user_email:
        raise HTTPException(status_code=400, detail="Could not retrieve user email from token")
    user = db.users.find_one({"email": user_email}, {"_id": 0, "password": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.get("user_type") != "employer":
        raise HTTPException(status_code=403, detail="Only employers have company details")
    job_title = user.get("onboarding", {}).get("formData", {}).get("jobPosition")
    company = db.companies.find_one({"company_id": user.get("company_id")}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    company["job_title"] = job_title
    return company

@router.get("/job_stats")
async def get_job_stats(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user_email = payload.get("email")
    if not user_email:
        raise HTTPException(status_code=400, detail="Could not retrieve user email from token")
    user = db.users.find_one({"email": user_email}, {"_id": 0, "password": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.get("user_type") != "employer":
        raise HTTPException(status_code=403, detail="Only employers can access job stats")
    employer_id = user.get("user_id")
    jobs = list(db.jobs.find({"employer_id": employer_id}, {"job_id": 1, "title": 1}))
    job_stats = []
    total_applicants = 0
    for job in jobs:
        job_id = job["job_id"]
        applicants_count = db.applications.count_documents({"job_id": job_id})
        total_applicants += applicants_count
        job_stats.append({
            "job_id": job_id,
            "title": job.get("title"),
            "applicants": applicants_count
        })
    return {
        "total_jobs": len(jobs),
        "total_applicants": total_applicants,
        "job_stats": job_stats
    }

@router.get("/employer_stats")
async def employer_stats(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user_email = payload.get("email")
    if not user_email:
        raise HTTPException(status_code=400, detail="Could not retrieve user email from token")
    user = db.users.find_one({"email": user_email}, {"_id": 0, "password": 0})
    if not user or user.get("user_type") != "employer":
        raise HTTPException(status_code=403, detail="Only employers can access stats")
    employer_id = user.get("user_id")
    # Active Jobs
    active_jobs_count = db.jobs.count_documents({"employer_id": employer_id, "status": {"$ne": "expired"}})
    # Total Applications
    job_ids = [job["job_id"] for job in db.jobs.find({"employer_id": employer_id}, {"job_id": 1})]
    total_applications = db.applications.count_documents({"job_id": {"$in": job_ids}}) if job_ids else 0
    # Profile Views (optional, here as a placeholder)
    # If you have a profile_views field, use it. Otherwise, return a static or 0.
    profile_views = user.get("profile_views", 0)
    return {
        "active_jobs": active_jobs_count,
        "total_applications": total_applications,
        "profile_views": profile_views
    }

@router.get("/job_postings")
async def get_job_postings(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user_email = payload.get("email")
    if not user_email:
        raise HTTPException(status_code=400, detail="Could not retrieve user email from token")
    user = db.users.find_one({"email": user_email}, {"_id": 0, "password": 0})
    if not user or user.get("user_type") != "employer":
        raise HTTPException(status_code=403, detail="Only employers can access job postings")
    employer_id = user.get("user_id")
    jobs = list(db.jobs.find({"employer_id": employer_id}, {"_id": 0}))
    job_postings = []
    for job in jobs:
        applications = db.applications.count_documents({"job_id": job["job_id"]})
        # You can add a 'views' field to jobs, or set to 0 if not present
        job_postings.append({
            "id": job["job_id"],
            "title": job.get("title"),
            "location": job.get("location"),
            "department": job.get("department"),
            "postedDate": job.get("posted_at").strftime("%Y-%m-%d") if job.get("posted_at") else None,
            "expiryDate": job.get("expires_at").strftime("%Y-%m-%d") if job.get("expires_at") else None,
            "status": job.get("status", "active"),
            "applications": applications,
            "views": job.get("views", 0)
        })
    return {"jobPostings": job_postings}

@router.get("/job_applications/{job_id}")
async def get_job_applications(job_id: str, authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user_email = payload.get("email")
    if not user_email:
        raise HTTPException(status_code=400, detail="Could not retrieve user email from token")
    user = db.users.find_one({"email": user_email}, {"_id": 0, "password": 0})
    if not user or user.get("user_type") != "employer":
        raise HTTPException(status_code=403, detail="Only employers can access job applications")
    job = db.jobs.find_one({"job_id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    # Get company info
    employer = db.users.find_one({"user_id": job.get("employer_id")}, {"_id": 0, "company_name": 1})
    company_name = employer["company_name"] if employer and "company_name" in employer else None
    company_logo = job.get("logo", "/abstract-geometric-logo.png")
    # Job details
    job_details = {
        "id": job["job_id"],
        "title": job.get("title"),
        "location": job.get("location"),
        "department": job.get("department"),
        "company": company_name,
        "companyLogo": company_logo,
    }
    # Applications
    applications = list(db.applications.find(
        {"job_id": job_id},
        {
            "_id": 1,
            "job_id": 1,
            "user_id": 1,
            "email": 1,
            "cover_letter": 1,
            "linked_in": 1,
            "portfolio": 1,
            "resume_file_id": 1,
            "resume_filename": 1,
            "resume_content_type": 1,
            "status": 1,
            "applied_at": 1,
            "interview_date": 1,
            "interview_time": 1
        }
    ))
    enriched_apps = []
    for app in applications:
        candidate = db.users.find_one({"user_id": app["user_id"]}, {"_id": 0, "user_id": 1, "first_name": 1, "last_name": 1, "email": 1, "phone": 1, "location": 1, "avatar": 1})
        print("candidate :",candidate)
        if not candidate:
            continue
        enriched_apps.append({
            "id": str(app.get("_id", app.get("application_id", ""))),
            "candidate": {
                "id": candidate.get("user_id"),
                "name": f"{candidate.get('first_name', '')} {candidate.get('last_name', '')}",
                "email": candidate.get("email"),
                "avatar": candidate.get("avatar", "/mystical-forest-spirit.png"),
                "phone": candidate.get("phone", "N/A"),
                "location": candidate.get("location", "N/A"),
            },
            "appliedDate": app["applied_at"].strftime("%Y-%m-%d") if app.get("applied_at") else None,
            "status": app.get("status", "review"),
            # "resumeUrl": f"/api/application/download_resume/{app.get('resume_file_id')}" if app.get("resume_file_id") else None,
            "coverLetter": app.get("cover_letter", ""),
            "matchScore": app.get("match_score", 0),
            "interviewDate": app.get("interview_date", None),
            "interviewTime": app.get("interview_time", None),
        })
        print(enriched_apps)
    return {
        "jobDetails": job_details,
        "applications": enriched_apps
    }

@router.get("/get_resume_by_user/{job_id}/{user_id}")
async def get_resume_by_user(job_id: str, user_id: str, authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user_email = payload.get("email")
    if not user_email:
        raise HTTPException(status_code=400, detail="Could not retrieve user email from token")
    user = db.users.find_one({"email": user_email}, {"_id": 0, "password": 0})
    if not user or user.get("user_type") != "employer":
        raise HTTPException(status_code=403, detail="Only employers can access resumes")
    # Find the application for this job and user
    application = db.applications.find_one({"job_id": job_id, "user_id": user_id})
    if not application or not application.get("resume_file_id"):
        raise HTTPException(status_code=404, detail="Application or resume not found")
    resume_file_id = application["resume_file_id"]
    try:
        file = gfs.get(ObjectId(resume_file_id))
    except Exception:
        raise HTTPException(status_code=404, detail="Resume file not found in storage")
    return Response(content=file.read(), media_type=file.content_type, headers={"Content-Disposition": f"inline; filename={file.filename}"})
