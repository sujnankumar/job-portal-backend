import uuid
import hashlib
import base64
import json
import requests
from datetime import datetime, timedelta
from app.db import db
from app.config.settings import (
    PHONEPE_MERCHANT_ID,
    PHONEPE_SALT_KEY,
    PHONEPE_SALT_INDEX,
    PHONEPE_BASE_URL,
    PHONEPE_REDIRECT_BASE,
)
from app.utils.timezone_utils import get_ist_now


PLANS = {
    "free": {
        "price": 0,
        "currency": "INR",
        "yearly_post_limit": 5,  # Hard cap overall for free tier
        "monthly_post_limit": 5,
        "access_limit": 1,
        "name": "Free",
    },
    "basic": {
        "price": 2999,
        "currency": "INR",
        "yearly_post_limit": 36,
        "monthly_post_limit": 3,
        "access_limit": 1,
        "name": "Basic",
    },
    "pro": {
        "price": 4999,
        "currency": "INR",
        "yearly_post_limit": 96,
        "monthly_post_limit": 8,
        "access_limit": 1,
        "name": "Pro",
    },
    "premium": {
        "price": 9999,
        "currency": "INR",
        "yearly_post_limit": None,  # Unlimited
        "monthly_post_limit": None,  # Unlimited
        "access_limit": 1,
        "name": "Premium",
    },
    "enterprise": {
        "price": 19999,
        "currency": "INR",
        "yearly_post_limit": None,
        "monthly_post_limit": None,
        "access_limit": None,  # Unlimited users under same company
        "name": "Enterprise",
    },
}


def get_plan(plan_id: str):
    return PLANS.get(plan_id)


def _subscription_collection():
    return db.subscriptions


def get_active_subscription(employer_id: str):
    now = get_ist_now()
    sub = _subscription_collection().find_one(
        {"employer_id": employer_id, "status": "active", "expires_at": {"$gt": now}}, {"_id": 0}
    )
    return sub


def create_or_update_subscription(employer_id: str, plan_id: str, payment_ref: str, duration_days: int = 365, company_id: str | None = None):
    plan = get_plan(plan_id)
    if not plan:
        return None
    now = get_ist_now()
    expires_at = now + timedelta(days=duration_days)
    data = {
        "subscription_id": str(uuid.uuid4()),
        "employer_id": employer_id,
        "plan_id": plan_id,
        "plan_snapshot": plan,
        "status": "active",
        "started_at": now,
        "expires_at": expires_at,
        "payment_reference": payment_ref,
        "posts_used_year": 0,
        "posts_used_month": 0,
        "year": now.year,
        "month": now.month,
    }
    # Scope: enterprise plan applies to entire company
    if plan_id == "enterprise" and company_id:
        data["company_id"] = company_id
        data["scope"] = "company"
    else:
        data["scope"] = "employer"
    # Deactivate previous active subs
    _subscription_collection().update_many(
        {"employer_id": employer_id, "status": "active"}, {"$set": {"status": "replaced"}}
    )
    _subscription_collection().insert_one(data)
    data.pop("_id", None)
    return data


def get_company_enterprise_subscription(company_id: str):
    if not company_id:
        return None
    now = get_ist_now()
    sub = _subscription_collection().find_one({
        "company_id": company_id,
        "plan_id": "enterprise",
        "status": "active",
        "expires_at": {"$gt": now}
    }, {"_id": 0})
    return sub


