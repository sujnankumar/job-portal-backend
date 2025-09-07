from app.db import db
import uuid
from datetime import datetime, timedelta, timezone
from bson import ObjectId
from app.config.settings import BASE_URL 
from app.utils.timezone_utils import get_ist_now, IST, ist_to_utc 

def create_job(job_data: dict):
    job_data["job_id"] = str(uuid.uuid4())
    now = get_ist_now()
    validity_days = int(job_data.get("validity_days", 15))
    job_data["posted_at"] = now
    if "application_deadline" in job_data:
        # Convert application_deadline string (e.g., "2025-05-01") to a timezone-aware datetime object in IST
        deadline_naive = datetime.strptime(job_data["application_deadline"], "%Y-%m-%d")
        job_data["expires_at"] = deadline_naive.replace(tzinfo=IST)
    else:
        job_data["expires_at"] = now + timedelta(days=validity_days)
    job_data["status"] = "active"
    db.jobs.insert_one(job_data)
    return {"msg": "Job posted", "job_id": job_data["job_id"]}

def list_jobs():
    now = get_ist_now()
    # Auto-mark expired jobs before listing
    _auto_mark_expired(now)
    two_days_ago = now - timedelta(days=2)
    # Newest first
    jobs = db.jobs.find({}, {"_id": 0}).sort("posted_at", -1)
    job_list = []
    for job in jobs:
        # Ensure posted_at has timezone info for comparison
        posted_at = job["posted_at"]
        if posted_at.tzinfo is None:
            posted_at = posted_at.replace(tzinfo=IST)
        job["isNew"] = posted_at >= two_days_ago
        if "company_id" in job:
            company = db.companies.find_one({"company_id": job["company_id"]}, {"_id": 0, "company_name": 1, "logo": 1})
        job["company"] = company["company_name"] if company else None
        job["logo_url"] = f"{BASE_URL}/api/company/logo/{company['logo']}" if company and "logo" in company else None
        job_list.append(job)
    return job_list

def get_job_by_title(title: str):
    _auto_mark_expired(get_ist_now())
    return db.jobs.find_one({"title": title}, {"_id": 0})

def remove_job(job_id: str, employer_id: str):
    """Archive a job and cascade archive its applications & interviews.

    Steps:
    1. Fetch job (must belong to employer)
    2. Copy job doc to deleted_jobs with metadata (deleted_at, original_status)
    3. Copy related applications -> deleted_applications (add deleted_at)
    4. Copy related interviews -> deleted_interviews (add deleted_at)
    5. Delete originals from live collections
    """
    job = db.jobs.find_one({"job_id": job_id, "employer_id": employer_id})
    if not job:
        # Fallback: if it was expired and moved, try expired_jobs collection
        job = db.expired_jobs.find_one({"job_id": job_id, "employer_id": employer_id})
        if not job:
            return {"msg": "Job not found or unauthorized"}
    now = get_ist_now()
    # Related data
    applications = list(db.applications.find({"job_id": job_id}))
    interviews = list(db.interviews.find({"job_id": job_id}))

    # Prepare archival copies (strip _id to avoid clashes)
    job_copy = {k: v for k, v in job.items() if k != "_id"}
    job_copy.update({
        "deleted_at": now,
        "original_status": job.get("status"),
        "archived_applications_count": len(applications),
        "archived_interviews_count": len(interviews),
    "status": "deleted",
    })
    try:
        db.deleted_jobs.insert_one(job_copy)
    except Exception:
        # If insertion fails, abort to avoid data loss
        return {"msg": "Failed to archive job"}

    if applications:
        archived_apps = []
        for app in applications:
            app_copy = {k: v for k, v in app.items() if k != "_id"}
            app_copy["deleted_at"] = now
            archived_apps.append(app_copy)
        try:
            db.deleted_applications.insert_many(archived_apps)
        except Exception:
            pass  # Non-fatal; originals will still be deleted
    if interviews:
        archived_interviews = []
        for iv in interviews:
            iv_copy = {k: v for k, v in iv.items() if k != "_id"}
            iv_copy["deleted_at"] = now
            archived_interviews.append(iv_copy)
        try:
            db.deleted_interviews.insert_many(archived_interviews)
        except Exception:
            pass

    # Delete originals
    db.jobs.delete_one({"job_id": job_id})
    db.expired_jobs.delete_one({"job_id": job_id})
    if applications:
        db.applications.delete_many({"job_id": job_id})
    if interviews:
        db.interviews.delete_many({"job_id": job_id})

    return {"msg": "Job deleted and archived", "applications_archived": len(applications), "interviews_archived": len(interviews)}

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
        now = get_ist_now()
        update_data["expires_at"] = now + timedelta(days=validity_days)
    result = db.jobs.update_one({"job_id": job_id, "employer_id": employer_id}, {"$set": update_data})
    if result.modified_count == 1:
        return {"msg": "Job details updated"}
    return {"msg": "Job not found or unauthorized"}

