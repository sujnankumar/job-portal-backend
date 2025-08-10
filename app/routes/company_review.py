from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from datetime import datetime
from app.utils.timezone_utils import get_ist_now
from typing import Optional
from pydantic import BaseModel, Field
from app.routes.user import get_current_user
from app.db import db

router = APIRouter()

class Review(BaseModel):
    company_id: str
    rating: int = Field(..., ge=1, le=5)
    review_text: Optional[str] = ""

@router.post("/review", tags=["company_review"])
async def write_review(review: Review, current_user: dict = Depends(get_current_user)):
    """Create a new review or, if the user previously only submitted a rating (empty review_text),
    upgrade that rating with the provided review text and potentially updated rating."""
    if current_user["user_type"] != "job_seeker":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only job seekers can write reviews")

    existing_review = db.company_reviews.find_one({
        "user_id": current_user["user_id"],
        "company_id": review.company_id
    })

    if existing_review:
        # If there's already a review text, block duplicate full review
        if existing_review.get("review_text"):
            raise HTTPException(status_code=400, detail="You have already reviewed this company")
        # Otherwise update the existing rating-only document
        db.company_reviews.update_one(
            {"_id": existing_review["_id"]},
            {"$set": {"review_text": review.review_text, "rating": review.rating, "updated_at": get_ist_now()},
             "$inc": {"editcount": 1}}
        )
        return {"message": "Review submitted successfully", "editcount": existing_review.get("editcount",0)+1}

    review_doc = {
        "user_id": current_user["user_id"],
        "company_id": review.company_id,
        "rating": review.rating,
        "review_text": review.review_text,
    "created_at": get_ist_now(),
        "editcount": 0
    }
    db.company_reviews.insert_one(review_doc)
    return {"message": "Review submitted successfully"}


@router.get("/my-reviews", tags=["company_review"])
async def get_my_reviews(current_user: dict = Depends(get_current_user)):
    if current_user["user_type"] != "job_seeker":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only job seekers can view their reviews"
        )

    user_reviews = list(db.company_reviews.find({"user_id": current_user["user_id"]}))
    
    for review in user_reviews:
        review["_id"] = str(review["_id"])
        review["user_id"] = str(review["user_id"])
        review["company_id"] = str(review["company_id"])
        review["created_at"] = review["created_at"].isoformat()

    return {"reviews": user_reviews}


@router.post("/edit-review", tags=["company_review"])
async def edit_review(review: Review, current_user: dict = Depends(get_current_user)):
    if current_user["user_type"] != "job_seeker":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only job seekers can edit reviews"
        )

    existing_review = db.company_reviews.find_one({
        "user_id": current_user["user_id"],
        "company_id": review.company_id
    })

    if not existing_review:
        raise HTTPException(status_code=404, detail="Review not found")

    update_result = db.company_reviews.update_one(
        {
            "user_id": current_user["user_id"],
            "company_id": review.company_id
        },
        {
            "$set": {
                "rating": review.rating,
                "review_text": review.review_text,
                "updated_at": get_ist_now()
            },
            "$inc": {"editcount": 1}
        }
    )

    if update_result.modified_count == 0:
        return {"message": "No changes made to the review"}

    return {"message": "Review updated successfully"}


@router.get("/company/{company_id}", tags=["company_review"])
async def get_company_reviews(company_id: str):
    """Return all reviews (including ratings) for a company with basic user info (name/email).
    Only include entries that have a non-empty review_text for 'reviews' list; ratings-only entries can be sent too if desired."""
    cursor = db.company_reviews.find({"company_id": company_id})
    reviews = []
    for r in cursor:
        user = db.users.find_one({"user_id": r.get("user_id")}) or db.users.find_one({"_id": r.get("user_id")})
        print(r)
        r["_id"] = str(r["_id"])
        # Normalize ids to strings
        r["user_id"] = str(r.get("user_id"))
        r["company_id"] = str(r.get("company_id"))
        if r.get("created_at"):
            try:
                r["created_at"] = r["created_at"].isoformat()
            except Exception:
                pass
        if r.get("updated_at"):
            try:
                r["updated_at"] = r["updated_at"].isoformat()
            except Exception:
                pass
        r["user_name"] = user.get("first_name")+" "+user.get("last_name") if user else "Anonymous"
        reviews.append(r)
    # Separate those with actual textual reviews
    textual_reviews = [rv for rv in reviews if rv.get("review_text")]  # non-empty string
    return {"company_id": company_id, "count": len(textual_reviews), "reviews": textual_reviews}
