from app.db import db
from datetime import datetime
from bson import ObjectId
from app.utils import zoom_utils

def schedule_interview(hr_id: str, candidate_id: str, job_id: str, scheduled_time: str, zoom_host_email: str, details: str = ""):
    # Create Zoom meeting
    zoom_meeting = zoom_utils.create_zoom_meeting(
        user_id=zoom_host_email,  # HR's Zoom email
        topic=f"Interview for job {job_id}",
        start_time=scheduled_time,
        duration=30
    )
    interview = {
        "hr_id": hr_id,
        "candidate_id": candidate_id,
        "job_id": job_id,
        "scheduled_time": scheduled_time,  # ISO string
        "zoom_link": zoom_meeting["join_url"],
        "zoom_start_url": zoom_meeting["start_url"],
        "details": details,
        "created_at": datetime.utcnow(),
        "status": "scheduled"
    }
    result = db.interviews.insert_one(interview)
    # Create notifications for HR and candidate
    db.notifications.insert_many([
        {"user_id": hr_id, "message": f"Interview scheduled with candidate {candidate_id} for job {job_id} at {scheduled_time}. Start meeting: {zoom_meeting['start_url']}", "created_at": datetime.utcnow(), "read": False},
        {"user_id": candidate_id, "message": f"Interview scheduled with HR {hr_id} for job {job_id} at {scheduled_time}. Join meeting: {zoom_meeting['join_url']}", "created_at": datetime.utcnow(), "read": False}
    ])
    return {"msg": "Interview scheduled", "interview_id": str(result.inserted_id), "zoom_link": zoom_meeting["join_url"]}

def get_interviews_for_user(user_id: str):
    return list(db.interviews.find({"$or": [{"hr_id": user_id}, {"candidate_id": user_id}]}, {"_id": 0}))

def get_notifications(user_id: str):
    return list(db.notifications.find({"user_id": user_id}, {"_id": 0}))

def mark_notification_read(user_id: str, notification_id: str):
    result = db.notifications.update_one({"user_id": user_id, "_id": ObjectId(notification_id)}, {"$set": {"read": True}})
    return result.modified_count == 1
