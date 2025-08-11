from fastapi import APIRouter, Request, HTTPException, Depends
from app.db import db
from app.routes.user import get_current_user

router = APIRouter()

@router.post("/follow/{employer_id}")
async def follow_employer(employer_id: str, request: Request, user=Depends(get_current_user)):
    user_id = user.get("user_id")
    user_type = user.get("user_type")

    if user_type != "job_seeker":
        raise HTTPException(status_code=403, detail="Only job seekers can follow employers")
    
    # Check if employer exists
    employer = db.users.find_one({"user_id": employer_id, "user_type": "employer"})
    if not employer:
        raise HTTPException(status_code=404, detail="Employer not found")

    # Get company name from companies collection
    company = db.companies.find_one({"employer_id": employer_id})
    company_name = company.get("company_name") if company else "the company"

    # Add employer to following list
    db.users.update_one(
        {"user_id": user_id},
        {"$addToSet": {"following": employer_id}}
    )

    return {"detail": f"Now following {company_name}"}

@router.delete("/follow/{employer_id}")
async def unfollow_employer(employer_id: str, request: Request, user=Depends(get_current_user)):
    user_id = user.get("user_id")
    user_type = user.get("user_type")

    if user_type != "job_seeker":
        raise HTTPException(status_code=403, detail="Only job seekers can unfollow employers")

    db.users.update_one(
        {"user_id": user_id},
        {"$pull": {"following": employer_id}}
    )

    return {"detail": f"Unfollowed employer {employer_id}"}

@router.get("/following")
async def get_following(request: Request, user=Depends(get_current_user)):
    user_id = user.get("user_id")
    user_type = user.get("user_type")

    if user_type != "job_seeker":
        raise HTTPException(status_code=403, detail="Only job seekers have a following list")

    user_doc = db.users.find_one({"user_id": user_id}, {"following": 1, "_id": 0})
    following = user_doc.get("following", []) if user_doc else []
    return {"following": following}

@router.get("/followers")
async def get_followers(user=Depends(get_current_user)):
    user_id = user.get("user_id")
    user_type = user.get("user_type")

    if user_type != "employer":
        raise HTTPException(status_code=403, detail="Only companies can view their followers")

    followers_cursor = db.users.find(
        {"user_type": "job_seeker", "following": user_id},
        {"_id": 0, "user_id": 1, "first_name": 1, "last_name": 1, "email": 1}
    )
    followers = list(followers_cursor)

    return {"followers": followers}
