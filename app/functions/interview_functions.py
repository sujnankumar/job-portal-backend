from app.db import db
from datetime import datetime
from bson import ObjectId
from app.utils import zoom_utils
from app.routes.notification import notification_manager, serialize_notification

def schedule_interview(hr_id: str, candidate_id: str, job_id: str, scheduled_time: str, zoom_link: str = None, details: dict = None):
    interview_data = {
        "hr_id": hr_id,
        "candidate_id": candidate_id,
        "job_id": job_id,
        "scheduled_time": scheduled_time,  # ISO string
        "details": details or {},
        "created_at": datetime.utcnow(),
        "status": "scheduled"
    }
    # Handle Zoom meeting creation if needed
    if details and details.get("interviewType") == "video":
        if not zoom_link:
            # Optionally, you could use the HR's email or a default for Zoom host
            zoom_meeting = zoom_utils.create_zoom_meeting(
                user_id=hr_id,  # You may want to use HR's email if available
                topic=f"Interview for job {job_id}",
                start_time=scheduled_time,
                duration=int(details.get("duration", 30))
            )
            interview_data["zoom_link"] = zoom_meeting["join_url"]
            interview_data["zoom_start_url"] = zoom_meeting["start_url"]
        else:
            interview_data["zoom_link"] = zoom_link
    elif zoom_link:
        interview_data["zoom_link"] = zoom_link
    result = db.interviews.insert_one(interview_data)
    # Create notifications for HR and candidate
    # Get job and user info for better notification text
    job = db.jobs.find_one({"job_id": job_id})
    job_title = job["title"] if job and "title" in job else "the job"
    employer = db.users.find_one({"user_id": hr_id})
    candidate = db.users.find_one({"user_id": candidate_id})
    employer_name = f"{employer.get('first_name', '')} {employer.get('last_name', '')}" if employer else "Employer"
    candidate_name = f"{candidate.get('first_name', '')} {candidate.get('last_name', '')}" if candidate else "Candidate"
    time_str = scheduled_time
    # Notification for employer
    notif_employer = {
        "user_id": hr_id,
        "type": "interview",
        "title": "Interview Scheduled",
        "description": f"Interview with {candidate_name} for {job_title} scheduled at {time_str}.",
        "time": datetime.utcnow(),
        "read": False,
        "link": f"/employer/dashboard/applications/{job_id}"
    }
    # Notification for candidate
    notif_candidate = {
        "user_id": candidate_id,
        "type": "interview",
        "title": "Interview Scheduled",
        "description": f"Interview with {employer_name} for {job_title} scheduled at {time_str}.",
        "time": datetime.utcnow(),
        "read": False,
        "link": f"/applications"
    }
    db.notifications.insert_many([notif_employer, notif_candidate])
    # Real-time push
    import asyncio
    asyncio.create_task(notification_manager.send_notification(hr_id, serialize_notification(notif_employer)))
    asyncio.create_task(notification_manager.send_notification(candidate_id, serialize_notification(notif_candidate)))
    return {"msg": "Interview scheduled", "interview_id": str(result.inserted_id), "zoom_link": interview_data.get("zoom_link")}

def edit_interview(interview_id: str, user_id: str, data: dict):
    interview = db.interviews.find_one({"_id": ObjectId(interview_id)})
    if not interview:
        return {"error": "Interview not found", "status": 404}
    # Only employer or candidate can edit
    if user_id not in [interview["hr_id"], interview["candidate_id"]]:
        return {"error": "Not authorized to edit this interview", "status": 403}
    # Update interview details
    update_fields = {}
    for field in ["scheduled_time", "details"]:
        if field in data:
            update_fields[field] = data[field]
    if not update_fields:
        return {"error": "No valid fields to update", "status": 400}
    db.interviews.update_one({"_id": ObjectId(interview_id)}, {"$set": update_fields})
    # Fetch updated interview and job/candidate/employer info
    updated_interview = db.interviews.find_one({"_id": ObjectId(interview_id)})
    job = db.jobs.find_one({"job_id": updated_interview["job_id"]})
    job_title = job["title"] if job and "title" in job else "the job"
    employer = db.users.find_one({"user_id": updated_interview["hr_id"]})
    candidate = db.users.find_one({"user_id": updated_interview["candidate_id"]})
    employer_name = f"{employer.get('first_name', '')} {employer.get('last_name', '')}" if employer else "Employer"
    candidate_name = f"{candidate.get('first_name', '')} {candidate.get('last_name', '')}" if candidate else "Candidate"
    time_str = update_fields.get("scheduled_time", updated_interview.get("scheduled_time"))
    # Notifications
    notif_employer = {
        "user_id": updated_interview["hr_id"],
        "type": "interview",
        "title": "Interview Rescheduled",
        "description": f"Interview with {candidate_name} for {job_title} has been rescheduled to {time_str}.",
        "time": datetime.utcnow(),
        "read": False,
        "link": f"/employer/dashboard/applications/{updated_interview['job_id']}"
    }
    notif_candidate = {
        "user_id": updated_interview["candidate_id"],
        "type": "interview",
        "title": "Interview Rescheduled",
        "description": f"Interview with {employer_name} for {job_title} has been rescheduled to {time_str}.",
        "time": datetime.utcnow(),
        "read": False,
        "link": f"/applications"
    }
    db.notifications.insert_many([notif_employer, notif_candidate])
    import asyncio
    asyncio.create_task(notification_manager.send_notification(updated_interview["hr_id"], serialize_notification(notif_employer)))
    asyncio.create_task(notification_manager.send_notification(updated_interview["candidate_id"], serialize_notification(notif_candidate)))
    return {"msg": "Interview updated and notifications sent"}

def get_interviews_for_user(user_id: str):
    return list(db.interviews.find({"$or": [{"hr_id": user_id}, {"candidate_id": user_id}]}, {"_id": 0}))

def get_notifications(user_id: str):
    return list(db.notifications.find({"user_id": user_id}, {"_id": 0}))

def mark_notification_read(user_id: str, notification_id: str):
    result = db.notifications.update_one({"user_id": user_id, "_id": ObjectId(notification_id)}, {"$set": {"read": True}})
    return result.modified_count == 1
