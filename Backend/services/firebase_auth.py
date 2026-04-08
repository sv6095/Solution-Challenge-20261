from __future__ import annotations

import os
from typing import Any

from fastapi import Header, HTTPException

from .security import decode_token


def verify_firebase_or_local_token(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """
    Cloud-first auth: if Firebase is configured use it (placeholder),
    otherwise fallback to local JWT verification. Local dev bypass can be enabled.
    """
    if os.getenv("LOCAL_AUTH_BYPASS", "false").lower() == "true":
        return {"sub": "local-dev-user", "email": "local@example.com", "source": "bypass"}

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization.split(" ", 1)[1]

    # Firebase verification path can be enabled later by checking FIREBASE_* envs.
    firebase_enabled = os.getenv("FIRESTORE_ENABLED", "false").lower() == "true"
    if firebase_enabled and os.getenv("FIREBASE_PROJECT_ID"):
        # Fallback to local decode until firebase-admin integration is added.
        payload = decode_token(token)
        payload["source"] = "firebase-fallback-local-jwt"
        return payload

    payload = decode_token(token)
    payload["source"] = "local-jwt"
    return payload
