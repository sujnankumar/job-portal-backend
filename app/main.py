from fastapi import FastAPI
from app.routes import auth, user, job

app = FastAPI()

app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(user.router, prefix="/api/user", tags=["User"])
app.include_router(job.router, prefix="/api/job", tags=["Job"])

@app.get("/")
def root():
    return {"message": "Job Portal Backend Running"}
