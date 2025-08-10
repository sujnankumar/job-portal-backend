from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from app.utils.jwt_handler import verify_token
from app.functions.notification_function import create_and_send_notification

router = APIRouter()

class NotificationRequest(BaseModel):
    user_id: str
    title: str
    message: str
    token: str

@router.post("/send-notification")
async def send_notification(request: NotificationRequest, background_tasks: BackgroundTasks):
    # Auth check
    try:
        current_user = verify_token(request.token)
    except:
        raise HTTPException(status_code=401, detail="Invalid token")

    if current_user.get("user_type") != "employer":
        raise HTTPException(status_code=403, detail="Only employers can send notifications")

    notification = await create_and_send_notification(
        user_id=request.user_id,
        title=request.title,
        message=request.message,
        background_tasks=background_tasks
    )

    return {"detail": "Notification sent", "notification": notification}
