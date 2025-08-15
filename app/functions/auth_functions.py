from passlib.hash import bcrypt
from app.db import db
from app.utils.jwt_handler import create_access_token
from datetime import datetime, timezone, timedelta
import uuid
import hashlib
import secrets
from app.utils.timezone_utils import get_ist_now
from app.utils.email_utils import send_email

PASSWORD_RESET_EXPIRY_MINUTES = 15
PASSWORD_RESET_MAX_ATTEMPTS = 5
OTP_LENGTH = 6

def hash_password(password: str):
    return bcrypt.hash(password)

def verify_password(plain_password, hashed_password):
    return bcrypt.verify(plain_password, hashed_password)

def register_user(user_data: dict):
    user_data["password"] = hash_password(user_data["password"])
    user_data["register_time"] = get_ist_now()
    user_data["user_id"] = str(uuid.uuid4())
    user_data["onboarding"] = {
        "isComplete": False,
        "startedAt": get_ist_now().isoformat(),
        "formData": {},
        "validationStatus": {},
        "validationMessages": {},
        "lastStep": 0,
        "lastUpdated": get_ist_now().isoformat()
    }
    db.users.insert_one(user_data)
    user_data.pop("_id", None)
    user_data.pop("password", None)
    return {"msg": "User registered", "data": user_data}

def is_email_registered(email: str):
    return db.users.find_one({"email": email}) is not None

def login_user(email: str, password: str, remember_me: bool = False):
    user = db.users.find_one({"email": email})
    if not user or not verify_password(password, user["password"]):
        return None
    token = create_access_token({
        "email": user["email"],
        "user_id": user["user_id"],
        "user_type": user["user_type"],
        "first_name": user["first_name"],
        "last_name": user["last_name"]
    }, remember_me=remember_me)
    onboarding = user["onboarding"]
    return {"access_token": token, "token_type": "bearer", "onboarding": onboarding}

def update_user_profile_by_email(email: str, update_data: dict):
    result = db.users.update_one({"email": email}, {"$set": update_data})
    if result.modified_count == 1:
        return {"msg": "Profile updated"}
    return None
    
def onboard_user(user_data: dict, onboarding_data: dict, company_data: dict):
    user = db.users.find_one({"email": user_data["email"]})
    if not user:
        return {"msg": "User not found"}
    
    updated_onboarding = {
        "isComplete": True,
        "formData": onboarding_data,
        "validationStatus": {},
        "validationMessages": {},
        "lastStep": 0,
        "lastUpdated": get_ist_now().isoformat()
    }
    
    update_fields = {
        "onboarding": updated_onboarding,
        "company_id": company_data.get("company_id")
    }
    
    db.users.update_one({"email": user_data["email"]}, {"$set": update_fields})
    user["onboarding"] = updated_onboarding
    user["company_id"] = company_data["company_id"]
    user["_id"] = str(user["_id"])  # Convert ObjectId to string
    return {"msg": "Onboarding complete", "user": user}

def get_user_by_id(user_id: str):
    user = db.users.find_one({"user_id": user_id})
    if not user:
        return None
    user["_id"] = str(user["_id"])  # Convert ObjectId to string
    return user


def _password_reset_collection():
    return db.password_reset_tokens


def _ensure_password_reset_indexes():  # idempotent
    try:
        _password_reset_collection().create_index(
            [
                ("email", 1),
                ("expires_at", 1),
            ]
        )
        # TTL index (expire whole doc after expiry) – cannot depend on conditional, so we store expires_at and use expireAfterSeconds
        _password_reset_collection().create_index("expires_at", expireAfterSeconds=0)
        _password_reset_collection().create_index("reset_token", unique=True, sparse=True)
    except Exception:
        pass


_ensure_password_reset_indexes()


def _hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()


def _generate_otp() -> str:
    return ''.join(secrets.choice('0123456789') for _ in range(OTP_LENGTH))


def initiate_password_reset(email: str):
    user = db.users.find_one({"email": email})
    # Return False if email not present so API can surface message
    if not user:
        return False
    otp = _generate_otp()
    # Store expiry as naive (strip tz) to avoid Mongo timezone ambiguity
    expires_at = (get_ist_now() + timedelta(minutes=PASSWORD_RESET_EXPIRY_MINUTES)).replace(tzinfo=None)
    _password_reset_collection().delete_many({"email": email})  # invalidate previous
    _password_reset_collection().insert_one({
        "email": email,
        "otp_hash": _hash_otp(otp),
        "expires_at": expires_at,
        "attempts": 0,
        "verified": False,
        "created_at": get_ist_now().replace(tzinfo=None),
    })
    try:
        subject = "Your Password Reset OTP"
        body = f"Your OTP is {otp}. It expires in {PASSWORD_RESET_EXPIRY_MINUTES} minutes."
        html_body = f"<p>Your OTP is <strong>{otp}</strong>.</p><p>It expires in {PASSWORD_RESET_EXPIRY_MINUTES} minutes.</p>"
        send_email(email, subject, body, html_body)
    except Exception:
        # swallow email errors to prevent enumeration; token still stored
        pass
    return True


def verify_reset_otp(email: str, otp: str):
    rec = _password_reset_collection().find_one({"email": email})
    if not rec:
        return None
    if rec.get("verified"):
        return rec.get("reset_token")
    if rec.get("attempts", 0) >= PASSWORD_RESET_MAX_ATTEMPTS:
        return None
    now = get_ist_now()
    exp = rec.get("expires_at")
    if exp is None:
        return None
    # Normalize comparison: if stored naive, compare against naive now
    if getattr(exp, "tzinfo", None) is None:
        if now.replace(tzinfo=None) > exp:
            return None
    else:  # stored aware
        if now > exp:
            return None
    otp_hash = _hash_otp(otp)
    if otp_hash != rec.get("otp_hash"):
        _password_reset_collection().update_one({"_id": rec["_id"]}, {"$inc": {"attempts": 1}})
        return None
    reset_token = secrets.token_urlsafe(32)
    _password_reset_collection().update_one({"_id": rec["_id"]}, {"$set": {"verified": True, "reset_token": reset_token, "verified_at": get_ist_now().replace(tzinfo=None)}})
    return reset_token


def reset_password_with_token(email: str, reset_token: str, new_password: str):
    rec = _password_reset_collection().find_one({"email": email, "reset_token": reset_token, "verified": True})
    if not rec:
        return False
    now = get_ist_now()
    exp = rec.get("expires_at")
    if exp is None:
        return False
    if getattr(exp, "tzinfo", None) is None:
        if now.replace(tzinfo=None) > exp:
            return False
    else:
        if now > exp:
            return False
    # update user password
    user = db.users.find_one({"email": email})
    if not user:
        return False
    hashed = hash_password(new_password)
    db.users.update_one({"email": email}, {"$set": {"password": hashed, "password_updated_at": get_ist_now().replace(tzinfo=None)}})
    _password_reset_collection().update_one({"_id": rec["_id"]}, {"$set": {"used": True, "used_at": get_ist_now().replace(tzinfo=None)}})
    return True