from app.db import db
from datetime import datetime
from bson import ObjectId

def schedule_interview(hr_id: str, candidate_id: str, job_id: str, scheduled_time: str, zoom_link: str, details: str = ""):
    interview = {
        "hr_id": hr_id,
        "candidate_id": candidate_id,
        "job_id": job_id,
        "scheduled_time": scheduled_time,  # ISO string
        "zoom_link": zoom_link,
        "details": details,
        "created_at": datetime.utcnow(),
        "status": "scheduled"
    }
    result = db.interviews.insert_one(interview)
    # Create notifications for HR and candidate
    db.notifications.insert_many([
        {"user_id": hr_id, "message": f"Interview scheduled with candidate {candidate_id} for job {job_id} at {scheduled_time}", "created_at": datetime.utcnow(), "read": False},
        {"user_id": candidate_id, "message": f"Interview scheduled with HR {hr_id} for job {job_id} at {scheduled_time}. Zoom link: {zoom_link}", "created_at": datetime.utcnow(), "read": False}
    ])
    return {"msg": "Interview scheduled", "interview_id": str(result.inserted_id)}

def get_interviews_for_user(user_id: str):
    return list(db.interviews.find({"$or": [{"hr_id": user_id}, {"candidate_id": user_id}]}, {"_id": 0}))

def get_notifications(user_id: str):
    return list(db.notifications.find({"user_id": user_id}, {"_id": 0}))

def mark_notification_read(user_id: str, notification_id: str):
    result = db.notifications.update_one({"user_id": user_id, "_id": ObjectId(notification_id)}, {"$set": {"read": True}})
    return result.modified_count == 1
