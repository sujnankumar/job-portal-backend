import uuid
import hashlib
import base64
import json
import logging
import requests
from datetime import datetime, timedelta
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from app.db import db
from app.config.settings import (
    PHONEPE_MERCHANT_ID,
    PHONEPE_SALT_KEY,
    PHONEPE_SALT_INDEX,
    PHONEPE_BASE_URL,
    PHONEPE_REDIRECT_BASE,
)
from app.utils.timezone_utils import get_ist_now

logger = logging.getLogger(__name__)


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


def ensure_subscription_indexes():
    """Create indexes needed for performance and uniqueness.

    Safe to call multiple times; MongoDB will no-op if index exists. Called at app startup instead of import time
    to avoid slowing cold starts in serverless/container environments.
    """
    try:
        db.jobs.create_index([("employer_id", 1), ("posted_at", 1)])
    except Exception as e:  # pragma: no cover
        logger.debug("jobs index create skipped: %s", e)
    try:
        db.subscriptions.create_index([("employer_id", 1), ("status", 1), ("expires_at", 1)])
        db.subscriptions.create_index([("company_id", 1), ("status", 1), ("expires_at", 1)])
        db.subscriptions.create_index([("subscription_id", 1)], unique=True)
        db.subscriptions.create_index([("plan_id", 1)])
    except Exception as e:  # pragma: no cover
        logger.debug("subscriptions index create skipped: %s", e)
    try:
        db.subscription_orders.create_index([("merchant_transaction_id", 1)], unique=True)
        db.subscription_orders.create_index([("employer_id", 1), ("status", 1)])
        db.subscription_orders.create_index([("plan_id", 1)])
        # TTL for pending orders (expire after 1 day)
        db.subscription_orders.create_index(
            [("created_at", 1)],
            expireAfterSeconds=86400,
            partialFilterExpression={"status": "pending"},
        )
    except Exception as e:  # pragma: no cover
        logger.debug("subscription_orders index create skipped: %s", e)
    try:
        db.phonepe_callbacks.create_index([("merchant_transaction_id", 1)])
        db.phonepe_callbacks.create_index([("received_at", 1)])
    except Exception as e:  # pragma: no cover
        logger.debug("phonepe_callbacks index create skipped: %s", e)


# Backwards compatibility name (if other modules imported it before refactor)
_ensure_indexes = ensure_subscription_indexes


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


def _resolve_plan(sub: dict | None):
    """Return the effective plan dict for a subscription.

    Uses stored snapshot (to honor legacy terms) but falls back to current PLANS if snapshot missing.
    """
    if not sub:
        return PLANS["free"], "free"
    snapshot = sub.get("plan_snapshot")
    plan_id = sub.get("plan_id", "free")
    if snapshot and isinstance(snapshot, dict):
        return snapshot, plan_id
    return PLANS.get(plan_id, PLANS["free"]), plan_id


def get_effective_subscription(employer_id: str):
    """Fetch the effective active subscription (personal first, else company enterprise) with a single
    subscription collection query (after one user query).
    """
    now = get_ist_now()
    user = db.users.find_one({"user_id": employer_id}, {"company_id": 1, "_id": 0})
    company_id = user.get("company_id") if user else None
    # Query for both possible active subs in one round trip
    subs_cursor = db.subscriptions.find(
        {
            "status": "active",
            "expires_at": {"$gt": now},
            "$or": [
                {"employer_id": employer_id},
                {"company_id": company_id, "plan_id": "enterprise"} if company_id else {"employer_id": employer_id},
            ],
        }
    )
    personal = None
    enterprise = None
    for s in subs_cursor:
        if s.get("employer_id") == employer_id and s.get("scope") in ("employer", None):
            personal = s
        if s.get("plan_id") == "enterprise":
            enterprise = s
    # Preference: personal over enterprise (except maybe if we want enterprise override; current logic prefers personal)
    chosen = personal or enterprise
    if chosen:
        chosen.pop("_id", None)
    return chosen


def can_post_job(employer_id: str):
    """Determine if employer can post a job.

    Returns (allowed: bool, plan_id: str, message: str, subscription_id: str | None)
    """
    sub = get_effective_subscription(employer_id)
    now = get_ist_now()
    plan, plan_id = _resolve_plan(sub)

    if sub:
        # Reset counters for limited plans at boundary
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
        # Unlimited plans
        if plan_id in ("enterprise", "premium"):
            return True, plan_id, "OK", sub["subscription_id"]

    yearly_limit = plan.get("yearly_post_limit")
    monthly_limit = plan.get("monthly_post_limit")
    used_year = sub.get("posts_used_year", 0) if sub else _count_jobs(employer_id, year=now.year)
    used_month = sub.get("posts_used_month", 0) if sub else _count_jobs(employer_id, year=now.year, month=now.month)
    if yearly_limit is not None and used_year >= yearly_limit:
        return False, plan_id, "Yearly post limit reached", sub["subscription_id"] if sub else None
    if monthly_limit is not None and used_month >= monthly_limit:
        return False, plan_id, "Monthly post limit reached", sub["subscription_id"] if sub else None
    return True, plan_id, "OK", sub["subscription_id"] if sub else None