def can_post_job(employer_id: str):
    """Determine if employer can post a job, considering company-wide enterprise subscription.

    Returns (allowed: bool, plan_id: str, message: str, subscription_id: str | None)
    """
    sub = get_active_subscription(employer_id)
    plan_id = "free"
    plan = PLANS[plan_id]
    now = get_ist_now()

    # Fetch employer user document to derive company_id
    user = db.users.find_one({"user_id": employer_id})
    company_id = user.get("company_id") if user else None

    # If no personal subscription, check for company enterprise
    enterprise_sub = None
    if not sub and company_id:
        enterprise_sub = get_company_enterprise_subscription(company_id)
        if enterprise_sub:
            sub = enterprise_sub

    if sub:
        plan_id = sub["plan_id"]
        plan = sub["plan_snapshot"]
        # Reset counters for non-unlimited plans (or keep counters for enterprise to track usage if present)
        updates = {}
        if sub.get("month") != now.month:
            updates["posts_used_month"] = 0
            updates["month"] = now.month
        if sub.get("year") != now.year:
            updates["posts_used_year"] = 0
            updates["year"] = now.year
        if updates:
            _subscription_collection().update_one({"subscription_id": sub["subscription_id"]}, {"$set": updates})
            sub.update(updates)

        # If enterprise plan found (company scope) -> unlimited
        if plan_id == "enterprise":
            return True, plan_id, "OK", sub["subscription_id"]
        # Premium unlimited for single employer
        if plan_id == "premium":
            return True, plan_id, "OK", sub["subscription_id"]

    # Evaluate limits for limited plans (free/basic/pro)
    yearly_limit = plan.get("yearly_post_limit")
    monthly_limit = plan.get("monthly_post_limit")
    used_year = sub.get("posts_used_year", 0) if sub else _count_jobs(employer_id, year=now.year)
    used_month = sub.get("posts_used_month", 0) if sub else _count_jobs(employer_id, year=now.year, month=now.month)
    if yearly_limit is not None and used_year >= yearly_limit:
        return False, plan_id, "Yearly post limit reached", sub["subscription_id"] if sub else None
    if monthly_limit is not None and used_month >= monthly_limit:
        return False, plan_id, "Monthly post limit reached", sub["subscription_id"] if sub else None
    return True, plan_id, "OK", sub["subscription_id"] if sub else None


def increment_post_counters(employer_id: str, subscription_id: str | None = None):
    """Increment counters on the specific subscription document (if limited plan).

    For unlimited plans we still track usage if counters exist, but they never gate posting.
    """
    now = get_ist_now()
    sub = None
    if subscription_id:
        sub = _subscription_collection().find_one({"subscription_id": subscription_id})
    else:
        sub = get_active_subscription(employer_id)
    if not sub:
        # Possibly enterprise company scope
        user = db.users.find_one({"user_id": employer_id})
        company_id = user.get("company_id") if user else None
        if company_id:
            sub = get_company_enterprise_subscription(company_id)
    if not sub:
        return
    # Increment counts (safe even for unlimited)
    _subscription_collection().update_one(
        {"subscription_id": sub["subscription_id"]},
        {"$inc": {"posts_used_year": 1, "posts_used_month": 1}, "$set": {"month": now.month, "year": now.year}},
    )


def _count_jobs(employer_id: str, year: int, month: int | None = None):
    q = {"employer_id": employer_id}
    if month is not None:
        # Approximation: count jobs with posted_at month/year (requires posted_at stored as datetime)
        start = datetime(year, month, 1, tzinfo=get_ist_now().tzinfo)
        if month == 12:
            end = datetime(year + 1, 1, 1, tzinfo=start.tzinfo)
        else:
            end = datetime(year, month + 1, 1, tzinfo=start.tzinfo)
        return db.jobs.count_documents({"employer_id": employer_id, "posted_at": {"$gte": start, "$lt": end}})
    else:
        start = datetime(year, 1, 1, tzinfo=get_ist_now().tzinfo)
        end = datetime(year + 1, 1, 1, tzinfo=start.tzinfo)
        return db.jobs.count_documents({"employer_id": employer_id, "posted_at": {"$gte": start, "$lt": end}})


# ---------------- PhonePe Integration ----------------

def _build_phonepe_checksum(payload_base64: str, endpoint: str):
    # Checksum format: base64_payload + endpoint + salt_key then SHA256 + ### + salt_index
    raw = payload_base64 + endpoint + PHONEPE_SALT_KEY
    sha256_hash = hashlib.sha256(raw.encode()).hexdigest()
    return f"{sha256_hash}###{PHONEPE_SALT_INDEX}"


