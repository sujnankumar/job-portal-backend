from dotenv import load_dotenv
import os

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "job_portal")
SECRET_KEY = os.getenv("SECRET_KEY", "job_portal_wow_x")
ALGORITHM = "HS256"
