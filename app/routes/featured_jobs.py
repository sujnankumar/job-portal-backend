# app/routes/featured_jobs.py

from fastapi import APIRouter
from app.db import db

router = APIRouter()

@router.get("/featured-jobs")
async def get_featured_jobs():
    try:
        # Step 1: Aggregate the top jobs based on number of applications
        application_pipeline = [
            {
                "$group": {
                    "_id": "$job_id",
                    "application_count": {"$sum": 1}
                }
            },
            {
                "$sort": {"application_count": -1}
            },
            {
                "$limit": 10  # Top 10 jobs with most applications
            }
        ]
        popular_jobs = list(db.applications.aggregate(application_pipeline))
        popular_job_ids = [job["_id"] for job in popular_jobs]

        if not popular_job_ids:
            return {"featured_jobs": []}

        # Step 2: Fetch job details from jobs collection
        jobs = list(db.jobs.find({
            "job_id": {"$in": popular_job_ids},
            "status": "active"  # Only active jobs
        }, {"_id": 0}))  # Exclude Mongo _id field

        # Optional: Sort the fetched jobs in the same order as application count
        jobs_sorted = sorted(jobs, key=lambda job: popular_job_ids.index(job["job_id"]))

        return {"featured_jobs": jobs_sorted}

    except Exception as e:
        return {"error": str(e)}
