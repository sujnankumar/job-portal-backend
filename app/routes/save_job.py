from fastapi import APIRouter, HTTPException, Depends, Request
from datetime import datetime
from app.db import db
from app.utils.jwt_handler import verify_token

router = APIRouter()

def get_current_user(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    user_data = verify_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or missing token")
    return user_data

@router.post("/save-job/{job_id}")
def save_job(job_id: str, user=Depends(get_current_user)):
    if user["user_type"] != "job_seeker":
        raise HTTPException(status_code=403, detail="Only jobseekers can save jobs")

    job = db.jobs.find_one({"job_id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    already_saved = db.saved_jobs.find_one({"user_id": user["user_id"], "job_id": job_id})
    if already_saved:
        raise HTTPException(status_code=400, detail="Job already saved")

    saved_job = {
        **job,
        "user_id": user["user_id"],
        "saved_at": datetime.utcnow()
    }
    db.saved_jobs.insert_one(saved_job)
    return {"message": "Job saved successfully"}
@router.get("/saved-jobs")
def get_saved_jobs(user=Depends(get_current_user)):
    if user["user_type"] != "job_seeker":
        raise HTTPException(status_code=403, detail="Only jobseekers can view saved jobs")

    saved_jobs = list(db.saved_jobs.find({"user_id": user["user_id"]}, {"_id": 0}))
    return {"saved_jobs": saved_jobs}
