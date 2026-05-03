from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException

_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def _secret() -> str:
    return os.getenv("JWT_SECRET", "change-me-in-prod")


def mint_access_token(
    user_id: str,
    email: str,
    tenant_id: str | None = None,
    role: str = "admin",
    ttl_minutes: int | None = None,
) -> str:
    ttl = ttl_minutes if ttl_minutes is not None else int(os.getenv("JWT_ACCESS_TTL_MINUTES", "525600"))
    payload = {
        "sub": user_id,
        "email": email,
        "tenant_id": tenant_id or user_id,
        "role": role,
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ttl),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def mint_refresh_token(user_id: str) -> str:
    ttl_days = int(os.getenv("JWT_REFRESH_TTL_DAYS", "365"))
    payload = {
        "sub": user_id,
        "type": "refresh",
        "nonce": secrets.token_hex(8),
        "exp": datetime.now(timezone.utc) + timedelta(days=ttl_days),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, _secret(), algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc
