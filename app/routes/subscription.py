from fastapi import APIRouter, Request, HTTPException
import logging
from app.utils.jwt_handler import verify_token
from app.functions import subscription_functions as subs
from app.db import db
from app.config.settings import PHONEPE_SALT_KEY, PHONEPE_SALT_INDEX
import hashlib
import json

router = APIRouter()
logger = logging.getLogger(__name__)


def _auth_employer(request: Request):
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
    return {"plans": subs.PLANS}


@router.get("/me")
def my_subscription(request: Request):
    user = _auth_employer(request)
    sub = subs.get_active_subscription(user["user_id"])
    if not sub:
        # Auto-provision free plan if user has never subscribed
        sub = subs.create_or_update_subscription(user["user_id"], "free", "FREE-AUTO")
    return {"subscription": sub}


@router.post("/initiate/{plan_id}")
async def initiate_payment(plan_id: str, request: Request):
    user = _auth_employer(request)
    merchant_txn_id = None
    if plan_id != "free":
        merchant_txn_id = f"SUB-{plan_id}-{user['user_id'][:8]}"
        subs.create_pending_order(user["user_id"], plan_id, merchant_txn_id)
    data = subs.initiate_payment(user["user_id"], plan_id, merchant_txn_id)
    return data


@router.post("/phonepe/callback/{merchant_transaction_id}")
async def phonepe_callback(merchant_transaction_id: str, request: Request):
    # Accept and validate webhook with checksum if provided
    body_bytes = await request.body()
    body_text = body_bytes.decode() if body_bytes else ""
    headers = request.headers
    x_verify = headers.get("X-VERIFY") or headers.get("x-verify")

    # Persist raw callback for auditing
    db.phonepe_callbacks.insert_one({
        "merchant_transaction_id": merchant_transaction_id,
        "headers": dict(headers),
        "body": body_text,
        "received_at": subs.get_ist_now(),
    })

    def _verify_signature(payload_text: str):
        # As per PhonePe: checksum = SHA256(payload + endpoint + salt_key) + ### + salt_index
        endpoint = f"/pg/v1/status/{subs.PHONEPE_MERCHANT_ID}/{merchant_transaction_id}"
        raw = payload_text + endpoint + PHONEPE_SALT_KEY
        sha256_hash = hashlib.sha256(raw.encode()).hexdigest()
        expected = f"{sha256_hash}###{PHONEPE_SALT_INDEX}"
        return expected

    order = db.subscription_orders.find_one({"merchant_transaction_id": merchant_transaction_id})
    if not order:
        return {"status": "unknown_transaction"}

    # If signature provided and matches, skip verify API call
    if x_verify:
        try:
            expected = _verify_signature(body_text)
            if x_verify == expected:
                result = subs.handle_payment_callback(order["employer_id"], merchant_transaction_id, verified=True)
                return result
            else:
                logger.warning("PhonePe signature mismatch for %s", merchant_transaction_id)
        except Exception as e:  # pragma: no cover
            logger.warning("PhonePe signature verify error for %s: %s", merchant_transaction_id, e)

    # Fallback to verify API
    result = subs.handle_payment_callback(order["employer_id"], merchant_transaction_id)
    return result


# Backward compatible GET route (will always verify via status API)
@router.get("/phonepe/callback/{merchant_transaction_id}")
def phonepe_callback_get(merchant_transaction_id: str, request: Request):
    order = db.subscription_orders.find_one({"merchant_transaction_id": merchant_transaction_id})
    if not order:
        return {"status": "unknown_transaction"}
    result = subs.handle_payment_callback(order["employer_id"], merchant_transaction_id)
    return result


@router.post("/attempt-bulk-post/{count}")
def attempt_bulk_post(count: int, request: Request):
    user = _auth_employer(request)
    allowed, plan_id, message, subscription_id = subs.attempt_bulk_post_jobs(user["user_id"], count)
    return {
        "allowed": allowed,
        "plan_id": plan_id,
        "message": message,
        "subscription_id": subscription_id,
        "count": count,
    }
