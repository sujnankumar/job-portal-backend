from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from datetime import datetime
from app.utils.timezone_utils import get_ist_now
from app.routes.user import get_current_user
from app.db import db

router = APIRouter()

class RatingInput(BaseModel):
    company_id: str
    rating: int = Field(..., ge=1, le=5)

class RatingEditInput(BaseModel):
    company_id: str
    rating: int = Field(..., ge=1, le=5)

@router.post("/rate", tags=["ratings"])
async def submit_rating(rating: RatingInput, current_user: dict = Depends(get_current_user)):
    if current_user["user_type"] != "job_seeker":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only job seekers can rate companies"
        )

    existing_review = db.company_reviews.find_one({
        "user_id": current_user["user_id"],
        "company_id": rating.company_id
    })

    if existing_review:
        raise HTTPException(status_code=400, detail="You have already submitted a review or rating")

    rating_doc = {
        "user_id": current_user["user_id"],
        "company_id": rating.company_id,
        "rating": rating.rating,
        "review_text": "",  # No review text since this is just a rating
    "created_at": get_ist_now(),
        "editcount": 0
    }

    db.company_reviews.insert_one(rating_doc)

    return {"message": f"Rating of {rating.rating} submitted successfully"}


@router.get("/average-rating/{company_id}", tags=["ratings"])
async def get_average_rating(company_id: str):
    ratings = db.company_reviews.find({"company_id": company_id})
    
    ratings_list = [r["rating"] for r in ratings if "rating" in r]

    if not ratings_list:
        return {"company_id": company_id, "average_rating": None, "total_ratings": 0}

    average = sum(ratings_list) / len(ratings_list)
    return {
        "company_id": company_id,
        "average_rating": round(average, 2),
        "total_ratings": len(ratings_list)
    }


@router.post("/edit", tags=["ratings"])
async def edit_rating(rating: RatingEditInput, current_user: dict = Depends(get_current_user)):
    if current_user["user_type"] != "job_seeker":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only job seekers can edit ratings")

    existing = db.company_reviews.find_one({
        "user_id": current_user["user_id"],
        "company_id": rating.company_id
    })

    if not existing:
        raise HTTPException(status_code=404, detail="Rating/Review not found")

    # Increment editcount (create if missing) only on edit
    new_editcount = existing.get("editcount", 0) + 1
    db.company_reviews.update_one(
        {"_id": existing["_id"]},
        {"$set": {"rating": rating.rating, "updated_at": get_ist_now(), "editcount": new_editcount}}
    )
    return {"message": "Rating updated", "editcount": new_editcount}
