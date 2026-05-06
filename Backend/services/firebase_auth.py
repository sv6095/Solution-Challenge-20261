from __future__ import annotations

import logging
import os
from typing import Any, Callable

import jwt as pyjwt
from fastapi import Header, HTTPException

from .security import decode_token

logger = logging.getLogger(__name__)

_initialized = False


def init_firebase_admin_app() -> None:
    """
    Initialize Firebase Admin once when verifying ID tokens or using Firestore-backed auth.
    On Render, set GOOGLE_APPLICATION_CREDENTIALS to the mounted service account JSON path.
    """
    global _initialized
    if _initialized:
        return

    auth_provider = (os.getenv("AUTH_PROVIDER") or "local").strip().lower()
    firebase_enabled = os.getenv("FIRESTORE_ENABLED", "false").lower() == "true"
    firebase_project = bool(os.getenv("FIREBASE_PROJECT_ID"))
    if auth_provider != "firebase" and not (firebase_enabled and firebase_project):
        _initialized = True
        return

    import firebase_admin
    from firebase_admin import credentials

    if firebase_admin._apps:
        _initialized = True
        return

    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    needs_credentials = auth_provider == "firebase" or (firebase_enabled and firebase_project)
    if cred_path and not os.path.isfile(cred_path):
        if needs_credentials:
            raise RuntimeError(
                f"GOOGLE_APPLICATION_CREDENTIALS points to a missing file: {cred_path!r}. "
                "On Render: Dashboard → your web service → Environment → Secret Files — upload your "
                "Firebase/GCP service account JSON and set this variable to exactly "
                "/etc/secrets/<that-filename>.json, then redeploy."
            ) from None
        logger.warning(
            "GOOGLE_APPLICATION_CREDENTIALS is set but file is missing (%s); ignoring for ADC discovery",
            cred_path,
        )
        os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
        cred_path = ""

    try:
        if cred_path and os.path.isfile(cred_path):
            firebase_admin.initialize_app(credentials.Certificate(cred_path))
            logger.info("Firebase Admin initialized from service account file")
        else:
            firebase_admin.initialize_app()
            logger.info("Firebase Admin initialized with application default credentials")
    except Exception as exc:
        if auth_provider == "firebase":
            logger.exception("Firebase Admin failed to initialize; AUTH_PROVIDER=firebase requires valid credentials")
            raise RuntimeError(
                "AUTH_PROVIDER=firebase but Firebase Admin could not initialize. "
                "On Render, mount a service account JSON and set GOOGLE_APPLICATION_CREDENTIALS to its path."
            ) from exc
        logger.warning("Firebase Admin could not initialize (Firestore may still use ADC): %s", exc)
    _initialized = True


def _token_signing_alg(token: str) -> str | None:
    try:
        alg = pyjwt.get_unverified_header(token).get("alg")
        return str(alg).upper() if alg else None
    except Exception:
        return None


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

    init_firebase_admin_app()

    auth_provider = (os.getenv("AUTH_PROVIDER") or "local").strip().lower()
    firebase_enabled = os.getenv("FIRESTORE_ENABLED", "false").lower() == "true"
    firebase_project = bool(os.getenv("FIREBASE_PROJECT_ID"))

    # Route by JOSE alg so RS256 Firebase ID tokens are never passed to PyJWT HS256-only decode
    # (avoids misleading "The specified alg value is not allowed").
    alg = _token_signing_alg(token)
    verifiers: list[tuple[str, Callable[[str], dict[str, Any]]]] = []
    if alg == "HS256":
        verifiers.append(("local-jwt", decode_token))
    elif alg == "RS256":
        verifiers.append(("firebase-id-token", _verify_firebase_id_token))
    elif auth_provider == "firebase" or (firebase_enabled and firebase_project):
        verifiers.append(("firebase-id-token", _verify_firebase_id_token))
        verifiers.append(("local-jwt", decode_token))
    else:
        verifiers.append(("local-jwt", decode_token))

    last_exc: Exception | None = None
    for source, verifier in verifiers:
        try:
            payload = verifier(token)
            payload["source"] = source
            return payload
        except Exception as exc:
            last_exc = exc
            continue

    detail = f"Invalid or expired token: {last_exc}" if last_exc else "Invalid or expired token"
    raise HTTPException(status_code=401, detail=detail)
