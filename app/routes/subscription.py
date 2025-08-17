from fastapi import APIRouter, Request, HTTPException
import logging
import hashlib
import json

from app.utils.jwt_handler import verify_token
from app.functions import subscription_functions as subs
from app.db import db
from app.config.settings import PHONEPE_SALT_KEY, PHONEPE_SALT_INDEX

router = APIRouter()
logger = logging.getLogger(__name__)

def _auth_employer(request: Request):
    """Authenticate employer from JWT token."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")

    token = auth_header.split(" ", 1)[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    if payload.get("user_type") != "employer":
        raise HTTPException(status_code=403, detail="Employers only")

    return payload

@router.get("/plans")
def list_plans():
    """Get all available subscription plans."""
    return {"plans": subs.PLANS}

@router.get("/me")
def my_subscription(request: Request):
    """Get current user's subscription."""
    user = _auth_employer(request)
    sub = subs.get_active_subscription(user["user_id"])

    if not sub:
        # Auto-provision free plan
        sub = subs.create_or_update_subscription(user["user_id"], "free", "FREE-AUTO")

    return {"subscription": sub}

@router.post("/initiate/{plan_id}")
async def initiate_payment(plan_id: str, request: Request):
    """Initiate payment for a subscription plan."""
    user = _auth_employer(request)
    plan_id = plan_id.strip().lower()

    merchant_txn_id = None
    if plan_id != "free":
        # Generate unique merchant transaction ID
        import uuid, datetime
        short = uuid.uuid4().hex[:10]
        ts = datetime.datetime.utcnow().strftime('%y%m%d%H%M')
        merchant_txn_id = f"SUB{ts}-{plan_id}-{short}"

    # Get company ID for enterprise plans
    user_doc = db.users.find_one({"user_id": user["user_id"]}, {"company_id": 1, "_id": 0}) or {}
    company_id = user_doc.get("company_id") if plan_id == "enterprise" else None

    # Create pending order
    if merchant_txn_id:
        subs.create_pending_order(user["user_id"], plan_id, merchant_txn_id, company_id=company_id)

    # Initiate payment
    data = subs.initiate_payment(user["user_id"], plan_id, merchant_txn_id)

    # Ensure transaction ID is in response
    if merchant_txn_id and isinstance(data, dict) and "merchantTransactionId" not in data:
        data["merchantTransactionId"] = merchant_txn_id

    return data

@router.post("/phonepe/callback/{merchant_transaction_id}")
async def phonepe_callback(merchant_transaction_id: str, request: Request):
    """Handle PhonePe payment callback (webhook)."""
    body_bytes = await request.body()
    body_text = body_bytes.decode() if body_bytes else ""
    headers = request.headers

    x_verify = headers.get("X-VERIFY") or headers.get("x-verify")

    # Log callback for auditing
    db.phonepe_callbacks.insert_one({
        "merchant_transaction_id": merchant_transaction_id,
        "headers": dict(headers),
        "body": body_text,
        "received_at": subs.get_ist_now(),
    })

    def _verify_signature(payload_text: str, txn_id: str) -> str:
        """
        Compute expected X-VERIFY checksum for callback verification.
        Note: For callbacks, the payload is the response body.
        """
        endpoint = f"/pg/v1/status/{subs.PHONEPE_MERCHANT_ID}/{txn_id}"
        raw = payload_text + endpoint + PHONEPE_SALT_KEY
        sha256_hash = hashlib.sha256(raw.encode()).hexdigest()
        return f"{sha256_hash}###{PHONEPE_SALT_INDEX}"

    # Find the order
    order = db.subscription_orders.find_one({
        "merchant_transaction_id": merchant_transaction_id
    })

    if not order:
        return {"status": "unknown_transaction"}

    # Verify signature if provided
    signature_verified = False
    if x_verify and body_text:
        try:
            expected = _verify_signature(body_text, merchant_transaction_id)
            if x_verify == expected:
                signature_verified = True
                logger.info(f"Signature verified for {merchant_transaction_id}")
            else:
                logger.warning(f"Signature mismatch for {merchant_transaction_id}")
        except Exception as e:
            logger.warning(f"Signature verification error for {merchant_transaction_id}: {e}")

    # Process callback
    result = subs.handle_payment_callback(
        order["employer_id"], 
        merchant_transaction_id, 
        verified=signature_verified
    )

    return result

@router.get("/phonepe/callback/{merchant_transaction_id}")
def phonepe_callback_get(merchant_transaction_id: str, request: Request):
    """Handle PhonePe redirect callback (GET method)."""
    order = db.subscription_orders.find_one({
        "merchant_transaction_id": merchant_transaction_id
    })

    if not order:
        return {"status": "unknown_transaction"}

    result = subs.handle_payment_callback(order["employer_id"], merchant_transaction_id)
    return result

@router.post("/attempt-bulk-post/{count}")
def attempt_bulk_post(count: int, request: Request):
    """Attempt to bulk post jobs (for testing limits)."""
    user = _auth_employer(request)
    allowed, plan_id, message, subscription_id = subs.attempt_bulk_post_jobs(user["user_id"], count)

    return {
        "allowed": allowed,
        "plan_id": plan_id,
        "message": message,
        "subscription_id": subscription_id,
        "count": count,
    }

@router.get("/usage/{employer_id}")
def get_usage_stats(employer_id: str, request: Request):
    """Get current usage statistics for an employer."""
    user = _auth_employer(request)
    
    # Only allow access to own data or admin access
    if user["user_id"] != employer_id:
        raise HTTPException(status_code=403, detail="Access denied")

    sub = subs.get_effective_subscription(employer_id)
    plan, plan_id = subs._resolve_plan(sub)

    result = {
        "employer_id": employer_id,
        "plan_id": plan_id,
        "plan": plan,
        "subscription": sub,
    }

    if sub:
        result.update({
            "posts_used_month": sub.get("posts_used_month", 0),
            "posts_used_year": sub.get("posts_used_year", 0),
            "monthly_limit": plan.get("monthly_post_limit"),
            "yearly_limit": plan.get("yearly_post_limit"),
            "expires_at": sub.get("expires_at"),
        })

    return result
