from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Header, Response
from app.functions import resume_functions
from app.utils.jwt_handler import verify_token

router = APIRouter()

def get_current_user_id(authorization: str = Header(None)):
    print(authorization)
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload["user_id"]

@router.post("/upload_resume")
async def upload_resume(file: UploadFile = File(...), user_id: str = Depends(get_current_user_id)):
    if file.content_type not in ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/msword"]:
        raise HTTPException(status_code=400, detail="Only PDF or DOCX files are allowed")
    content = await file.read()
    return resume_functions.upload_resume(user_id, content, file.filename, file.content_type)

@router.get("/download_resume")
async def download_resume(user_id: str = Depends(get_current_user_id)):
    result = resume_functions.get_resume(user_id)
    if not result:
        raise HTTPException(status_code=404, detail="Resume not found")
    file, meta = result
    return Response(content=file.read(), media_type=meta["content_type"], headers={"Content-Disposition": f"attachment; filename={meta['filename']}"})

@router.delete("/delete_resume")
async def delete_resume(user_id: str = Depends(get_current_user_id)):
    if resume_functions.delete_resume(user_id):
        return {"msg": "Resume deleted"}
    raise HTTPException(status_code=404, detail="Resume not found")

@router.get("/list_resumes")
async def list_resumes(authorization: str = Header(None)):
    token = authorization.split(" ", 1)[1] if authorization else None
    payload = verify_token(token) if token else None
    if not payload or payload.get("user_type") not in ["employer", "admin"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    return resume_functions.list_resumes()

@router.post("/parse_resume")
async def parse_resume_endpoint(file: UploadFile = File(...), user_id: str = Depends(get_current_user_id)):
    if file.content_type not in ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/msword"]:
        raise HTTPException(status_code=400, detail="Only PDF or DOCX files are allowed")
    content = await file.read()
    parsed = resume_functions.parse_resume(content, file.content_type)
    return parsed

@router.get("/preview_resume")
async def preview_resume(user_id: str = Depends(get_current_user_id)):
    result = resume_functions.get_resume(user_id)
    if not result:
        raise HTTPException(status_code=404, detail="Resume not found")
    file, meta = result
    return Response(content=file.read(), media_type=meta["content_type"], headers={"Content-Disposition": f"inline; filename={meta['filename']}"})

@router.get("/get_profile_resume")
async def get_profile_resume(user_id: str = Depends(get_current_user_id)):
    result = resume_functions.get_resume(user_id)
    if not result:
        raise HTTPException(status_code=404, detail="Resume not found")
    file, meta = result
    file_content = file.read()
    response = Response(
        content=file_content,
        media_type=meta["content_type"],
        headers={
            "Content-Disposition": f"attachment; filename={meta['filename']}"
        }
    )
    # Expose headers for CORS
    response.headers["Access-Control-Expose-Headers"] = "Content-Disposition, Content-Type"
    return response
