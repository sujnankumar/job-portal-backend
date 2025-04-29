from fastapi import FastAPI
from app.routes import auth, user, job,application, get_application, save_job, interview, resume, email,recommendation_routes, get_my_applications, active_application, profile, featured_jobs, employee
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
from app.functions import job_functions
from contextlib import asynccontextmanager


scheduler = BackgroundScheduler()

@asynccontextmanager
async def lifespan(app):
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Schedule the job expiration check to run every day at midnight
scheduler.add_job(job_functions.move_expired_jobs, 'interval', days=1)

app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(user.router, prefix="/api/user", tags=["User"])
app.include_router(job.router, prefix="/api/job", tags=["Job"])
app.include_router(application.router, prefix="/api/application", tags=["Application"])
app.include_router(get_application.router, prefix="/api/ga", tags=["Applications"])
app.include_router(save_job.router, prefix="/api/sj", tags=["Save Jobs"])
app.include_router(recommendation_routes.router, prefix="/api", tags=["Recommendations"])
app.include_router(get_my_applications.router, prefix="/api/gma", tags=["Get My Applications"]) 
app.include_router(resume.router, prefix="/api/resume", tags=["Resume"])
app.include_router(interview.router, prefix="/api/interview", tags=["Interview"])
app.include_router(email.router, prefix="/api/email", tags=["Email"])
app.include_router(active_application.router, prefix="/api/aa", tags=["active_application"])
app.include_router(profile.router, prefix="/api/profile", tags=["profile"])
app.include_router(featured_jobs.router, prefix="/api/featured-jobs", tags=["Featured Jobs"])
app.include_router(employee.router, prefix="/api/emp", tags=["Employee"])


@app.get("/")
def root():
    return {"message": "Job Portal Backend Running"}