def advanced_search_jobs(query=None, category=None, job_type=None, experience_level=None, min_salary=None, max_salary=None, location=None, industry=None, skills=None):
    _auto_mark_expired(get_ist_now())
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
    now = get_ist_now()
    expired_jobs = list(db.jobs.find({"expires_at": {"$lt": now}, "status": "active"}))
    for job in expired_jobs:
        job["status"] = "expired"
        db.expired_jobs.insert_one(job)
        db.jobs.update_one({"job_id": job["job_id"]}, {"$set": {"status": "expired"}})
    return {"moved": len(expired_jobs)}

def reactivate_expired_job(job_id: str, employer_id: str, validity_days: int = 15):
    """Reactivate an expired job in-place; mark with reactivated flag.

    Avoid inserting a duplicate document (previous implementation inserted a new doc).
    """
    job = db.jobs.find_one({"job_id": job_id, "employer_id": employer_id})
    if not job:
        return {"msg": "Job not found or unauthorized"}
    if job.get("status") != "expired":
        return {"msg": "Job is not expired"}
    now = get_ist_now()
    update_fields = {
        "status": "active",
        "posted_at": now,
        "expires_at": now + timedelta(days=validity_days),
        "reactivated": True
    }
    db.jobs.update_one({"job_id": job_id, "employer_id": employer_id}, {"$set": update_fields})
    # Clean up any archived copy in expired_jobs collection
    db.expired_jobs.delete_one({"job_id": job_id, "employer_id": employer_id})
    return {"msg": "Job reactivated", "job_id": job_id}

def list_companies():
    companies = db.companies.find({}, {"_id": 0})
    for company in companies:
        company["logo_url"] = f"{BASE_URL}/api/company/logo/{company['logo']}"
    return list(companies)

def add_company(company_data: dict, employer_id: str):
    company_data["company_id"] = str(uuid.uuid4())
    company_data["employer_id"] = employer_id
    db.companies.insert_one(company_data)
    return {"msg": "Company added", "company_id": company_data["company_id"]}

def get_popular_job_categories():
    pipeline = [
        {"$group": {"_id": "$job_category", "count": {"$sum": 1}}}, 
        {"$sort": {"count": -1}}, 
        {"$project": {"name": "$_id", "count": 1, "_id": 0}}
    ]
    return {"categories": list(db.jobs.aggregate(pipeline))}
    
def get_jobs_by_company(company_id: str):
    _auto_mark_expired(get_ist_now())
    company_jobs = db.jobs.find({"company_id": company_id}, {"_id": 0})
    logo_id = db.companies.find_one({"company_id": company_id}, {"logo": 1}).get("logo")
        
    if not company_jobs:
        return {"msg": "No jobs found for this company"}
    for job in company_jobs:
        job.pop("_id", None)
        job["logo_url"] = f"{BASE_URL}/api/company/logo/{logo_id}"
        
    return list(company_jobs)

# --- Automatic expiration helper ---
def _auto_mark_expired(now=None):
    """Update status to 'expired' for any active jobs whose expires_at has passed.

    This function is idempotent and cheap (single update_many). Call it at the
    start of read paths to ensure clients see fresh status without a cron.
    """
    if now is None:
        now = get_ist_now()
    try:
        db.jobs.update_many({"status": "active", "expires_at": {"$lt": now}}, {"$set": {"status": "expired"}})
    except Exception:
        # Silently ignore to avoid breaking primary flows; optionally log.
        pass