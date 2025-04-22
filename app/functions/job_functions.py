from app.db import db
import uuid

def create_job(job_data: dict):
    job_data["job_id"] = str(uuid.uuid4())
    db.jobs.insert_one(job_data)
    return {"msg": "Job posted", "job_id": job_data["job_id"]}

def list_jobs():
    return list(db.jobs.find({}, {"_id": 0}))

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
