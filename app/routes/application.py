from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Header, Request, Depends
from app.utils.jwt_handler import verify_token
from app.db import db
from datetime import datetime
from typing import Optional
import uuid
from bson import ObjectId
from app.functions import application_functions
from app.routes.notification import notification_manager, serialize_notification

router = APIRouter()

def fix_objectid(doc):
    if not doc:
        return doc
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            doc[k] = str(v)
    return doc

def get_current_user(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    user_data = verify_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or missing token")
    return user_data

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

    # --- Notify employer ---
    job = db.jobs.find_one({"job_id": job_id})
    if job and "employer_id" in job:
        employer_id = job["employer_id"]
        notification = {
            "user_id": employer_id,
            "type": "application",
            "title": "New Application",
            "description": f"{user_data.get('first_name', '')} {user_data.get('last_name', '')} applied for {job.get('title', 'your job')}",
            "time": datetime.utcnow(),
            "read": False,
            "link": f"/employer/dashboard/applications/{job_id}"
        }
        db.notifications.insert_one(notification)
        await notification_manager.send_notification(employer_id, serialize_notification(notification))
    return {"message": "Application submitted successfully", "application": fix_objectid(application)}

@router.post("/delete_application/{application_id}")
async def delete_application(application_id: str, user=Depends(get_current_user)):
    # Find the application and job to notify employer BEFORE deleting
    application = db.applications.find_one({"_id": ObjectId(application_id)})
    employer_id = None
    job = None
    if application:
        job = db.jobs.find_one({"job_id": application["job_id"]})
        if job and "employer_id" in job:
            employer_id = job["employer_id"]
    response  = application_functions.delete_application(application_id, user["user_id"])

    if response["status"] == "success":
        if employer_id:
            notification = {
                "user_id": employer_id,
                "type": "application",
                "title": "Application Withdrawn",
                "description": f"{user.get('first_name', '')} {user.get('last_name', '')} withdrew their application for {job.get('title', 'your job') if job else ''}",
                "time": datetime.utcnow(),
                "read": False,
                "link": f"/employer/dashboard/applications/{job['job_id']}" if job else ""
            }
            db.notifications.insert_one(notification)
            await notification_manager.send_notification(employer_id, serialize_notification(notification))
        return {"message": "Application deleted successfully"}
    else:
        raise HTTPException(status_code=400, detail=response["message"])
