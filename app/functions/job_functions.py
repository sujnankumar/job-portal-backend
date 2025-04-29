from app.db import db
import uuid
from datetime import datetime, timedelta, timezone

def create_job(job_data: dict):
    job_data["job_id"] = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    validity_days = int(job_data.get("validity_days", 15))
    job_data["posted_at"] = now
    if "application_deadline" in job_data:
        # Convert application_deadline string (e.g., "2025-05-01") to a timezone-aware datetime object
        job_data["expires_at"] = datetime.strptime(job_data["application_deadline"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        job_data["expires_at"] = now + timedelta(days=validity_days)
    job_data["status"] = "active"
    db.jobs.insert_one(job_data)
    return {"msg": "Job posted", "job_id": job_data["job_id"]}

def list_jobs():
    now = datetime.now(timezone.utc)
    two_days_ago = now - timedelta(days=2)
    jobs = db.jobs.find({}, {"_id": 0})
    job_list = []
    for job in jobs:
        job["isNew"] = job["posted_at"].replace(tzinfo=timezone.utc) >= two_days_ago
        company = db.users.find_one({"user_id": job["employer_id"]}, {"_id": 0, "company_name": 1})
        print(job["employer_id"],company)
        job["company"] = company["company_name"] if company else None
        job_list.append(job)
    return job_list

def get_job_by_title(title: str):
    return db.jobs.find_one({"title": title}, {"_id": 0})

def remove_job(job_id: str, employer_id: str):
    result = db.jobs.delete_one({"job_id": job_id, "employer_id": employer_id})
    if result.deleted_count == 1:
        return {"msg": "Job removed"}
    return {"msg": "Job not found or unauthorized"}

def update_job_visibility(job_id: str, visibility: str, employer_id: str):
    if visibility not in ["public", "private"]:
        return {"msg": "Invalid visibility option"}
    result = db.jobs.update_one({"job_id": job_id, "employer_id": employer_id}, {"$set": {"visibility": visibility}})
    if result.modified_count == 1:
        return {"msg": f"Job visibility updated to {visibility}"}
    return {"msg": "Job not found or unauthorized"}

def update_job_details(job_id: str, employer_id: str, update_data: dict):
    # Remove fields that should not be updated
    update_data.pop("job_id", None)
    update_data.pop("employer_id", None)
    # Handle validity_days and update expires_at if present
    if "validity_days" in update_data:
        try:
            validity_days = int(update_data["validity_days"])
        except Exception:
            validity_days = 15
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        update_data["expires_at"] = now + timedelta(days=validity_days)
    result = db.jobs.update_one({"job_id": job_id, "employer_id": employer_id}, {"$set": update_data})
    if result.modified_count == 1:
        return {"msg": "Job details updated"}
    return {"msg": "Job not found or unauthorized"}

def advanced_search_jobs(query=None, category=None, job_type=None, experience_level=None, min_salary=None, max_salary=None, location=None, industry=None, skills=None):
    filters = {}
    if query:
        filters["$or"] = [
            {"title": {"$regex": query, "$options": "i"}},
            {"description": {"$regex": query, "$options": "i"}}
        ]
    if category:
        filters["category"] = category
    if job_type:
        filters["type"] = job_type
    if experience_level:
        filters["experience_level"] = experience_level
    if min_salary is not None or max_salary is not None:
        filters["salary"] = {}
        if min_salary is not None:
            filters["salary"]["$gte"] = min_salary
        if max_salary is not None:
            filters["salary"]["$lte"] = max_salary
    if location:
        filters["location"] = {"$regex": location, "$options": "i"}
    if industry:
        filters["industry"] = industry
    if skills:
        filters["skills"] = {"$in": [s.strip() for s in skills.split(",") if s.strip()]}
    return list(db.jobs.find(filters, {"_id": 0}))

def move_expired_jobs():
    now = datetime.now(timezone.utc)
    expired_jobs = list(db.jobs.find({"expires_at": {"$lt": now}, "status": "active"}))
    for job in expired_jobs:
        job["status"] = "expired"
        db.expired_jobs.insert_one(job)
        db.jobs.update_one({"job_id": job["job_id"]}, {"$set": {"status": "expired"}})
    return {"moved": len(expired_jobs)}

def reactivate_expired_job(job_id: str, employer_id: str, validity_days: int = 15):
    job = db.expired_jobs.find_one({"job_id": job_id, "employer_id": employer_id})
    if not job:
        return {"msg": "Expired job not found or unauthorized"}
    # Remove MongoDB _id and update fields
    job.pop("_id", None)
    now = datetime.now(timezone.utc)
    job["status"] = "active"
    job["posted_at"] = now
    job["expires_at"] = now + timedelta(days=validity_days)
    db.jobs.insert_one(job)
    db.expired_jobs.delete_one({"job_id": job_id, "employer_id": employer_id})
    return {"msg": "Job reactivated", "job_id": job_id}

def list_companies():
    return list(db.companies.find({}, {"_id": 0}))

def add_company(company_data: dict, employer_id: str):
    company_data["company_id"] = str(uuid.uuid4())
    company_data["employer_id"] = employer_id
    db.companies.insert_one(company_data)
    return {"msg": "Company added", "company_id": company_data["company_id"]}
