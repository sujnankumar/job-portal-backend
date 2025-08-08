from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Header, Request, Depends
from app.utils.jwt_handler import verify_token
from app.db import db
from datetime import datetime
from typing import Optional
import uuid
from bson import ObjectId
from app.functions import application_functions
from app.routes.notification import notification_manager, serialize_notification
from app.utils.timezone_utils import get_ist_now

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
        "applied_at": get_ist_now(),
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
        "upload_date": get_ist_now(),
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
            "time": get_ist_now(),
            "read": False,
            "link": f"/employer/dashboard/applications/{job_id}"
        }
        db.notifications.insert_one(notification)
        await notification_manager.send_notification(employer_id, serialize_notification(notification))
    return {"message": "Application submitted successfully", "application": fix_objectid(application)}

@router.post("/delete_application/{application_id}")
async def delete_application(application_id: str, user=Depends(get_current_user)):
    # Find the application and job to notify employer BEFORE deleting
    application = None
    
    # First try as ObjectId (real application ID)
    try:
        if ObjectId.is_valid(application_id):
            application = db.applications.find_one({"_id": ObjectId(application_id)})
    except:
        pass
    
    # If not found, try as job_id (UUID format)
    if not application:
        application = db.applications.find_one({"job_id": application_id, "user_id": user["user_id"]})
    
    employer_id = None
    job = None
    if application:
        # Save the application to deleted_applications before deleting
        db.deleted_applications.insert_one(application)
        job = db.jobs.find_one({"job_id": application["job_id"]})
        if job and "employer_id" in job:
            employer_id = job["employer_id"]
    
    # Use the actual ObjectId for deletion
    response = application_functions.delete_application(str(application["_id"]) if application else application_id, user["user_id"])

    if response["status"] == "success":
        if employer_id:
            notification = {
                "user_id": employer_id,
                "type": "application",
                "title": "Application Withdrawn",
                "description": f"{user.get('first_name', '')} {user.get('last_name', '')} withdrew their application for {job.get('title', 'your job') if job else ''}",
                "time": get_ist_now(),
                "read": False,
                "link": f"/employer/dashboard/applications/{job['job_id']}" if job else ""
            }
            db.notifications.insert_one(notification)
            await notification_manager.send_notification(employer_id, serialize_notification(notification))
        return {"message": "Application deleted successfully"}
    else:
        raise HTTPException(status_code=400, detail=response["message"])

@router.put("/edit_application/{application_id}")
async def edit_application(
    application_id: str,
    resume: Optional[UploadFile] = File(None),
    cover_letter: Optional[str] = Form(None),
    linked_in: Optional[str] = Form(None),
    portfolio: Optional[str] = Form(None),
    user=Depends(get_current_user)
):
    # Find the application - try both ObjectId format and job_id format
    application = None
    
    # First try as ObjectId (real application ID)
    try:
        if ObjectId.is_valid(application_id):
            application = db.applications.find_one({"_id": ObjectId(application_id)})
    except:
        pass
    
    # If not found, try as job_id (UUID format)
    if not application:
        application = db.applications.find_one({"job_id": application_id, "user_id": user["user_id"]})
    
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    # Check if user owns this application
    if application["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Unauthorized to edit this application")
    
    # Check if application is in editable status (pending or review)
    if application["status"] not in ["pending", "review"]:
        raise HTTPException(status_code=400, detail="Application cannot be edited in current status")
    
    # Find the job to check deadline
    job = db.jobs.find_one({"job_id": application["job_id"]})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Check if deadline has passed
    current_time = get_ist_now()
    job_deadline = job.get("expires_at")
    if job_deadline and current_time > job_deadline:
        raise HTTPException(status_code=400, detail="Application deadline has passed")
    
    # Prepare update data
    update_data = {}
    
    # Update optional fields only if provided
    if cover_letter is not None:
        update_data["cover_letter"] = cover_letter
    if linked_in is not None:
        update_data["linked_in"] = linked_in
    if portfolio is not None:
        update_data["portfolio"] = portfolio
    
    # Handle resume update if provided
    if resume is not None:
        # Delete old resume file from GridFS
        old_file_id = application.get("resume_file_id")
        if old_file_id:
            from app.functions import resume_functions
            try:
                resume_functions.gfs.delete(old_file_id)
            except Exception:
                pass  # File might not exist
        
        # Save new resume file
        file_bytes = await resume.read()
        from app.functions import resume_functions
        file_id = resume_functions.gfs.put(file_bytes, filename=resume.filename, content_type=resume.content_type)
        
        update_data.update({
            "resume_file_id": str(file_id),
            "resume_filename": resume.filename,
            "resume_content_type": resume.content_type
        })
        
        # Update temp_resume collection as well
        from app.functions.resume_functions import parse_resume
        user_id = user["user_id"]
        old_temp = db.temp_resume.find_one({"user_id": user_id})
        if old_temp and old_temp.get("file_id"):
            try:
                resume_functions.gfs.delete(old_temp["file_id"])
            except Exception:
                pass
            db.temp_resume.delete_one({"user_id": user_id})
        
        parsed_data = parse_resume(file_bytes, resume.content_type)
        db.temp_resume.insert_one({
            "user_id": user_id,
            "file_id": file_id,
            "filename": resume.filename,
            "content_type": resume.content_type,
            "upload_date": get_ist_now(),
            "parsed_data": parsed_data
        })
    
    # Add updated timestamp
    update_data["updated_at"] = get_ist_now()
    
    # Update the application
    result = db.applications.update_one(
        {"_id": application["_id"]},
        {"$set": update_data}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="No changes were made to the application")
    
    # Notify employer about the update
    if job and "employer_id" in job:
        employer_id = job["employer_id"]
        notification = {
            "user_id": employer_id,
            "type": "application",
            "title": "Application Updated",
            "description": f"{user.get('first_name', '')} {user.get('last_name', '')} updated their application for {job.get('title', 'your job')}",
            "time": get_ist_now(),
            "read": False,
            "link": f"/employer/dashboard/applications/{job['job_id']}"
        }
        db.notifications.insert_one(notification)
        await notification_manager.send_notification(employer_id, serialize_notification(notification))
    
    # Return updated application
    updated_application = db.applications.find_one({"_id": application["_id"]})
    return {"message": "Application updated successfully", "application": fix_objectid(updated_application)}

