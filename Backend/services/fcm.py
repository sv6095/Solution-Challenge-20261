from __future__ import annotations

import os
from typing import Any

from .local_store import add_audit


def send_fcm_notification(*, token: str | None, title: str, body: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Production-grade FCM dispatch with local durability fallback.
    """
    payload = data or {}
    if token and os.getenv("FIREBASE_ADMIN_ENABLED", "false").lower() == "true":
        try:
            import firebase_admin
            from firebase_admin import credentials, messaging

            if not firebase_admin._apps:
                cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
                firebase_admin.initialize_app(credentials.Certificate(cred_path) if cred_path else None)
            message = messaging.Message(
                token=token,
                notification=messaging.Notification(title=title, body=body),
                data={k: str(v) for k, v in payload.items()},
            )
            message_id = messaging.send(message)
            add_audit("fcm_send", str({"token_present": True, "message_id": message_id}))
            return {"status": "sent", "provider": "fcm", "message_id": message_id}
        except Exception as exc:
            add_audit("fcm_send_failed", str(exc))

    add_audit("fcm_local_fallback", str({"token_present": bool(token), "title": title, "body": body, "data": payload}))
    return {"status": "queued" if token else "skipped", "provider": "local-fallback", "token_present": bool(token), "title": title, "body": body, "data": payload}
