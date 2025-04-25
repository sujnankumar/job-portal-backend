from fastapi import FastAPI
from app.routes import auth, user, job,application, get_application, save_job, recommendation_routes, get_my_applications

app = FastAPI()

app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(user.router, prefix="/api/user", tags=["User"])
app.include_router(job.router, prefix="/api/job", tags=["Job"])
app.include_router(application.router, prefix="/api/application", tags=["Application"])
app.include_router(get_application.router, prefix="/jobs", tags=["Applications"])
app.include_router(save_job.router, prefix="/jobs", tags=["Save Jobs"])
app.include_router(recommendation_routes.router, prefix="/api", tags=["Recommendations"])
app.include_router(get_my_applications.router, prefix="/api", tags=["Get My Applications"]) 

@app.get("/")
def root():
    return {"message": "Job Portal Backend Running"}
