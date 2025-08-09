from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from datetime import datetime
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
    if current_user["user_type"] != "job_seeker":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only job seekers can write reviews")

    existing_review = db.company_reviews.find_one({
        "user_id": current_user["user_id"],
        "company_id": review.company_id
    })

    if existing_review:
        raise HTTPException(status_code=400, detail="You have already reviewed this company")

    review_doc = {
        "user_id": current_user["user_id"],
        "company_id": review.company_id,
        "rating": review.rating,
        "review_text": review.review_text,
        "created_at": datetime.utcnow()
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
                "updated_at": datetime.utcnow()
            }
        }
    )

    if update_result.modified_count == 0:
        return {"message": "No changes made to the review"}

    return {"message": "Review updated successfully"}