def initiate_payment(employer_id: str, plan_id: str, merchant_transaction_id: str | None = None):
    plan = get_plan(plan_id)
    if not plan:
        return {"error": "Invalid plan"}
    if plan["price"] == 0:
        # Immediately activate free plan (or skip if already any active plan)
        existing = get_active_subscription(employer_id)
        if existing and existing["plan_id"] != "free":
            return {"message": "Already subscribed", "subscription": existing}
        sub = create_or_update_subscription(employer_id, "free", "FREE-0")
        return {"message": "Free plan activated", "subscription": sub}
    merchant_transaction_id = merchant_transaction_id or str(uuid.uuid4())
    amount_in_paise = plan["price"] * 100
    endpoint = "/pg/v1/pay"
    redirect_url = f"{PHONEPE_REDIRECT_BASE}/api/subscription/phonepe/callback/{merchant_transaction_id}"
    payload = {
        "merchantId": PHONEPE_MERCHANT_ID,
        "merchantTransactionId": merchant_transaction_id,
        "merchantUserId": employer_id,
        "amount": amount_in_paise,
        "redirectUrl": redirect_url,
        "redirectMode": "REDIRECT",
        "callbackUrl": redirect_url,
        "paymentInstrument": {"type": "PAY_PAGE"},
        "deviceContext": {"deviceOS": "WEB"},
    }
    payload_str = json.dumps(payload, separators=(",", ":"))
    payload_base64 = base64.b64encode(payload_str.encode()).decode()
    checksum = _build_phonepe_checksum(payload_base64, endpoint)
    headers = {
        "Content-Type": "application/json",
        "X-VERIFY": checksum,
        "X-MERCHANT-ID": PHONEPE_MERCHANT_ID,
    }
    url = PHONEPE_BASE_URL + endpoint
    res = requests.post(url, json={"request": payload_base64}, headers=headers, timeout=30)
    try:
        data = res.json()
    except Exception:
        data = {"success": False, "code": "UNKNOWN", "message": res.text}
    data["merchantTransactionId"] = merchant_transaction_id
    return data


def verify_payment(merchant_transaction_id: str):
    endpoint = f"/pg/v1/status/{PHONEPE_MERCHANT_ID}/{merchant_transaction_id}"
    checksum = _build_phonepe_checksum("", endpoint)
    headers = {"Content-Type": "application/json", "X-VERIFY": checksum, "X-MERCHANT-ID": PHONEPE_MERCHANT_ID}
    url = PHONEPE_BASE_URL + endpoint
    res = requests.get(url, headers=headers, timeout=30)
    try:
        data = res.json()
    except Exception:
        data = {"success": False, "code": "UNKNOWN", "message": res.text}
    return data


def handle_payment_callback(employer_id: str, merchant_transaction_id: str):
    status_data = verify_payment(merchant_transaction_id)
    # PhonePe success code typically SUCCESS
    success = status_data.get("success") and status_data.get("code") == "SUCCESS"
    if success:
        # Determine plan by looking up a pending order; for simplicity assume plan_id stored earlier
        order = db.subscription_orders.find_one({"merchant_transaction_id": merchant_transaction_id})
        if order:
            sub = create_or_update_subscription(employer_id, order["plan_id"], merchant_transaction_id, company_id=order.get("company_id"))
            db.subscription_orders.update_one(
                {"merchant_transaction_id": merchant_transaction_id},
                {"$set": {"status": "paid", "updated_at": get_ist_now()}},
            )
            return {"status": "paid", "subscription": sub}
    return {"status": "failed", "details": status_data}


def create_pending_order(employer_id: str, plan_id: str, merchant_transaction_id: str, company_id: str | None = None):
    order = {
        "merchant_transaction_id": merchant_transaction_id,
        "employer_id": employer_id,
        "plan_id": plan_id,
        "status": "pending",
        "created_at": get_ist_now(),
    }
    if plan_id == "enterprise" and company_id:
        order["company_id"] = company_id
    db.subscription_orders.insert_one(order)
