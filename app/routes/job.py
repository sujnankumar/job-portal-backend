from fastapi import APIRouter, Request, HTTPException, Header
from app.functions import job_functions
from app.utils.jwt_handler import verify_token
from app.db import db

router = APIRouter()

def get_current_user(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    print(token)
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
    data["employer_id"] = payload.get("user_id")
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
    company = db.companies.find_one({"employer_id": job.get("employer_id")}, {"_id": 0})
    if company:
        job["company_details"] = company
    is_saved = db.saved_jobs.find_one({"user_id": user["user_id"], "job_id": job_id})
    return {"job": job, "is_saved": bool(is_saved)}