@router.get("/application_for_edit/{application_id}")
async def get_application_for_edit(application_id: str, user=Depends(get_current_user)):
    # Find the application - try both ObjectId format and job_id format
    application = None
    
    # First try as ObjectId (real application ID)
    try:
        if ObjectId.is_valid(application_id):
            application = db.applications.find_one({"_id": ObjectId(application_id)})
    except:
        pass
    
    # If not found, try as job_id (UUID format)
    if not application:
        application = db.applications.find_one({"job_id": application_id, "user_id": user["user_id"]})
    
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    # Check if user owns this application
    if application["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Unauthorized to access this application")
    
    # Check if application is editable
    if application["status"] not in ["pending", "review"]:
        raise HTTPException(status_code=400, detail="Application cannot be edited in current status")
    
    # Find the job to check deadline and get job details
    job = db.jobs.find_one({"job_id": application["job_id"]})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Check if deadline has passed
    current_time = get_ist_now()
    job_deadline = job.get("expires_at")
    if job_deadline and current_time > job_deadline:
        raise HTTPException(status_code=400, detail="Application deadline has passed")
    
    # Return application data for editing
    application_data = {
        "application_id": str(application["_id"]),
        "job_id": application["job_id"],
        "job_title": job.get("title", ""),
        "job_deadline": job_deadline.isoformat() if job_deadline else None,
        "cover_letter": application.get("cover_letter", ""),
        "linked_in": application.get("linked_in", ""),
        "portfolio": application.get("portfolio", ""),
        "resume_filename": application.get("resume_filename", ""),
        "status": application.get("status", ""),
        "applied_at": application.get("applied_at").isoformat() if application.get("applied_at") else None,
        "updated_at": application.get("updated_at").isoformat() if application.get("updated_at") else None
    }
    
    return {"application": application_data}

@router.get("/application_for_edit_by_job/{job_id}")
async def get_application_for_edit_by_job(job_id: str, user=Depends(get_current_user)):
    # Find the application by job_id and user_id
    application = db.applications.find_one({"job_id": job_id, "user_id": user["user_id"]})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    # Check if application is editable
    if application["status"] not in ["pending", "review"]:
        raise HTTPException(status_code=400, detail="Application cannot be edited in current status")
    
    # Find the job to check deadline and get job details
    job = db.jobs.find_one({"job_id": application["job_id"]})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Check if deadline has passed
    current_time = get_ist_now()
    job_deadline = job.get("expires_at")
    if job_deadline and current_time > job_deadline:
        raise HTTPException(status_code=400, detail="Application deadline has passed")
    
    # Return application data for editing
    application_data = {
        "application_id": str(application["_id"]),
        "job_id": application["job_id"],
        "job_title": job.get("title", ""),
        "job_deadline": job_deadline.isoformat() if job_deadline else None,
        "cover_letter": application.get("cover_letter", ""),
        "linked_in": application.get("linked_in", ""),
        "portfolio": application.get("portfolio", ""),
        "resume_filename": application.get("resume_filename", ""),
        "status": application.get("status", ""),
        "applied_at": application.get("applied_at").isoformat() if application.get("applied_at") else None,
        "updated_at": application.get("updated_at").isoformat() if application.get("updated_at") else None
    }
    
    return {"application": application_data}
