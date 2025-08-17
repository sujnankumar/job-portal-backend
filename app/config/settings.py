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
def _clean(v: str | None, default: str | None = None):
	if v is None:
		return default
	return v.strip()

PHONEPE_MERCHANT_ID = _clean(os.getenv("PHONEPE_MERCHANT_ID"))
PHONEPE_SALT_KEY = _clean(os.getenv("PHONEPE_SALT_KEY"))  # Secret / Salt Key
PHONEPE_SALT_INDEX = _clean(os.getenv("PHONEPE_SALT_INDEX"), "1")  # Salt Index, typically '1'
PHONEPE_BASE_URL = _clean(os.getenv("PHONEPE_BASE_URL"), "https://api-preprod.phonepe.com/apis") or "https://api-preprod.phonepe.com/apis"
# Ensure no trailing slash for consistent joining
if PHONEPE_BASE_URL.endswith('/'):
	PHONEPE_BASE_URL = PHONEPE_BASE_URL.rstrip('/')
PHONEPE_REDIRECT_BASE = _clean(os.getenv("PHONEPE_REDIRECT_BASE"), BASE_URL) or BASE_URL  # Where PhonePe should redirect after payment
PHONEPE_MODE = _clean(os.getenv("PHONEPE_MODE"), "live") or "live"  # 'live' | 'mock'