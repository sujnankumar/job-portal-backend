from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone
from app.config.settings import SECRET_KEY, ALGORITHM
from app.utils.timezone_utils import get_ist_now, IST

def create_access_token(data: dict, expires_delta: int = None, remember_me: bool = False):
    to_encode = data.copy()
    now = get_ist_now()
    if remember_me:
        # Set expiration to 30 days from now, at next midnight IST
        expire = (now + timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        # Set expiration to next midnight IST
        tomorrow = now + timedelta(days=1)
        expire = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Convert to UTC for JWT (standard practice)
    expire_utc = expire.astimezone(timezone.utc)
    to_encode.update({"exp": expire_utc})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