def ensure_free_subscription(employer_id: str):
    """Ensure a free subscription document exists for this employer to track counters.

    Returns the active subscription doc (free) without the _id field.
    """
    now = get_ist_now()
    sub = get_active_subscription(employer_id)
    if sub:
        return sub
    # Create a free plan to track counters atomically for non-paying employers
    return create_or_update_subscription(employer_id, "free", "FREE-AUTO", duration_days=365)


def attempt_post_job(employer_id: str):
    """Atomically check posting limits and increment counters by 1."""
    return attempt_bulk_post_jobs(employer_id, 1)


def attempt_bulk_post_jobs(employer_id: str, count: int):
    """Atomically attempt to post multiple jobs at once.

    Returns (allowed: bool, plan_id: str, message: str, subscription_id: str | None)
    """
    if count <= 0:
        return False, "free", "Count must be positive", None
    now = get_ist_now()
    sub = get_effective_subscription(employer_id)
    if not sub:
        sub = ensure_free_subscription(employer_id)
    plan, plan_id = _resolve_plan(sub)
    monthly_limit = plan.get("monthly_post_limit")
    yearly_limit = plan.get("yearly_post_limit")

    # Unlimited plans OR missing limits (None) => increment without gating
    if plan_id in ("premium", "enterprise") or monthly_limit is None or yearly_limit is None:
        updated = _subscription_collection().find_one_and_update(
            {
                "subscription_id": sub["subscription_id"],
                "status": "active",
                "expires_at": {"$gt": now},
            },
            {
                "$inc": {"posts_used_year": count, "posts_used_month": count},
                "$set": {"month": now.month, "year": now.year},
            },
            return_document=ReturnDocument.AFTER,
        )
        if not updated:
            return False, plan_id, "Subscription inactive or expired", sub["subscription_id"]
        return True, plan_id, "OK", sub["subscription_id"]

    # Reset counters if boundary changed
    reset_updates = {}
    if sub.get("month") != now.month:
        reset_updates["posts_used_month"] = 0
        reset_updates["month"] = now.month
    if sub.get("year") != now.year:
        reset_updates["posts_used_year"] = 0
        reset_updates["year"] = now.year
    if reset_updates:
        _subscription_collection().update_one({"subscription_id": sub["subscription_id"]}, {"$set": reset_updates})
        sub.update(reset_updates)

    # Build gating filter: current usage + count <= limit
    filter_query = {
        "subscription_id": sub["subscription_id"],
        "status": "active",
        "expires_at": {"$gt": now},
        "month": now.month,
        "year": now.year,
    }
    if monthly_limit is not None:
        filter_query["posts_used_month"] = {"$lte": (monthly_limit - count)}
    if yearly_limit is not None:
        filter_query["posts_used_year"] = {"$lte": (yearly_limit - count)}

    updated = _subscription_collection().find_one_and_update(
        filter_query,
        {"$inc": {"posts_used_year": count, "posts_used_month": count}},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        # Determine reason
        current = _subscription_collection().find_one({"subscription_id": sub["subscription_id"]}) or {}
        used_m = current.get("posts_used_month", 0)
        used_y = current.get("posts_used_year", 0)
        if yearly_limit is not None and used_y >= yearly_limit:
            return False, plan_id, "Yearly post limit reached", sub["subscription_id"]
        if monthly_limit is not None and used_m >= monthly_limit:
            return False, plan_id, "Monthly post limit reached", sub["subscription_id"]
        if yearly_limit is not None and used_y + count > yearly_limit:
            return False, plan_id, "Bulk exceeds yearly limit", sub["subscription_id"]
        if monthly_limit is not None and used_m + count > monthly_limit:
            return False, plan_id, "Bulk exceeds monthly limit", sub["subscription_id"]
        return False, plan_id, "Post limit reached", sub["subscription_id"]
    return True, plan_id, "OK", sub["subscription_id"]


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


def handle_payment_callback(employer_id: str, merchant_transaction_id: str, verified: bool = False, pre_status: dict | None = None):
    """Finalize subscription on callback. If verified is True, skip calling verify_payment.

    pre_status can be provided for logging or future use; currently ignored if verified.
    """
    status_data = pre_status or {}
    if not verified:
        status_data = verify_payment(merchant_transaction_id)
    # PhonePe success code typically SUCCESS
    success = (status_data.get("success") and status_data.get("code") == "SUCCESS") if not verified else True
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
    try:
        db.subscription_orders.insert_one(order)
    except DuplicateKeyError:
        # Idempotent: if the order exists, ensure it is still pending and update timestamp
        db.subscription_orders.update_one(
            {"merchant_transaction_id": merchant_transaction_id},
            {"$set": {"employer_id": employer_id, "plan_id": plan_id, "status": "pending", "updated_at": get_ist_now()}},
            upsert=True,
        )
