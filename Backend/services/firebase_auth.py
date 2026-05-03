from __future__ import annotations

import os
from typing import Any

from fastapi import Header, HTTPException

from .security import decode_token


def _verify_firebase_id_token(token: str) -> dict[str, Any]:
    import firebase_admin.auth as fb_auth

    decoded = fb_auth.verify_id_token(token)
    uid = str(decoded.get("uid") or decoded.get("sub") or "")
    return {
        "sub": uid,
        "email": str(decoded.get("email") or ""),
        "tenant_id": str(decoded.get("tenant_id") or decoded.get("org_id") or uid or "demo-tenant"),
        "role": str(decoded.get("role") or "admin"),
        "source": "firebase-id-token",
    }

def _dev_principal() -> dict[str, Any]:
    """Build the local bypass principal from env so dev auth matches local data."""
    return {
        "sub": os.getenv("DEV_USER_ID", "local-dev-user").strip() or "local-dev-user",
        "email": os.getenv("DEV_USER_EMAIL", "dev@local.praecantator").strip() or "dev@local.praecantator",
        "role": os.getenv("DEV_USER_ROLE", "admin").strip() or "admin",
        "tenant_id": os.getenv("DEV_TENANT_ID", "default").strip() or "default",
        "source": "local-bypass",
    }


def verify_firebase_or_local_token(
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> dict[str, Any]:
    """
    Cloud-first auth: if Firebase is configured use it (placeholder),
    otherwise fallback to local JWT verification.
    
    Dev bypass:
      When LOCAL_AUTH_BYPASS=true (default in .env) AND no Authorization header
      is present, returns a synthetic admin principal so dev/demo workflows
      can operate without minting real tokens.
    """
    # ── Dev bypass ────────────────────────────────────────────────────────────
    local_bypass = os.getenv("LOCAL_AUTH_BYPASS", "false").lower() == "true"
    if local_bypass and not authorization:
        # Use X-User-Id header if provided to personalise the dev principal.
        # This keeps local-browser requests aligned with the active user context.
        principal = _dev_principal()
        if x_user_id:
            principal["sub"] = x_user_id
            principal["tenant_id"] = x_user_id
        return principal

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization.split(" ", 1)[1]

    # ── Firebase ID token (Google / email-password via Firebase) ─────────────
    if (os.getenv("AUTH_PROVIDER") or "local").strip().lower() == "firebase":
        try:
            return _verify_firebase_id_token(token)
        except Exception as exc:
            raise HTTPException(status_code=401, detail=f"Invalid or expired token: {exc}") from exc

    # ── Local HS256 JWT (email/password against local store) ─────────────────
    payload = decode_token(token)
    payload["source"] = "local-jwt"
    return payload
