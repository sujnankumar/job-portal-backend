from fastapi import APIRouter, Depends, HTTPException, Request
from app.utils.jwt_handler import verify_token
from app.db import db

router = APIRouter()

def get_current_user(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    user_data = verify_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or missing token")
    return user_data

@router.get("/recommendations")
async def get_job_recommendations(user=Depends(get_current_user)):
    user_doc = db.users.find_one({"user_id": user["user_id"]})
    if not user_doc or "skills" not in user_doc:
        raise HTTPException(status_code=404, detail="User profile incomplete")

    skills = user_doc["skills"]

    # Fetch jobs that match at least one skill
    matching_jobs = list(db.jobs.find({
        "required_skills": {"$in": skills}
    }, {"_id": 0}))

    # Define similar job categories with more extensive mappings
    similar_categories_map = {
        "Software Development": ["Web Development", "Mobile Development", "DevOps", "Backend Development", "Frontend Development", "Full Stack Development"],
        "Data Science": ["Machine Learning", "AI", "Data Engineering", "Big Data", "Data Analytics", "Business Intelligence"],
        "Marketing": ["Content Creation", "SEO", "Social Media", "Digital Marketing", "Brand Management", "Market Research"],
        "Design": ["Graphic Design", "UI/UX Design", "Product Design", "Interaction Design", "Visual Design"],
        "Finance": ["Accounting", "Investment Banking", "Financial Analysis", "Risk Management", "Auditing"],
        "Healthcare": ["Nursing", "Medical Research", "Pharmacy", "Public Health", "Healthcare Administration"],
    }

    user_categories = user_doc.get("preferred_categories", [])
    expanded_categories = set(user_categories)
    for category in user_categories:
        expanded_categories.update(similar_categories_map.get(category, []))

    # Fetch jobs that are similar based on expanded categories
    similar_jobs = list(db.jobs.find({
        "category": {"$in": list(expanded_categories)}
    }, {"_id": 0}))

    # Combine matching and similar jobs
    combined_jobs = {job["job_id"]: job for job in matching_jobs + similar_jobs}.values()

    # Fetch applied jobs to exclude them
    applied_jobs = db.applications.find({
        "user_id": user["user_id"]
    })
    applied_job_ids = {app["job_id"] for app in applied_jobs}

    # Filter out already applied jobs
    recommended = [
        job for job in combined_jobs if job["job_id"] not in applied_job_ids
    ]

    # Scoring function to rank jobs
    def score(job):
        skill_match_score = len(set(job.get("required_skills", [])) & set(skills))
        category_match_score = 1 if job.get("category") in user_categories else 0
        similar_category_score = 1 if job.get("category") in expanded_categories else 0
        return skill_match_score * 2 + category_match_score + similar_category_score

    # Sort recommendations by score
    recommended.sort(key=score, reverse=True)

    # Return top 5 recommendations
    return {"recommended_jobs": recommended[:5]}
