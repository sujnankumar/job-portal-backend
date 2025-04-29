from passlib.hash import bcrypt
from app.db import db
from app.utils.jwt_handler import create_access_token
from datetime import datetime, timezone
import uuid

def hash_password(password: str):
    return bcrypt.hash(password)

def verify_password(plain_password, hashed_password):
    return bcrypt.verify(plain_password, hashed_password)

def add_company(company_data: dict):
    company_data["company_id"] = str(uuid.uuid4())
    company_data["created_at"] = datetime.now(timezone.utc).isoformat()
    db.companies.insert_one(company_data)
    company_data.pop("_id", None)  # Remove MongoDB's internal _id field
    return {"msg": "Company added", "data": company_data}

def get_company_by_id(company_id: str):
    company = db.companies.find_one({"company_id": company_id})
    if company:
        company.pop("_id", None)  # Remove MongoDB's internal _id field
        return company

def get_all_companies():
    companies = list(db.companies.find({}, {"_id": 0, "company_id": 1, "company_name": 1}))
    unique_companies = {company["company_id"]: company for company in companies}.values()
    return list(unique_companies)
