from fastapi import APIRouter, HTTPException, Request, Depends, Header
from app.functions import interview_functions
from app.utils.jwt_handler import verify_token
from app.db import db
from bson import ObjectId
from app.routes.notification import notification_manager, serialize_notification

router = APIRouter()

def get_current_user_id_and_type(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload["user_id"], payload["user_type"]

@router.post("/schedule")
async def schedule_interview(request: Request, authorization: str = Header(None)):
    user_id, user_type = get_current_user_id_and_type(authorization)
    if user_type != "employer":
        raise HTTPException(status_code=403, detail="Only HRs can schedule interviews")
    data = await request.json()
    required = ["candidate_id", "job_id", "date", "startTime", "duration", "interviewType"]
    for field in required:
        if not data.get(field):
            raise HTTPException(status_code=400, detail=f"{field} is required")
    # Combine date and startTime into scheduled_time (ISO format)
    from datetime import datetime
    try:
        scheduled_time = datetime.strptime(f"{data['date']} {data['startTime']}", "%Y-%m-%d %H:%M").isoformat()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid date or startTime format")
    # Only require zoom_link if interviewType is video
    zoom_link = data.get("zoomLink") if data.get("interviewType") == "video" else None
    if data.get("interviewType") == "video" and not zoom_link:
        raise HTTPException(status_code=400, detail="zoomLink is required for video interviews")
    details = {
        "interviewType": data.get("interviewType"),
        "interviewers": data.get("interviewers"),
        "notes": data.get("notes"),
        "duration": data.get("duration")
    }
    result = interview_functions.schedule_interview(
        hr_id=user_id,
        candidate_id=data["candidate_id"],
        job_id=data["job_id"],
        scheduled_time=scheduled_time,
        zoom_link=zoom_link,
        details=details
    )
    # Update application status to 'interview'
    db.applications.update_one(
        {"job_id": data["job_id"], "user_id": data["candidate_id"]},
        {"$set": {"status": "interview", "interview_date": data["date"], "interview_time": data["startTime"]}}
    )
    return result

@router.get("/my_interviews")
async def my_interviews(authorization: str = Header(None)):
    user_id, _ = get_current_user_id_and_type(authorization)
    return interview_functions.get_interviews_for_user(user_id)

@router.put("/edit/{interview_id}")
async def edit_interview_route(interview_id: str, request: Request, authorization: str = Header(None)):
    user_id, _ = get_current_user_id_and_type(authorization)
    data = await request.json()
    result = interview_functions.edit_interview(interview_id, user_id, data)
    if result.get("error"):
        raise HTTPException(status_code=result["status"], detail=result["error"])
    return result

@router.get("/applicant")
async def get_applicant_interviews(authorization: str = Header(None)):
    user_id, user_type = get_current_user_id_and_type(authorization)
    if user_type != "job_seeker":
        raise HTTPException(status_code=403, detail="Only applicants can view their interviews.")
    interviews = list(db.interviews.find({"candidate_id": user_id}))
    for interview in interviews:
        interview["id"] = str(interview["_id"])
        interview.pop("_id", None)
        # Optionally, add job title
        job = db.jobs.find_one({"job_id": interview["job_id"]})
        interview["job_title"] = job["title"] if job and "title" in job else interview["job_id"]
    return interviews

@router.get("/employer")
async def get_employer_interviews(authorization: str = Header(None)):
    user_id, user_type = get_current_user_id_and_type(authorization)
    if user_type != "employer":
        raise HTTPException(status_code=403, detail="Only employers can view their jobs' interviews.")
    jobs = list(db.jobs.find({"employer_id": user_id}, {"_id": 0}))
    for job in jobs:
        job_id = job["job_id"]
        interviews = list(db.interviews.find({"job_id": job_id}))
        for interview in interviews:
            interview["id"] = str(interview["_id"])
            interview.pop("_id", None)
            # Optionally, add applicant name
            candidate = db.users.find_one({"user_id": interview["candidate_id"]})
            interview["applicant_name"] = f"{candidate.get('first_name', '')} {candidate.get('last_name', '')}" if candidate else interview["candidate_id"]
        job["interviews"] = interviews
    return jobs


@router.get("/details/{job_id}")
async def get_interview_details(job_id: str, authorization: str = Header(None)):
    user_id, user_type = get_current_user_id_and_type(authorization)
    query = {"job_id": job_id}
    if user_type == "job_seeker":
        query["candidate_id"] = user_id
    elif user_type == "employer":
        query["hr_id"] = user_id
    else:
        raise HTTPException(status_code=403, detail="Unauthorized user type")
    interview = db.interviews.find_one(query)
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
    interview["id"] = str(interview["_id"])
    interview.pop("_id", None)
    return interview