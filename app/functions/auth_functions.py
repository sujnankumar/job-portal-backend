from passlib.hash import bcrypt
from app.db import db
from app.utils.jwt_handler import create_access_token
from datetime import datetime, timezone
import uuid

def hash_password(password: str):
    return bcrypt.hash(password)

def verify_password(plain_password, hashed_password):
    return bcrypt.verify(plain_password, hashed_password)

def register_user(user_data: dict):
    user_data["password"] = hash_password(user_data["password"])
    user_data["register_time"] = datetime.now(timezone.utc)
    user_data["user_id"] = str(uuid.uuid4())
    db.users.insert_one(user_data)
    return {"msg": "User registered"}

def is_email_registered(email: str):
    return db.users.find_one({"email": email}) is not None

def login_user(email: str, password: str):
    user = db.users.find_one({"email": email})
    if not user or not verify_password(password, user["password"]):
        return None
    token = create_access_token({
        "email": user["email"],
        "user_id": user["user_id"],
        "user_type": user["user_type"],
        "first_name": user["first_name"],
        "last_name": user["last_name"]
    })
    return {"access_token": token, "token_type": "bearer"}

def update_user_profile_by_email(email: str, update_data: dict):
    result = db.users.update_one({"email": email}, {"$set": update_data})
    if result.modified_count == 1:
        return {"msg": "Profile updated"}
    return None
