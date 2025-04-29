from fastapi import APIRouter, HTTPException, Request, Depends, Header
from app.functions import interview_functions
from app.utils.jwt_handler import verify_token
from app.db import db

router = APIRouter()

def get_current_user_id_and_type(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload["user_id"], payload["user_type"]

@router.post("/schedule")
async def schedule_interview(request: Request, authorization: str = Header(None)):
    user_id, user_type = get_current_user_id_and_type(authorization)
    if user_type != "employer":
        raise HTTPException(status_code=403, detail="Only HRs can schedule interviews")
    data = await request.json()
    required = ["candidate_id", "job_id", "date", "startTime", "duration", "interviewType"]
    for field in required:
        if not data.get(field):
            raise HTTPException(status_code=400, detail=f"{field} is required")
    # Combine date and startTime into scheduled_time (ISO format)
    from datetime import datetime
    try:
        scheduled_time = datetime.strptime(f"{data['date']} {data['startTime']}", "%Y-%m-%d %H:%M").isoformat()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid date or startTime format")
    # Only require zoom_link if interviewType is video
    zoom_link = data.get("zoomLink") if data.get("interviewType") == "video" else None
    if data.get("interviewType") == "video" and not zoom_link:
        raise HTTPException(status_code=400, detail="zoomLink is required for video interviews")
    details = {
        "interviewType": data.get("interviewType"),
        "interviewers": data.get("interviewers"),
        "notes": data.get("notes"),
        "duration": data.get("duration")
    }
    result = interview_functions.schedule_interview(
        hr_id=user_id,
        candidate_id=data["candidate_id"],
        job_id=data["job_id"],
        scheduled_time=scheduled_time,
        zoom_link=zoom_link,
        details=details
    )
    # Update application status to 'interview'
    db.applications.update_one(
        {"job_id": data["job_id"], "user_id": data["candidate_id"]},
        {"$set": {"status": "interview", "interview_date": data["date"], "interview_time": data["startTime"]}}
    )
    return result

@router.get("/my_interviews")
async def my_interviews(authorization: str = Header(None)):
    user_id, _ = get_current_user_id_and_type(authorization)
    return interview_functions.get_interviews_for_user(user_id)

@router.get("/notifications")
async def get_notifications(authorization: str = Header(None)):
    user_id, _ = get_current_user_id_and_type(authorization)
    return interview_functions.get_notifications(user_id)

@router.post("/notifications/mark_read/{notification_id}")
async def mark_notification_read(notification_id: str, authorization: str = Header(None)):
    user_id, _ = get_current_user_id_and_type(authorization)
    if interview_functions.mark_notification_read(user_id, notification_id):
        return {"msg": "Notification marked as read"}
    raise HTTPException(status_code=404, detail="Notification not found")
