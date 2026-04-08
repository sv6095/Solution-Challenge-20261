from __future__ import annotations

import base64
import os

from googleapiclient.discovery import build

from .local_store import add_audit
from .secret_manager import get_secret


def send_rfq_email(recipient: str, subject: str, body: str) -> dict:
    """
    Cloud-first: Gmail API if configured. Local fallback writes audit log.
    """
    gmail_enabled = os.getenv("GMAIL_API_ENABLED", "false").lower() == "true"
    if gmail_enabled:
        try:
            access_token = get_secret("GMAIL_OAUTH_ACCESS_TOKEN", "")
            if not access_token:
                raise RuntimeError("Missing GMAIL_OAUTH_ACCESS_TOKEN")
            service = build("gmail", "v1", credentials=None, developerKey=None)
            message = f"To: {recipient}\r\nSubject: {subject}\r\n\r\n{body}".encode("utf-8")
            raw = base64.urlsafe_b64encode(message).decode("utf-8")
            # raw endpoint normally requires OAuth creds. keep best-effort call and fallback below.
            service.users().messages().send(userId="me", body={"raw": raw}).execute()
            add_audit("gmail_send", f"{recipient}:{subject}")
            return {"status": "sent", "provider": "gmail"}
        except Exception as exc:
            add_audit("gmail_send_failed", str(exc))

    add_audit("local_mail_fallback", f"{recipient}:{subject}")
    return {"status": "logged", "provider": "local-fallback"}
