from __future__ import annotations

import base64
import json
import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from .local_store import add_audit
from .secret_manager import get_secret


def send_rfq_email(
    recipient: str,
    subject: str,
    body: str,
    *,
    workflow_id: str | None = None,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """
    Send an RFQ email through the best available transport.

    Delivery tiers (tried in order):
      1. Gmail API (OAuth2 credentials configured)
      2. SMTP relay (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS env vars)
      3. Local fallback (durable audit record — message body never lost)

    On successful send, triggers:
      - action_confirmation lifecycle update (PENDING → SENT)
      - WebSocket push notification to tenant dashboard
    """
    result = _try_gmail(recipient, subject, body)
    if result["status"] != "sent":
        result = _try_smtp(recipient, subject, body)
    if result["status"] != "sent":
        result = _local_fallback(recipient, subject, body)

    # ── Post-send lifecycle integration ───────────────────────────────────
    if workflow_id and result["status"] == "sent":
        _record_send_confirmation(workflow_id, tenant_id, recipient, result)

    return result


def _try_gmail(recipient: str, subject: str, body: str) -> dict[str, Any]:
    """Tier 1: Gmail API with OAuth2."""
    gmail_enabled = os.getenv("GMAIL_API_ENABLED", "false").lower() == "true"
    if not gmail_enabled:
        return {"status": "skipped", "provider": "gmail", "message_id": None}

    try:
        access_token = (
            os.getenv("GMAIL_OAUTH_ACCESS_TOKEN")
            or get_secret("GMAIL_OAUTH_ACCESS_TOKEN", "")
        )
        refresh_token = (
            os.getenv("GMAIL_OAUTH_REFRESH_TOKEN")
            or get_secret("GMAIL_OAUTH_REFRESH_TOKEN", "")
        )
        client_id = os.getenv("GMAIL_CLIENT_ID") or get_secret("GMAIL_CLIENT_ID", "")
        client_secret = os.getenv("GMAIL_CLIENT_SECRET") or get_secret("GMAIL_CLIENT_SECRET", "")
        token_uri = os.getenv("GMAIL_TOKEN_URI") or "https://oauth2.googleapis.com/token"
        if not access_token:
            raise RuntimeError("Missing GMAIL_OAUTH_ACCESS_TOKEN")
        creds = Credentials(
            token=access_token,
            refresh_token=refresh_token or None,
            token_uri=token_uri,
            client_id=client_id or None,
            client_secret=client_secret or None,
            scopes=["https://www.googleapis.com/auth/gmail.send"],
        )
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        message = f"To: {recipient}\r\nSubject: {subject}\r\n\r\n{body}".encode("utf-8")
        raw = base64.urlsafe_b64encode(message).decode("utf-8")
        result = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        add_audit("gmail_send", json.dumps({"recipient": recipient, "subject": subject, "message_id": result.get("id", "")}))
        return {"status": "sent", "provider": "gmail", "message_id": result.get("id")}
    except Exception as exc:
        add_audit("gmail_send_failed", str(exc))
        return {"status": "failed", "provider": "gmail", "message_id": None, "error": str(exc)}


def _try_smtp(recipient: str, subject: str, body: str) -> dict[str, Any]:
    """Tier 2: SMTP relay (SendGrid, AWS SES, or any SMTP server)."""
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_pass = os.getenv("SMTP_PASS", "").strip()
    smtp_from = os.getenv("SMTP_FROM", smtp_user).strip()

    if not smtp_host or not smtp_user:
        return {"status": "skipped", "provider": "smtp", "message_id": None}

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = smtp_from
        msg["To"] = recipient
        msg["Subject"] = subject
        msg["X-SupplyShield-Source"] = "autonomous-pipeline"

        # Plain text part
        msg.attach(MIMEText(body, "plain", "utf-8"))

        # HTML part (simple formatted version)
        html_body = _plain_to_html(body, subject)
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        use_ssl = smtp_port == 465
        if use_ssl:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
            server.ehlo()
            server.starttls()
            server.ehlo()

        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_from, [recipient], msg.as_string())
        server.quit()

        message_id = msg.get("Message-ID", "")
        add_audit("smtp_send", json.dumps({
            "recipient": recipient,
            "subject": subject,
            "host": smtp_host,
            "message_id": message_id,
        }))
        return {"status": "sent", "provider": "smtp", "message_id": message_id}

    except Exception as exc:
        add_audit("smtp_send_failed", json.dumps({
            "host": smtp_host,
            "error": str(exc),
        }))
        return {"status": "failed", "provider": "smtp", "message_id": None, "error": str(exc)}


def _local_fallback(recipient: str, subject: str, body: str) -> dict[str, Any]:
    """Tier 3: Durable local audit record — message body is NEVER lost."""
    fallback_payload = {
        "recipient": recipient,
        "subject": subject,
        "body": body,
        "stored_at": datetime.now(timezone.utc).isoformat(),
    }
    add_audit("local_mail_fallback", json.dumps(fallback_payload))
    return {"status": "logged", "provider": "local-fallback", "message_id": None}


def _plain_to_html(body: str, subject: str) -> str:
    """Convert plain text RFQ body to styled HTML email."""
    escaped = (
        body.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br>\n")
    )
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
             max-width: 640px; margin: 0 auto; padding: 24px;
             background: #f8f9fa; color: #1a1a2e;">
  <div style="background: white; border-radius: 8px; padding: 32px;
              box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
    <h2 style="color: #0d47a1; margin-top: 0;">{subject}</h2>
    <div style="line-height: 1.6; color: #333;">
      {escaped}
    </div>
    <hr style="border: none; border-top: 1px solid #e0e0e0; margin: 24px 0;">
    <p style="font-size: 11px; color: #999;">
      Sent by SupplyShield Autonomous Pipeline · 
      <a href="#" style="color: #0d47a1;">View in Dashboard</a>
    </p>
  </div>
</body>
</html>"""


def _record_send_confirmation(
    workflow_id: str,
    tenant_id: str | None,
    recipient: str,
    result: dict[str, Any],
) -> None:
    """Update action_confirmation lifecycle and push WebSocket event."""
    try:
        from services.action_confirmation import update_action_status
        update_action_status(
            workflow_id=workflow_id,
            status="SENT",
            provider=result.get("provider", "unknown"),
            message_id=result.get("message_id"),
        )
    except Exception:
        pass  # action_confirmation is optional

    if tenant_id:
        try:
            import asyncio
            from services.event_bus import push_incident_event
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(push_incident_event(
                    tenant_id,
                    workflow_id,
                    "rfq_sent",
                    {
                        "recipient": recipient,
                        "provider": result.get("provider"),
                        "message_id": result.get("message_id"),
                    },
                ))
        except Exception:
            pass  # WebSocket push is best-effort

