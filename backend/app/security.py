import os
from datetime import datetime, timedelta, timezone
import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session
from .db import get_db
from .models import User

SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me-please-0123456789")
ADMIN_KEY = os.getenv("ADMIN_KEY", "dev-admin-key")


def make_token(user_id: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=365)
    return jwt.encode({"sub": str(user_id), "exp": exp}, SECRET, algorithm="HS256")


def current_user(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> User:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing_token")
    try:
        data = jwt.decode(authorization[7:], SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "bad_token")
    user = db.get(User, int(data["sub"]))
    if not user:
        raise HTTPException(401, "no_user")
    return user


def admin_only(x_admin_key: str = Header(default="")):
    if x_admin_key != ADMIN_KEY:
        raise HTTPException(403, "forbidden")
