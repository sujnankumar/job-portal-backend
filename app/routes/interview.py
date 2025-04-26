from fastapi import APIRouter, HTTPException, Request, Depends, Header
from app.functions import interview_functions
from app.utils.jwt_handler import verify_token

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
    required = ["candidate_id", "job_id", "scheduled_time", "zoom_link"]
    for field in required:
        if not data.get(field):
            raise HTTPException(status_code=400, detail=f"{field} is required")
    return interview_functions.schedule_interview(
        hr_id=user_id,
        candidate_id=data["candidate_id"],
        job_id=data["job_id"],
        scheduled_time=data["scheduled_time"],
        zoom_link=data["zoom_link"],
        details=data.get("details", "")
    )

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
