from app.db import db
from bson import ObjectId

def delete_application(application_id: str, user_id: str):

    if not db.applications.find_one({"_id": ObjectId(application_id), "user_id": user_id}):
        return {"message": "Application not found or you are not authorized to delete it", "status": "error"}
    
    result = db.applications.delete_one({"_id": ObjectId(application_id)})
    if result.deleted_count == 1:
        return {"message": "Application deleted", "status": "success"}
    return {"message": "Application not found", "status": "error"}