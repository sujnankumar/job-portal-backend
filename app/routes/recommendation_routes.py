from fastapi import APIRouter, Depends, HTTPException, Request
from app.utils.jwt_handler import verify_token
from app.db import db

router = APIRouter()

def get_current_user(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    user_data = verify_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or missing token")
    return user_data

@router.get("/recommendations")
def get_job_recommendations(user=Depends(get_current_user)):
    user_doc = db.users.find_one({"user_id": user["user_id"]})
    if not user_doc or "skills" not in user_doc:
        raise HTTPException(status_code=404, detail="User profile incomplete")

    skills = user_doc["skills"]

    matching_jobs = list(db.jobs.find({
        "required_skills": {"$in": skills}
    }, {"_id": 0}))

    applied_jobs = db.applications.find({
        "user_id": user["user_id"]
    })
    applied_job_ids = {app["job_id"] for app in applied_jobs}

    recommended = [
        job for job in matching_jobs if job["job_id"] not in applied_job_ids
    ]

    def score(job):
        return len(set(job.get("required_skills", [])) & set(skills))

    recommended.sort(key=score, reverse=True)

    return {"recommended_jobs": recommended}
