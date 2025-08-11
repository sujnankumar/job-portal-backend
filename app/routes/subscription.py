from fastapi import APIRouter, Request, HTTPException
from app.utils.jwt_handler import verify_token
from app.functions import subscription_functions as subs
from app.db import db

router = APIRouter()


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


@router.get("/phonepe/callback/{merchant_transaction_id}")
def phonepe_callback(merchant_transaction_id: str, request: Request):
    # In real scenario PhonePe hits this without auth; we map txn -> employer via stored order
    order = db.subscription_orders.find_one({"merchant_transaction_id": merchant_transaction_id})
    if not order:
        return {"status": "unknown_transaction"}
    result = subs.handle_payment_callback(order["employer_id"], merchant_transaction_id)
    return result
