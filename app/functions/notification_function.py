from datetime import datetime
from app.db import db
from app.routes.notification import notification_manager, serialize_notification
from app.utils.email_utils import send_email

async def create_and_send_notification(user_id: str, title: str, message: str, background_tasks=None):
    # Create and save notification
    notification_data = {
        "user_id": user_id,
        "title": title,
        "message": message,
        "read": False,
        "time": datetime.utcnow()
    }
    result = db.notifications.insert_one(notification_data)
    notification_data["id"] = str(result.inserted_id)

    # Send via WebSocket (if connected)
    await notification_manager.send_notification(user_id, serialize_notification(notification_data))

    # Send email (if background_tasks & email exists)
    user = db.users.find_one({"user_id": user_id})
    if user and user.get("email") and background_tasks:
        subject = f"New Notification: {title}"
        html_body = f"<h3>{title}</h3><p>{message}</p>"
        background_tasks.add_task(send_email, user["email"], subject, message, html_body)

    return notification_data
