from dotenv import load_dotenv
import os

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL")
DB_NAME = os.getenv("DB_NAME")
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
EMAIL_FROM = os.getenv("EMAIL_FROM", SMTP_USER)

# PhonePe Payment Gateway configuration (set these in your environment)
# def _clean(v: str | None, default: str | None = None):
# 	if v is None:
# 		return default
# 	return v.strip()

# PHONEPE_MERCHANT_ID = _clean(os.getenv("PHONEPE_MERCHANT_ID"))
# PHONEPE_SALT_KEY = _clean(os.getenv("PHONEPE_SALT_KEY"))  # Secret / Salt Key
# PHONEPE_SALT_INDEX = _clean(os.getenv("PHONEPE_SALT_INDEX"), "1")  # Salt Index, typically '1'
# PHONEPE_BASE_URL = _clean(os.getenv("PHONEPE_BASE_URL"), "https://api-preprod.phonepe.com/apis") or "https://api-preprod.phonepe.com/apis"
# # Ensure no trailing slash for consistent joining
# if PHONEPE_BASE_URL.endswith('/'):
# 	PHONEPE_BASE_URL = PHONEPE_BASE_URL.rstrip('/')
# PHONEPE_REDIRECT_BASE = _clean(os.getenv("PHONEPE_REDIRECT_BASE"), BASE_URL) or BASE_URL  # Where PhonePe should redirect after payment
# PHONEPE_MODE = _clean(os.getenv("PHONEPE_MODE"), "live") or "live"  # 'live' | 'mock'

PHONEPE_MERCHANT_ID="PGTESTPAYUAT86"
# PHONEPE_SALT_KEY="MmFlOTdjNWMtYWJiNS00MzI3LTg1OGYtMmZiYmIxZTFlNjc0"
# PHONEPE_SALT_KEY="2ae97c5c-abb5-4327-858f-2fbbb1e1e674"
PHONEPE_SALT_KEY="96434309-7796-489d-8924-ab56988a6076"
PHONEPE_SALT_INDEX="1"
# Use base /apis; code falls back to sandbox path automatically
PHONEPE_BASE_URL="https://api-preprod.phonepe.com/apis"
# Use backend origin so callback hits FastAPI route
PHONEPE_REDIRECT_BASE="http://localhost:8000"
PHONEPE_MODE="live"

# Frontend base URL used for user-facing redirects after payment (success/pending/error)
# Configure via env FRONTEND_BASE_URL in deployment (e.g. https://app.example.com)
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000")
