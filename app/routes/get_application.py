from fastapi import APIRouter, HTTPException, Depends, Path
from app.utils.jwt_handler import verify_token
from app.db import db
from fastapi import Request

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
