"""Password hashing (bcrypt) + JWT auth (HS256, 30-day expiry)."""
import os
from datetime import datetime, timedelta
import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from db import get_db
from models import User

SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY env var is required")

TOKEN_DAYS = 30

_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    # bcrypt caps at 72 bytes; truncate deterministically to avoid hard failures.
    pw = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, pass_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], pass_hash.encode("utf-8"))
    except Exception:
        return False


def create_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.utcnow() + timedelta(days=TOKEN_DAYS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def user_dict(u: User) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "display_name": u.display_name,
        "coach_id": u.coach_id,
        "hearts": u.hearts,
        "timezone": u.timezone,
        "onboarding_done": u.onboarding_done,
    }


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if not creds or not creds.credentials:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    try:
        payload = jwt.decode(creds.credentials, SECRET_KEY, algorithms=["HS256"])
        user_id = int(payload["sub"])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user
