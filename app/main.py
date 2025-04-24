from fastapi import FastAPI
from apscheduler.schedulers.background import BackgroundScheduler
from app.routes import auth, user, job, resume, interview
from app.functions import job_functions
from contextlib import asynccontextmanager

scheduler = BackgroundScheduler()

@asynccontextmanager
async def lifespan(app):
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)

# Schedule the job expiration check to run every day at midnight
scheduler.add_job(job_functions.move_expired_jobs, 'interval', days=1)

app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(user.router, prefix="/api/user", tags=["User"])
app.include_router(job.router, prefix="/api/job", tags=["Job"])
app.include_router(resume.router, prefix="/api/resume", tags=["Resume"])
app.include_router(interview.router, prefix="/api/interview", tags=["Interview"])

@app.get("/")
def root():
    return {"message": "Job Portal Backend Running"}
