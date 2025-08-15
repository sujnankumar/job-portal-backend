from fastapi import APIRouter, Request, HTTPException, Depends
from app.db import db
from app.routes.user import get_current_user

router = APIRouter()

@router.post("/follow/{company_id}")
async def follow_company(company_id: str, request: Request, user=Depends(get_current_user)):
    user_id = user.get("user_id")
    user_type = user.get("user_type")

    if user_type != "job_seeker":
        raise HTTPException(status_code=403, detail="Only job seekers can follow companies")

    # Check if company exists
    company = db.companies.find_one({"company_id": company_id})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    company_name = company.get("company_name", "the company")

    # Add company to following list
    db.users.update_one(
        {"user_id": user_id},
        {"$addToSet": {"following": company_id}}
    )

    return {"detail": f"Now following {company_name}"}

@router.delete("/follow/{company_id}")
async def unfollow_company(company_id: str, request: Request, user=Depends(get_current_user)):
    user_id = user.get("user_id")
    user_type = user.get("user_type")

    if user_type != "job_seeker":
        raise HTTPException(status_code=403, detail="Only job seekers can unfollow companies")
    company = db.companies.find_one({"company_id": company_id})
    company_name = company.get("company_name", "the company")
    db.users.update_one(
        {"user_id": user_id},
        {"$pull": {"following": company_id}}
    )

    return {"detail": f"Unfollowed company {company_name}"}

@router.get("/following")
async def get_following(request: Request, user=Depends(get_current_user)):
    user_id = user.get("user_id")
    user_type = user.get("user_type")

    if user_type != "job_seeker":
        raise HTTPException(status_code=403, detail="Only job seekers have a following list")

    user_doc = db.users.find_one({"user_id": user_id}, {"following": 1, "_id": 0})
    following = user_doc.get("following", []) if user_doc else []
    return {"following": following}

@router.get("/followers/{company_id}")
async def get_company_followers(company_id: str, user=Depends(get_current_user)):
    user_type = user.get("user_type")

    # Only employers can view followers of their company
    if user_type != "employer":
        raise HTTPException(status_code=403, detail="Only companies can view their followers")

    # Check if company exists
    company = db.companies.find_one({"company_id": company_id})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    followers_cursor = db.users.find(
        {"user_type": "job_seeker", "following": company_id},
        {"_id": 0, "user_id": 1, "first_name": 1, "last_name": 1, "email": 1}
    )
    followers = list(followers_cursor)

    return {"followers": followers}
