from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel, EmailStr
import logging
import hashlib
import json

from app.utils.jwt_handler import verify_token
from app.functions import subscription_functions as subs
from app.db import db
from app.config.settings import PHONEPE_SALT_KEY, PHONEPE_SALT_INDEX, FRONTEND_BASE_URL

router = APIRouter()
logger = logging.getLogger(__name__)

class AddMemberRequest(BaseModel):
    employer_email: EmailStr

class RemoveMemberRequest(BaseModel):
    employer_email: EmailStr

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
    """Get current user's subscription (direct or via team membership)."""
    user = _auth_employer(request)
    
    # Check direct subscription first
    direct_sub = subs.get_active_subscription(user["user_id"])
    
    # Check team membership access
    user_doc = db.users.find_one({"user_id": user["user_id"]}, {"email": 1})
    team_sub = None
    if user_doc and user_doc.get("email"):
        team_sub = subs.get_employer_subscription_access(user_doc["email"])
    
    # Determine which subscription to return
    subscription = None
    access_type = "direct"
    
    if direct_sub:
        subscription = direct_sub
        access_type = "direct"
    elif team_sub:
        subscription = team_sub
        access_type = "team_member"
    else:
        # Auto-provision free plan
        subscription = subs.create_or_update_subscription(user["user_id"], "free", "FREE-AUTO")
        access_type = "direct"

    return {
        "subscription": subscription,
        "access_type": access_type,
        "is_owner": access_type == "direct" and subscription.get("employer_id") == user["user_id"]
    }

@router.post("/initiate/{plan_id}")
async def initiate_payment(plan_id: str, request: Request):
    """Initiate payment for a subscription plan."""
    user = _auth_employer(request)
    plan_id = plan_id.strip().lower()

    # Prevent downgrades (only allow same or higher tier purchases)
    PLAN_ORDER = ["free", "basic", "pro", "premium", "enterprise"]
    try:
        current_sub = subs.get_effective_subscription(user["user_id"])
        current_plan = (current_sub or {}).get("plan_id", "free")
        if plan_id not in PLAN_ORDER:
            raise HTTPException(status_code=400, detail="Unknown plan")
        if current_plan in PLAN_ORDER and PLAN_ORDER.index(plan_id) < PLAN_ORDER.index(current_plan):
            raise HTTPException(status_code=400, detail=f"Downgrade not allowed from {current_plan} to {plan_id}")
    except HTTPException:
        raise
    except Exception:
        # If plan resolution fails, continue silently (failsafe)
        pass

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
        """Compute expected X-VERIFY checksum for callback verification."""
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
    """Handle PhonePe redirect callback (GET) then bounce user to frontend UI.

    Logic:
    - Lookup order & evaluate payment status
    - Build frontend redirect: /subscribe?success=1|pending=1|error=1&txn=...&plan=...
    - If client explicitly wants JSON (Accept: application/json), return JSON
    - Otherwise issue HTTP 302 redirect to FRONTEND_BASE_URL
    """
    order = db.subscription_orders.find_one({"merchant_transaction_id": merchant_transaction_id})
    if not order:
        # Unknown transaction -> redirect with error flag
        target = f"{FRONTEND_BASE_URL.rstrip('/')}/subscribe?error=1&reason=unknown&txn={merchant_transaction_id}"
        if 'application/json' in (request.headers.get('accept') or '').lower():
            return JSONResponse({
                "status": "unknown_transaction",
                "redirect_url": target,
            }, status_code=404)
        return RedirectResponse(target, status_code=302)

    result = subs.handle_payment_callback(order["employer_id"], merchant_transaction_id)

    status = result.get("status")  # expected: paid|pending|failed
    plan_id = result.get("plan_id") or order.get("plan_id")
    # Map internal status to query params
    if status == "paid":
        qp = "success=1"
    elif status == "pending":
        qp = "pending=1"
    else:
        qp = "error=1"

    target = f"{FRONTEND_BASE_URL.rstrip('/')}/subscribe?{qp}&txn={merchant_transaction_id}"
    if plan_id:
        target += f"&plan={plan_id}"

    # Always include redirect_url in JSON body for transparency
    result["redirect_url"] = target

    if 'application/json' in (request.headers.get('accept') or '').lower():
        return JSONResponse(result)
    return RedirectResponse(target, status_code=302)

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

