from fastapi import APIRouter, Request, HTTPException, Header
from app.functions import job_functions
from app.utils.jwt_handler import verify_token

router = APIRouter()

@router.post("/post_job")
async def post_job(request: Request, authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if payload.get("user_type") != "employer":
        raise HTTPException(status_code=403, detail="Only employers can post jobs")
    data = await request.json()
    data["employer_id"] = payload.get("user_id")
    # Set job visibility, default to public if not provided
    data["visibility"] = data.get("visibility", "public")
    return job_functions.create_job(data)

@router.get("/list")
def list_all_jobs():
    return job_functions.list_jobs()

@router.get("/search/{title}")
def search_job(title: str):
    job = job_functions.get_job_by_title(title)
    if job:
        return job
    return {"msg": "Job not found"}

@router.delete("/remove_job/{job_id}")
def remove_job(job_id: str, authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if payload.get("user_type") != "employer":
        raise HTTPException(status_code=403, detail="Only employers can remove jobs")
    return job_functions.remove_job(job_id, payload.get("user_id"))

@router.patch("/update_visibility/{job_id}")
def update_job_visibility(job_id: str, visibility: str, authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if payload.get("user_type") != "employer":
        raise HTTPException(status_code=403, detail="Only employers can update job visibility")
    return job_functions.update_job_visibility(job_id, visibility, payload.get("user_id"))
