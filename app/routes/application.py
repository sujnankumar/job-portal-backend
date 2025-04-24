from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Header
from app.utils.jwt_handler import verify_token
from app.db import db
from datetime import datetime
from typing import Optional
import uuid

router = APIRouter()

@router.post("/apply/{job_id}")
async def apply_for_job(
    job_id: str,
    resume: UploadFile = File(...),
    cover_letter: Optional[str] = Form(""),
    linked_in: Optional[str] = Form(""),
    portfolio: Optional[str] = Form(""),
    authorization: str = Header(None)
):
    # Step 1: Authenticate the user
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    token = authorization.split(" ", 1)[1]
    user_data = verify_token(token)

    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Step 2: Check if already applied
    existing_application = db.applications.find_one({
        "job_id": job_id,
        "user_id": user_data["user_id"]
    })
    if existing_application:
        raise HTTPException(status_code=400, detail="You have already applied for this job")

    # Step 3: Save resume file (simulate by generating a mock URL)
    resume_url = f"https://yourcdn.com/uploads/{uuid.uuid4()}-{resume.filename}"

    # Step 4: Create and save the application
    application = {
        "job_id": job_id,
        "user_id": user_data["user_id"],
        "email": user_data["email"],
        "cover_letter": cover_letter,
        "linked_in": linked_in,
        "portfolio": portfolio,
        "resume": resume_url,
        "status": "pending",
        "applied_at": datetime.utcnow(),
    }

    db.applications.insert_one(application)

    return {"message": "Application submitted successfully", "application": application}
