from __future__ import annotations

from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.user import User


def get_db():
    raise RuntimeError("get_db must be provided as a dependency with Request-scoped access")


def get_db_from_request(request: Request):
    SessionLocal = request.app.state.db_sessionmaker
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    db: Session = Depends(get_db_from_request),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> User:
    """Resolve current user from bearer auth or explicit dev mode fallback."""
    settings = get_settings()
    auth_mode = str(settings.auth_mode or "bearer").lower().strip()

    if auth_mode == "bearer":
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing bearer token",
            )
        token = authorization.split(" ", 1)[1].strip()
        try:
            decode_kwargs: dict = {
                "jwt": token,
                "key": settings.auth_jwt_secret,
                "algorithms": [settings.auth_jwt_algorithm],
                "options": {"require": ["sub", "exp", "iat"]},
                "leeway": max(0, int(settings.auth_jwt_leeway_seconds)),
            }
            if settings.auth_jwt_issuer:
                decode_kwargs["issuer"] = settings.auth_jwt_issuer
            if settings.auth_jwt_audience:
                decode_kwargs["audience"] = settings.auth_jwt_audience
            claims = jwt.decode(**decode_kwargs)
            sub = claims.get("sub")
            if not sub:
                raise ValueError("Missing sub claim")
            user_id = UUID(str(sub))
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid bearer token",
            ) from e
        user = db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user")
        return user

    if auth_mode != "dev":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Unsupported AUTH_MODE '{auth_mode}'",
        )

    if x_user_id:
        try:
            user_id = UUID(x_user_id)
            user = db.get(User, user_id)
            if user:
                return user
        except Exception:
            pass

    user = db.execute(select(User).order_by(User.created_at.asc())).scalars().first()
    if user:
        return user

    # Explicitly dev-mode bootstrap only.
    user = User(email="dev@example.com", name="Dev User")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

