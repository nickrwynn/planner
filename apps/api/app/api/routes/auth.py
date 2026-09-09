from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db_from_request
from app.core.config import get_settings
from app.models.user import User
from app.services.auth_passwords import hash_password, mint_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthCredentials(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=200)
    name: str | None = Field(default=None, max_length=200)


class AuthUserOut(BaseModel):
    id: str
    email: str
    name: str | None = None


class AuthTokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUserOut


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _user_out(user: User) -> AuthUserOut:
    return AuthUserOut(id=str(user.id), email=user.email, name=user.name)


@router.post("/register", response_model=AuthTokenOut)
def register(payload: AuthCredentials, db: Session = Depends(get_db_from_request)):
    email = _normalize_email(payload.email)
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email")
    password = payload.password
    if len(password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 8 characters")

    existing = db.execute(select(User).where(User.email == email)).scalars().first()
    settings = get_settings()

    if existing is not None:
        # Allow claiming the seed/dev account once (password_hash still null).
        if existing.password_hash:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Account already exists — sign in instead")
        existing.password_hash = hash_password(password)
        if payload.name and payload.name.strip():
            existing.name = payload.name.strip()
        db.add(existing)
        db.commit()
        db.refresh(existing)
        token = mint_access_token(user_id=str(existing.id), settings=settings)
        return AuthTokenOut(access_token=token, user=_user_out(existing))

    user = User(
        email=email,
        name=(payload.name or "").strip() or email.split("@", 1)[0],
        password_hash=hash_password(password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = mint_access_token(user_id=str(user.id), settings=settings)
    return AuthTokenOut(access_token=token, user=_user_out(user))


@router.post("/login", response_model=AuthTokenOut)
def login(payload: AuthCredentials, db: Session = Depends(get_db_from_request)):
    email = _normalize_email(payload.email)
    user = db.execute(select(User).where(User.email == email)).scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No account with that email — create an account first (or point the app at your hosted API)",
        )
    if not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This account has no password yet — use Create account to claim it",
        )
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password")
    settings = get_settings()
    token = mint_access_token(user_id=str(user.id), settings=settings)
    return AuthTokenOut(access_token=token, user=_user_out(user))


@router.get("/me", response_model=AuthUserOut)
def me(user: User = Depends(get_current_user)):
    return _user_out(user)
