import os
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models import User

JWT_ALGORITHM = "HS256"
DEFAULT_JWT_EXPIRE_MINUTES = 60


def _get_jwt_secret() -> str:
    """Read the JWT signing secret from the environment, raising if it's unset."""
    secret = os.environ.get("JWT_SECRET_KEY")
    if not secret:
        raise RuntimeError(
            "JWT_SECRET_KEY environment variable must be set to sign/verify tokens."
        )
    return secret


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt, returning the encoded hash as a string."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Check whether a plaintext password matches a bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(user_id: uuid.UUID) -> str:
    """Encode a signed JWT for the given user id with an expiration claim."""
    expire_minutes = int(os.environ.get("JWT_EXPIRE_MINUTES", DEFAULT_JWT_EXPIRE_MINUTES))
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=expire_minutes),
    }
    return jwt.encode(payload, _get_jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID:
    """Decode and validate a JWT, returning the encoded user id or raising HTTPException(401)."""
    try:
        payload = jwt.decode(token, _get_jwt_secret(), algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or expired token"
        ) from exc

    subject = payload.get("sub")
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")

    try:
        return uuid.UUID(subject)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token"
        ) from exc


def authenticate_attorney(db: Session, email: str, password: str) -> User | None:
    """Look up a User by email and verify the password, returning None on any failure."""
    user = db.query(User).filter(User.email == email).first()
    if user is None or not verify_password(password, user.password_hash):
        return None
    return user


def get_current_attorney(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency: resolve the authenticated User from the Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token"
        )

    token = authorization.removeprefix("Bearer ").strip()
    user_id = decode_access_token(token)

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found")
    return user


def seed_attorney_from_env(db: Session) -> None:
    """Idempotently create an attorney account from SEED_ATTORNEY_* env vars, if all are set."""
    email = os.environ.get("SEED_ATTORNEY_EMAIL")
    password = os.environ.get("SEED_ATTORNEY_PASSWORD")
    name = os.environ.get("SEED_ATTORNEY_NAME")

    if not (email and password and name):
        return

    existing = db.query(User).filter(User.email == email).first()
    if existing is not None:
        return

    user = User(email=email, password_hash=hash_password(password), name=name)
    db.add(user)
    db.commit()
