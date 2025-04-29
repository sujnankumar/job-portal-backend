from app.db import db
from datetime import datetime
from bson import ObjectId
from app.utils import zoom_utils

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
    db.notifications.insert_many([
        {"user_id": hr_id, "message": f"Interview scheduled with candidate {candidate_id} for job {job_id} at {scheduled_time}.", "created_at": datetime.utcnow(), "read": False},
        {"user_id": candidate_id, "message": f"Interview scheduled with HR {hr_id} for job {job_id} at {scheduled_time}.", "created_at": datetime.utcnow(), "read": False}
    ])
    return {"msg": "Interview scheduled", "interview_id": str(result.inserted_id), "zoom_link": interview_data.get("zoom_link")}

def get_interviews_for_user(user_id: str):
    return list(db.interviews.find({"$or": [{"hr_id": user_id}, {"candidate_id": user_id}]}, {"_id": 0}))

def get_notifications(user_id: str):
    return list(db.notifications.find({"user_id": user_id}, {"_id": 0}))

def mark_notification_read(user_id: str, notification_id: str):
    result = db.notifications.update_one({"user_id": user_id, "_id": ObjectId(notification_id)}, {"$set": {"read": True}})
    return result.modified_count == 1