@router.get("/can-post")
def can_post_job(request: Request):
    """Check if authenticated employer can post another job. Returns plan status and upgrade message if blocked."""
    user = _auth_employer(request)
    
    # Get user email for team membership check
    user_doc = db.users.find_one({"user_id": user["user_id"]}, {"email": 1})
    user_email = user_doc.get("email") if user_doc else None
    
    # Use enhanced function that checks both direct subscription and team membership
    allowed, plan_id, message, subscription_id = subs.can_employer_post_job(user["user_id"], user_email)
    
    # Get subscription details for usage stats
    sub = subs.get_effective_subscription(user["user_id"])
    if not sub and user_email:
        sub = subs.get_employer_subscription_access(user_email)
    
    plan, _ = subs._resolve_plan(sub) if sub else (subs.PLANS["free"], "free")
    
    # Fallback counts
    posts_used_month = sub.get("posts_used_month", 0) if sub else 0
    posts_used_year = sub.get("posts_used_year", 0) if sub else 0
    monthly_limit = plan.get("monthly_post_limit")
    yearly_limit = plan.get("yearly_post_limit")

    reason = None
    if not allowed:
        if yearly_limit is not None and posts_used_year >= yearly_limit:
            reason = "YEARLY_LIMIT"
        elif monthly_limit is not None and posts_used_month >= monthly_limit:
            reason = "MONTHLY_LIMIT"
        else:
            reason = "LIMIT_REACHED"

    return {
        "allowed": allowed,
        "reason": reason,
        "plan_id": plan_id,
        "monthly_limit": monthly_limit,
        "yearly_limit": yearly_limit,
        "posts_used_month": posts_used_month,
        "posts_used_year": posts_used_year,
        "message": message,
        "subscription_id": subscription_id
    }

# ---------------- Team Management Endpoints ----------------

@router.post("/members/add")
def add_team_member(request: Request, member_request: AddMemberRequest):
    """Add a team member to premium or enterprise subscription."""
    user = _auth_employer(request)
    
    # Get user's active subscription
    sub = subs.get_effective_subscription(user["user_id"])
    if not sub:
        raise HTTPException(status_code=404, detail="No active subscription found")
    
    plan_id = sub.get("plan_id")
    if plan_id not in ["premium", "enterprise"]:
        raise HTTPException(status_code=403, detail="Team members only available for Premium and Enterprise plans")
    
    # Verify the requesting user is the subscription owner
    if sub.get("employer_id") != user["user_id"]:
        raise HTTPException(status_code=403, detail="Only subscription owner can add members")
    
    # Check if the email being added is a valid employer
    target_user = db.users.find_one({
        "email": member_request.employer_email.lower(),
        "user_type": "employer"
    })
    
    if not target_user:
        raise HTTPException(status_code=404, detail="Employer with this email not found")
    
    # For enterprise plans, check if the target user is from the same company
    if plan_id == "enterprise":
        user_doc = db.users.find_one({"user_id": user["user_id"]}, {"company_id": 1})
        target_company = target_user.get("company_id")
        owner_company = user_doc.get("company_id") if user_doc else None
        
        if not owner_company or target_company != owner_company:
            raise HTTPException(status_code=403, detail="Enterprise plan members must be from the same company")
    
    result = subs.add_subscription_member(
        sub["subscription_id"], 
        user["user_id"], 
        member_request.employer_email,
        user["user_id"]
    )
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return {"message": result["message"], "subscription_id": sub["subscription_id"]}

