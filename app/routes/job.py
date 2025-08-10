from fastapi import APIRouter, Request, HTTPException, Header
from app.functions import job_functions, auth_functions
from app.utils.jwt_handler import verify_token
from app.db import db
from app.utils.timezone_utils import get_ist_now
from app.config.settings import BASE_URL

router = APIRouter()

def get_current_user(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    
    user_data = verify_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or missing token")
    return user_data

@router.post("/post_job")
async def post_job(request: Request, authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if payload.get("user_type") != "employer":
        raise HTTPException(status_code=403, detail="Only employers can post jobs")
    data = await request.json()
    user = auth_functions.get_user_by_id(payload.get("user_id"))
    data["employer_id"] = payload.get("user_id")
    data["company_id"] = user.get("company_id", "")
    # Set job visibility, default to public if not provided
    data["visibility"] = data.get("visibility", "public")
    return job_functions.create_job(data)

@router.get("/list")
async def list_all_jobs():
    return job_functions.list_jobs()

@router.get("/search/{title}")
async def search_job(title: str):
    job = job_functions.get_job_by_title(title)
    if job:
        return job
    return {"msg": "Job not found"}

@router.get("/search")
async def search_jobs(query: str = None, category: str = None, job_type: str = None, experience_level: str = None, min_salary: int = None, max_salary: int = None, location: str = None, industry: str = None, skills: str = None):
    return job_functions.advanced_search_jobs(query, category, job_type, experience_level, min_salary, max_salary, location, industry, skills)

@router.get("/companies")
async def get_companies():
    return job_functions.list_companies()

@router.delete("/remove_job/{job_id}")
async def remove_job(job_id: str, authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if payload.get("user_type") != "employer":
        raise HTTPException(status_code=403, detail="Only employers can remove jobs")
    return job_functions.remove_job(job_id, payload.get("user_id"))

@router.patch("/update_visibility/{job_id}")
async def update_job_visibility(job_id: str, visibility: str, authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if payload.get("user_type") != "employer":
        raise HTTPException(status_code=403, detail="Only employers can update job visibility")
    return job_functions.update_job_visibility(job_id, visibility, payload.get("user_id"))

@router.post("/add_company")
async def add_company(request: Request, authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if payload.get("user_type") != "employer":
        raise HTTPException(status_code=403, detail="Only employers can add companies")
    data = await request.json()
    return job_functions.add_company(data, payload.get("user_id"))

@router.put("/update_job/{job_id}")
async def update_job(job_id: str, request: Request, authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if payload.get("user_type") != "employer":
        raise HTTPException(status_code=403, detail="Only employers can update jobs")
    update_data = await request.json()
    return job_functions.update_job_details(job_id, payload.get("user_id"), update_data)

@router.post("/move_expired_jobs")
async def move_expired_jobs_endpoint(authorization: str = Header(None)):
    # Optionally, restrict this endpoint to admin or employer
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    # You can add more role checks here if needed
    return job_functions.move_expired_jobs()

@router.post("/reactivate_job/{job_id}")
async def reactivate_job(job_id: str, validity_days: int = 15, authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if payload.get("user_type") != "employer":
        raise HTTPException(status_code=403, detail="Only employers can reactivate jobs")
    return job_functions.reactivate_expired_job(job_id, payload.get("user_id"), validity_days)

@router.get("/get-job/{job_id}")
async def get_job_with_saved_status(job_id: str, request: Request):
    user = get_current_user(request)
    job = db.jobs.find_one({"job_id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    # Auto-mark expired if needed (single fetch path)
    try:
        now = get_ist_now()
        expires_at = job.get("expires_at")
        if expires_at and job.get("status") == "active" and expires_at < now:
            db.jobs.update_one({"job_id": job_id}, {"$set": {"status": "expired"}})
            job["status"] = "expired"
    except Exception:
        pass
    company = db.companies.find_one({"employer_id": job.get("employer_id")}, {"_id": 0})
    if company:
        job["company_details"] = company
    is_saved = db.saved_jobs.find_one({"user_id": user["user_id"], "job_id": job_id})
    return {"job": job, "is_saved": bool(is_saved)}

@router.get("/categories/popular")
async def get_popular_job_categories():
    return job_functions.get_popular_job_categories()

@router.get("/featured-jobs")
async def get_featured_jobs():
    try:
        application_pipeline = [
            {
                "$group": {
                    "_id": "$job_id",
                    "application_count": {"$sum": 1}
                }
            },
            {
                "$sort": {"application_count": -1}
            },
            {
                "$limit": 10
            }
        ]
        popular_jobs = list(db.applications.aggregate(application_pipeline))
        popular_job_ids = [job["_id"] for job in popular_jobs]
        if not popular_job_ids:
            return {"featured_jobs": []}

        jobs = list(db.jobs.find({
            "job_id": {"$in": popular_job_ids},
            "status": "active"  # Only active jobs
        }, {
            "_id": 0,
            "company_id": 1,
            "job_id": 1,
            "title": 1,
            "description": 1,
            "location": 1,
            "show_salary": 1,
            "min_salary": {"$cond": {"if": "$show_salary", "then": "$min_salary", "else": None}},
            "max_salary": {"$cond": {"if": "$show_salary", "then": "$max_salary", "else": None}},
            "posted_at": 1,
            "employment_type": 1,
        }))  # Fetch relevant fields
        
        # Step 3: Fetch company details for the jobs
        company_ids = list({
            str(job.get("company_id")) for job in jobs if job.get("company_id")
        })

        # Step 3: Fetch company details
        companies = list(db.companies.find(
            {"company_id": {"$in": company_ids}},
            {"_id": 0, "company_id": 1, "company_name": 1, "logo": 1}
        ))

        # Make sure keys match: use str keys for consistency
        company_map = {str(company["company_id"]): company for company in companies}

        # Attach company details to each job
        for job in jobs:
            cid = str(job.get("company_id"))
            company_details = company_map.get(cid, {})
            job["company_name"] = company_details.get("company_name", "")
            logo_id = company_details.get("logo", "")
            job["logo"] = logo_id
            job["logo_url"] = f"{BASE_URL}/api/company/logo/{logo_id}" if logo_id else None

        
        jobs_sorted = sorted(jobs, key=lambda job: popular_job_ids.index(job["job_id"]))

        return {"featured_jobs": jobs_sorted}

    except Exception as e:
        return {"error": str(e)}

@router.get("/company/{company_id}")
def get_jobs_by_company_route(company_id: str):
    return job_functions.get_jobs_by_company(company_id)

@router.get("/jobs/by_company/{company_id}")
async def get_jobs_by_company(company_id: str):
    # Only return active jobs
    jobs = list(db.jobs.find({
        "company_id": company_id, 
        "status": "active"
    }, {"_id": 0}))
    return {"jobs": jobs}