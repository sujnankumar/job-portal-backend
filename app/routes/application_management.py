from fastapi import APIRouter, HTTPException, Request, Header
from app.db import db
from app.utils.jwt_handler import verify_token
from app.routes.notification import notification_manager, serialize_notification
from app.utils.timezone_utils import get_ist_now
from bson import ObjectId
import asyncio

router = APIRouter()

def get_current_user_id_and_type(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload["user_id"], payload["user_type"]

def create_notification(user_id: str, title: str, message: str, notification_type: str = "application"):
    """Create a notification and send it to the user"""
    notification = {
        "user_id": user_id,
        "title": title,
        "message": message,
        "type": notification_type,
        "read": False,
        "time": get_ist_now()
    }
    
    # Insert notification into database
    result = db.notifications.insert_one(notification)
    notification["_id"] = result.inserted_id
    
    # Send real-time notification
    serialized_notification = serialize_notification(notification.copy())
    asyncio.create_task(notification_manager.send_notification(user_id, serialized_notification))
    
    return notification

@router.post("/accept/{application_id}")
async def accept_application(application_id: str, request: Request, authorization: str = Header(None)):
    """Accept an application - only employers can do this"""
    user_id, user_type = get_current_user_id_and_type(authorization)
    
    if user_type != "employer":
        raise HTTPException(status_code=403, detail="Only employers can accept applications")
    
    try:
        # Find the application
        application = db.applications.find_one({"_id": ObjectId(application_id)})
        if not application:
            raise HTTPException(status_code=404, detail="Application not found")
        
        # Verify that the employer owns the job
        job = db.jobs.find_one({"job_id": application["job_id"]})
        if not job or job["employer_id"] != user_id:
            raise HTTPException(status_code=403, detail="You can only manage applications for your own jobs")
        
        # Check if application is already processed
        if application["status"] in ["accepted", "rejected"]:
            raise HTTPException(status_code=400, detail=f"Application has already been {application['status']}")
        
        # Get additional data from request body (optional)
        data = await request.json() if request.headers.get('content-type') == 'application/json' else {}
        feedback_message = data.get("message", "")
        
        # Update application status to accepted
        update_data = {
            "status": "accepted",
            "status_updated_at": get_ist_now(),
            "employer_feedback": feedback_message
        }
        
        result = db.applications.update_one(
            {"_id": ObjectId(application_id)},
            {"$set": update_data}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Application not found")
        
        # Get applicant details
        applicant = db.users.find_one({"user_id": application["user_id"]})
        applicant_name = f"{applicant.get('first_name', '')} {applicant.get('last_name', '')}" if applicant else "Applicant"
        
        # Create notification for the job seeker
        notification_title = "Application Accepted! 🎉"
        notification_message = f"Great news! Your application for '{job['title']}' at {job.get('company_name', 'the company')} has been accepted."
        if feedback_message:
            notification_message += f" Message from employer: {feedback_message}"
        
        create_notification(
            user_id=application["user_id"],
            title=notification_title,
            message=notification_message,
            notification_type="application_accepted"
        )
        
        return {
            "success": True,
            "message": "Application accepted successfully",
            "application_id": application_id,
            "status": "accepted",
            "applicant_name": applicant_name,
            "job_title": job["title"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.post("/reject/{application_id}")
async def reject_application(application_id: str, request: Request, authorization: str = Header(None)):
    """Reject an application - only employers can do this"""
    user_id, user_type = get_current_user_id_and_type(authorization)
    
    if user_type != "employer":
        raise HTTPException(status_code=403, detail="Only employers can reject applications")
    
    try:
        # Find the application
        application = db.applications.find_one({"_id": ObjectId(application_id)})
        if not application:
            raise HTTPException(status_code=404, detail="Application not found")
        
        # Verify that the employer owns the job
        job = db.jobs.find_one({"job_id": application["job_id"]})
        if not job or job["employer_id"] != user_id:
            raise HTTPException(status_code=403, detail="You can only manage applications for your own jobs")
        
        # Check if application is already processed
        if application["status"] in ["accepted", "rejected"]:
            raise HTTPException(status_code=400, detail=f"Application has already been {application['status']}")
        
        # Get additional data from request body (optional)
        data = await request.json() if request.headers.get('content-type') == 'application/json' else {}
        feedback_message = data.get("message", "")
        reason = data.get("reason", "")
        
        # Update application status to rejected
        update_data = {
            "status": "rejected",
            "status_updated_at": get_ist_now(),
            "employer_feedback": feedback_message,
            "rejection_reason": reason
        }
        
        result = db.applications.update_one(
            {"_id": ObjectId(application_id)},
            {"$set": update_data}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Application not found")
        
        # Get applicant details
        applicant = db.users.find_one({"user_id": application["user_id"]})
        applicant_name = f"{applicant.get('first_name', '')} {applicant.get('last_name', '')}" if applicant else "Applicant"
        
        # Create notification for the job seeker
        notification_title = "Application Update"
        notification_message = f"Thank you for your interest in '{job['title']}' at {job.get('company_name', 'the company')}. Unfortunately, we have decided to move forward with other candidates."
        if feedback_message:
            notification_message += f" Feedback: {feedback_message}"
        
        create_notification(
            user_id=application["user_id"],
            title=notification_title,
            message=notification_message,
            notification_type="application_rejected"
        )
        
        return {
            "success": True,
            "message": "Application rejected successfully",
            "application_id": application_id,
            "status": "rejected",
            "applicant_name": applicant_name,
            "job_title": job["title"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/status/{application_id}")
async def get_application_status(application_id: str, authorization: str = Header(None)):
    """Get application status - accessible by both employer and applicant"""
    user_id, user_type = get_current_user_id_and_type(authorization)
    
    try:
        # Find the application
        application = db.applications.find_one({"_id": ObjectId(application_id)})
        if not application:
            raise HTTPException(status_code=404, detail="Application not found")
        
        # Check authorization
        if user_type == "job_seeker" and application["user_id"] != user_id:
            raise HTTPException(status_code=403, detail="You can only view your own applications")
        elif user_type == "employer":
            job = db.jobs.find_one({"job_id": application["job_id"]})
            if not job or job["employer_id"] != user_id:
                raise HTTPException(status_code=403, detail="You can only view applications for your own jobs")
        else:
            raise HTTPException(status_code=403, detail="Unauthorized user type")
        
        # Get job details
        job = db.jobs.find_one({"job_id": application["job_id"]})
        
        # Get applicant details (only for employers)
        applicant_details = None
        if user_type == "employer":
            applicant = db.users.find_one({"user_id": application["user_id"]})
            if applicant:
                applicant_details = {
                    "name": f"{applicant.get('first_name', '')} {applicant.get('last_name', '')}",
                    "email": applicant.get("email", "")
                }
        
        response_data = {
            "application_id": str(application["_id"]),
            "status": application["status"],
            "applied_at": application.get("applied_at"),
            "status_updated_at": application.get("status_updated_at"),
            "employer_feedback": application.get("employer_feedback", ""),
            "rejection_reason": application.get("rejection_reason", ""),
            "job_title": job["title"] if job else "Unknown Job",
            "company_name": job.get("company_name", "") if job else ""
        }
        
        if applicant_details:
            response_data["applicant"] = applicant_details
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/pending")
async def get_pending_applications(authorization: str = Header(None)):
    """Get all pending applications for an employer's jobs"""
    user_id, user_type = get_current_user_id_and_type(authorization)
    
    if user_type != "employer":
        raise HTTPException(status_code=403, detail="Only employers can view pending applications")
    
    try:
        # Get all jobs for this employer
        jobs = list(db.jobs.find({"employer_id": user_id}, {"_id": 0, "job_id": 1, "title": 1, "company_name": 1}))
        job_ids = [job["job_id"] for job in jobs]
        
        # Get all pending applications for these jobs
        pending_applications = list(db.applications.find({
            "job_id": {"$in": job_ids},
            "status": "pending"
        }))
        
        # Enrich applications with job and applicant details
        enriched_applications = []
        for app in pending_applications:
            # Get job details
            job = next((j for j in jobs if j["job_id"] == app["job_id"]), None)
            
            # Get applicant details
            applicant = db.users.find_one({"user_id": app["user_id"]})
            
            enriched_app = {
                "application_id": str(app["_id"]),
                "job_id": app["job_id"],
                "job_title": job["title"] if job else "Unknown Job",
                "company_name": job.get("company_name", "") if job else "",
                "applicant_name": f"{applicant.get('first_name', '')} {applicant.get('last_name', '')}" if applicant else "Unknown Applicant",
                "applicant_email": applicant.get("email", "") if applicant else "",
                "applied_at": app.get("applied_at"),
                "status": app["status"]
            }
            enriched_applications.append(enriched_app)
        
        return {
            "success": True,
            "pending_applications": enriched_applications,
            "total_count": len(enriched_applications)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