@router.post("/members/remove")
def remove_team_member(request: Request, member_request: RemoveMemberRequest):
    """Remove a team member from subscription."""
    user = _auth_employer(request)
    
    # Get user's active subscription
    sub = subs.get_effective_subscription(user["user_id"])
    if not sub:
        raise HTTPException(status_code=404, detail="No active subscription found")
    
    # Verify the requesting user is the subscription owner
    if sub.get("employer_id") != user["user_id"]:
        raise HTTPException(status_code=403, detail="Only subscription owner can remove members")
    
    result = subs.remove_subscription_member(sub["subscription_id"], member_request.employer_email)
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return {"message": result["message"]}

@router.get("/members")
def list_team_members(request: Request):
    """List all team members of the subscription."""
    user = _auth_employer(request)
    
    # Get user's active subscription
    sub = subs.get_effective_subscription(user["user_id"])
    if not sub:
        raise HTTPException(status_code=404, detail="No active subscription found")
    
    plan_id = sub.get("plan_id")
    if plan_id not in ["premium", "enterprise"]:
        return {"members": [], "plan_id": plan_id, "message": "Team members only available for Premium and Enterprise plans"}
    
    members = subs.get_subscription_members(sub["subscription_id"])
    
    # Enrich with user details
    enriched_members = []
    for member in members:
        user_details = db.users.find_one(
            {"email": member["employer_email"]},
            {"name": 1, "email": 1, "company_name": 1, "_id": 0}
        )
        if user_details:
            member.update(user_details)
        enriched_members.append(member)
    
    # Get limits
    max_members = 4 if plan_id == "premium" else None
    current_count = len(members)
    
    return {
        "members": enriched_members,
        "plan_id": plan_id,
        "current_count": current_count,
        "max_members": max_members,
        "can_add_more": max_members is None or current_count < max_members
    }

@router.get("/access-check")
def check_subscription_access(request: Request):
    """Check if employer has subscription access (direct or via team membership)."""
    user = _auth_employer(request)
    
    # Check direct subscription
    direct_sub = subs.get_effective_subscription(user["user_id"])
    
    # Check team membership access
    user_doc = db.users.find_one({"user_id": user["user_id"]}, {"email": 1})
    team_sub = None
    if user_doc and user_doc.get("email"):
        team_sub = subs.get_employer_subscription_access(user_doc["email"])
    
    access_type = None
    active_sub = None
    
    if direct_sub:
        access_type = "direct"
        active_sub = direct_sub
    elif team_sub:
        access_type = "team_member"
        active_sub = team_sub
    
    if not active_sub:
        # Auto-provision free plan
        active_sub = subs.create_or_update_subscription(user["user_id"], "free", "FREE-AUTO")
        access_type = "direct"
    
    plan, plan_id = subs._resolve_plan(active_sub)
    
    return {
        "has_access": True,
        "access_type": access_type,
        "subscription": active_sub,
        "plan_id": plan_id,
        "plan": plan
    }

@router.get("/company-employees")
def get_company_employees_access(request: Request):
    """Get all employees who have access via enterprise subscription."""
    user = _auth_employer(request)
    
    # Get user's company
    user_doc = db.users.find_one({"user_id": user["user_id"]}, {"company_id": 1})
    if not user_doc or not user_doc.get("company_id"):
        raise HTTPException(status_code=404, detail="User not associated with any company")
    
    company_id = user_doc["company_id"]
    
    # Check if there's an active enterprise subscription for this company
    enterprise_sub = subs.get_company_enterprise_subscription(company_id)
    if not enterprise_sub:
        return {"employees": [], "message": "No enterprise subscription found for company"}
    
    # Get all employees with access
    employees = subs.get_company_employees_with_subscription_access(company_id)
    
    return {
        "employees": employees,
        "company_id": company_id,
        "subscription_id": enterprise_sub["subscription_id"],
        "plan_id": enterprise_sub["plan_id"]
    }
