from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone
from app.config.settings import SECRET_KEY, ALGORITHM

def create_access_token(data: dict, expires_delta: int = None, remember_me: bool = False):
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if remember_me:
        # Set expiration to 30 days from now, at next midnight
        expire = (now + timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        # Set expiration to next midnight (today at 23:59:59.999999)
        tomorrow = now + timedelta(days=1)
        expire = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
