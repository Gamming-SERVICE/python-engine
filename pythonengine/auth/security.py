"""Authentication helpers."""
from __future__ import annotations

import secrets

from fastapi import HTTPException, Request
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf"] = token
    return token


def require_login(request: Request) -> None:
    if not request.app.state.config.authentication.enabled:
        return
    if not request.session.get("user"):
        raise HTTPException(status_code=303, headers={"Location": "/login"})


def verify_csrf(request: Request, token: str | None) -> None:
    if token != request.session.get("csrf"):
        raise HTTPException(status_code=403, detail="invalid csrf token")
