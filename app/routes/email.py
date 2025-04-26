from fastapi import APIRouter, Query
from app.utils.email_utils import send_email

router = APIRouter()

@router.get("/test-email")
async def test_email(to: str = Query(..., description="Recipient email address")):
    subject = "Test Email from Job Portal"
    body = "This is a test email to verify your SMTP server configuration."
    try:
        send_email(to, subject, body)
        return {"msg": f"Test email sent to {to}"}
    except Exception as e:
        return {"error": str(e)}
