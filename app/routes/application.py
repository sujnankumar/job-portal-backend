from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Header
from app.utils.jwt_handler import verify_token
from app.db import db
from datetime import datetime
from typing import Optional
import uuid
from bson import ObjectId

router = APIRouter()

def fix_objectid(doc):
    if not doc:
        return doc
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            doc[k] = str(v)
    return doc

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

    # Step 3: Save resume file directly in MongoDB using GridFS
    file_bytes = await resume.read()
    from app.functions import resume_functions
    file_id = resume_functions.gfs.put(file_bytes, filename=resume.filename, content_type=resume.content_type)

    application = {
        "job_id": job_id,
        "user_id": user_data["user_id"],
        "email": user_data["email"],
        "cover_letter": cover_letter,
        "linked_in": linked_in,
        "portfolio": portfolio,
        "resume_file_id": str(file_id),
        "resume_filename": resume.filename,
        "resume_content_type": resume.content_type,
        "status": "pending",
        "applied_at": datetime.utcnow(),
    }
    db.applications.insert_one(application)

    # Also insert resume into temp_resume collection, referencing the same file_id
    from app.functions.resume_functions import parse_resume
    user_id = user_data["user_id"]
    filename = resume.filename
    content_type = resume.content_type
    old = db.temp_resume.find_one({"user_id": user_id})
    if old:
        resume_functions.gfs.delete(old["file_id"])
        db.temp_resume.delete_one({"user_id": user_id})
    parsed_data = parse_resume(file_bytes, content_type)
    db.temp_resume.insert_one({
        "user_id": user_id,
        "file_id": file_id,  # reference the same file_id
        "filename": filename,
        "content_type": content_type,
        "upload_date": datetime.utcnow(),
        "parsed_data": parsed_data
    })
    return {"message": "Application submitted successfully", "application": fix_objectid(application)}
