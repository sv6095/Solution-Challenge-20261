from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parents[1] / "local_fallback.db"


def _conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def init_local_store() -> None:
    with _conn() as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA foreign_keys=ON")
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                company_name TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS contexts (
                user_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_events (
                workflow_id TEXT PRIMARY KEY,
                stage TEXT NOT NULL,
                confidence REAL NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS rfq_events (
                rfq_id TEXT PRIMARY KEY,
                user_id TEXT,
                workflow_id TEXT,
                recipient TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        # Backwards-compatible migration (older DBs won't have workflow_id)
        try:
            con.execute("ALTER TABLE rfq_events ADD COLUMN workflow_id TEXT")
        except Exception:
            pass

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS rfq_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rfq_id TEXT NOT NULL,
                direction TEXT NOT NULL, -- "outbound" | "inbound" | "note"
                sender TEXT,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS signals (
                signal_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS signals_archive (
                signal_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                archived_at TEXT NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                payload TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_reports (
                workflow_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )


def upsert_workflow_event(workflow_id: str, stage: str, confidence: float) -> dict:
    updated_at = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        con.execute(
            """
            INSERT INTO workflow_events(workflow_id, stage, confidence, updated_at)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(workflow_id) DO UPDATE SET
                stage=excluded.stage,
                confidence=excluded.confidence,
                updated_at=excluded.updated_at
            """,
            (workflow_id, stage, confidence, updated_at),
        )
    return {"workflow_id": workflow_id, "stage": stage, "confidence": confidence, "updated_at": updated_at}


def get_workflow_event(workflow_id: str) -> dict | None:
    with _conn() as con:
        cur = con.execute(
            "SELECT workflow_id, stage, confidence, updated_at FROM workflow_events WHERE workflow_id = ?",
            (workflow_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {"workflow_id": row[0], "stage": row[1], "confidence": row[2], "updated_at": row[3]}


def add_audit(action: str, payload: str = "") -> None:
    with _conn() as con:
        con.execute(
            "INSERT INTO audit_log(action, payload, created_at) VALUES(?, ?, ?)",
            (action, payload, datetime.now(timezone.utc).isoformat()),
        )


def list_audit(limit: int = 50) -> list[dict]:
    with _conn() as con:
        cur = con.execute(
            "SELECT id, action, payload, created_at FROM audit_log ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = cur.fetchall()
    return [{"id": row[0], "action": row[1], "payload": row[2], "timestamp": row[3]} for row in rows]


def get_audit(audit_id: int) -> dict | None:
    with _conn() as con:
        cur = con.execute("SELECT id, action, payload, created_at FROM audit_log WHERE id = ?", (audit_id,))
        row = cur.fetchone()
    if not row:
        return None
    return {"id": row[0], "action": row[1], "payload": row[2], "timestamp": row[3]}


def upsert_workflow_report(workflow_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    updated_at = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        con.execute(
            """
            INSERT INTO workflow_reports(workflow_id, payload_json, updated_at)
            VALUES(?, ?, ?)
            ON CONFLICT(workflow_id) DO UPDATE SET
                payload_json=excluded.payload_json,
                updated_at=excluded.updated_at
            """,
            (workflow_id, json.dumps(payload), updated_at),
        )
    return {"workflow_id": workflow_id, "updated_at": updated_at}


def get_workflow_report(workflow_id: str) -> dict[str, Any] | None:
    with _conn() as con:
        cur = con.execute("SELECT workflow_id, payload_json, updated_at FROM workflow_reports WHERE workflow_id = ?", (workflow_id,))
        row = cur.fetchone()
    if not row:
        return None
    try:
        data = json.loads(row[1] or "{}")
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    data.setdefault("workflow_id", row[0])
    data.setdefault("updated_at", row[2])
    return data


def create_user(user_id: str, email: str, password_hash: str, company_name: str = "") -> dict:
    created_at = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        con.execute(
            """
            INSERT INTO users(user_id, email, password_hash, company_name, created_at)
            VALUES(?, ?, ?, ?, ?)
            """,
            (user_id, email.lower(), password_hash, company_name, created_at),
        )
    return {"user_id": user_id, "email": email.lower(), "company_name": company_name, "created_at": created_at}


def get_user_by_email(email: str) -> dict | None:
    with _conn() as con:
        with closing(
            con.execute(
                "SELECT user_id, email, password_hash, company_name, created_at FROM users WHERE email = ?",
                (email.lower(),),
            )
        ) as cur:
            row = cur.fetchone()
    if not row:
        return None
    return {
        "user_id": row[0],
        "email": row[1],
        "password_hash": row[2],
        "company_name": row[3],
        "created_at": row[4],
    }


def upsert_context(user_id: str, payload_json: str) -> dict:
    updated_at = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        con.execute(
            """
            INSERT INTO contexts(user_id, payload_json, updated_at)
            VALUES(?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                payload_json=excluded.payload_json,
                updated_at=excluded.updated_at
            """,
            (user_id, payload_json, updated_at),
        )
    return {"user_id": user_id, "updated_at": updated_at}


def get_context(user_id: str) -> dict | None:
    with _conn() as con:
        with closing(con.execute("SELECT user_id, payload_json, updated_at FROM contexts WHERE user_id = ?", (user_id,))) as cur:
            row = cur.fetchone()
    if not row:
        return None
    return {"user_id": row[0], "payload_json": row[1], "updated_at": row[2]}


def insert_signal(signal_id: str, payload_json: str) -> None:
    with _conn() as con:
        con.execute(
            "INSERT OR REPLACE INTO signals(signal_id, payload_json, created_at) VALUES(?, ?, ?)",
            (signal_id, payload_json, datetime.now(timezone.utc).isoformat()),
        )


def list_signals(limit: int = 50) -> list[dict[str, Any]]:
    with _conn() as con:
        with closing(con.execute("SELECT signal_id, payload_json, created_at FROM signals ORDER BY created_at DESC LIMIT ?", (limit,))) as cur:
            rows = cur.fetchall()
    return [{"signal_id": row[0], "payload_json": row[1], "created_at": row[2]} for row in rows]


def replace_active_signals(items: list[dict[str, Any]]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    deduped: dict[str, dict[str, Any]] = {}
    for item in items:
        signal_id = str(item.get("id") or item.get("signal_id") or "").strip()
        if not signal_id:
            signal_id = f"sig_{abs(hash((item.get('source'), item.get('title'), item.get('location'))))}"
        deduped[signal_id] = item

    with _conn() as con:
        existing_rows = con.execute("SELECT signal_id, payload_json, created_at FROM signals").fetchall()
        existing_ids = {row[0] for row in existing_rows}
        incoming_ids = set(deduped.keys())

        stale_ids = existing_ids - incoming_ids
        if stale_ids:
            placeholders = ",".join("?" for _ in stale_ids)
            rows_to_archive = con.execute(
                f"SELECT signal_id, payload_json, created_at FROM signals WHERE signal_id IN ({placeholders})",
                tuple(stale_ids),
            ).fetchall()
            con.executemany(
                "INSERT INTO signals_archive(signal_id, payload_json, created_at, archived_at) VALUES(?, ?, ?, ?)",
                [(r[0], r[1], r[2], now) for r in rows_to_archive],
            )
            con.execute(f"DELETE FROM signals WHERE signal_id IN ({placeholders})", tuple(stale_ids))

        for signal_id, payload in deduped.items():
            con.execute(
                "INSERT OR REPLACE INTO signals(signal_id, payload_json, created_at) VALUES(?, ?, ?)",
                (signal_id, json.dumps(payload), now),
            )


def purge_archived_signals(days: int = 7) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with _conn() as con:
        cur = con.execute("DELETE FROM signals_archive WHERE archived_at < ?", (cutoff,))
        deleted = cur.rowcount or 0
    return int(deleted)


def create_rfq_event(rfq_id: str, user_id: str, recipient: str, subject: str, body: str, status: str) -> dict:
    created_at = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        con.execute(
            """
            INSERT INTO rfq_events(rfq_id, user_id, workflow_id, recipient, subject, body, status, created_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (rfq_id, user_id, None, recipient, subject, body, status, created_at),
        )
    return {"rfq_id": rfq_id, "status": status, "created_at": created_at}


def create_rfq_event_linked(
    rfq_id: str,
    user_id: str,
    workflow_id: str | None,
    recipient: str,
    subject: str,
    body: str,
    status: str,
) -> dict:
    created_at = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        con.execute(
            """
            INSERT INTO rfq_events(rfq_id, user_id, workflow_id, recipient, subject, body, status, created_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (rfq_id, user_id, workflow_id, recipient, subject, body, status, created_at),
        )
    return {"rfq_id": rfq_id, "status": status, "created_at": created_at}


def list_rfq_events(limit: int = 50) -> list[dict]:
    with _conn() as con:
        with closing(
            con.execute(
                "SELECT rfq_id, user_id, workflow_id, recipient, subject, body, status, created_at FROM rfq_events ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        ) as cur:
            rows = cur.fetchall()
    return [
        {
            "rfq_id": row[0],
            "user_id": row[1],
            "workflow_id": row[2],
            "recipient": row[3],
            "subject": row[4],
            "body": row[5],
            "status": row[6],
            "created_at": row[7],
        }
        for row in rows
    ]


def update_rfq_status(rfq_id: str, status: str) -> dict[str, Any] | None:
    with _conn() as con:
        cur = con.execute("UPDATE rfq_events SET status = ? WHERE rfq_id = ?", (status, rfq_id))
        if (cur.rowcount or 0) <= 0:
            return None
    return {"rfq_id": rfq_id, "status": status}


def add_rfq_message(rfq_id: str, direction: str, sender: str | None, body: str) -> dict[str, Any]:
    created_at = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        con.execute(
            "INSERT INTO rfq_messages(rfq_id, direction, sender, body, created_at) VALUES(?, ?, ?, ?, ?)",
            (rfq_id, direction, sender, body, created_at),
        )
    return {"rfq_id": rfq_id, "direction": direction, "sender": sender, "body": body, "created_at": created_at}


def list_rfq_messages(rfq_id: str, limit: int = 50) -> list[dict[str, Any]]:
    with _conn() as con:
        cur = con.execute(
            "SELECT id, rfq_id, direction, sender, body, created_at FROM rfq_messages WHERE rfq_id = ? ORDER BY id DESC LIMIT ?",
            (rfq_id, limit),
        )
        rows = cur.fetchall()
    items = [
        {"id": r[0], "rfq_id": r[1], "direction": r[2], "sender": r[3], "body": r[4], "created_at": r[5]}
        for r in rows
    ]
    return list(reversed(items))


def list_workflow_reports(limit: int = 100) -> list[dict[str, Any]]:
    with _conn() as con:
        cur = con.execute(
            "SELECT workflow_id, payload_json, updated_at FROM workflow_reports ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        )
        rows = cur.fetchall()
    items: list[dict[str, Any]] = []
    for (workflow_id, payload_json, updated_at) in rows:
        try:
            payload = json.loads(payload_json or "{}")
            if not isinstance(payload, dict):
                payload = {}
        except Exception:
            payload = {}
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        items.append(
            {
                "workflow_id": workflow_id,
                "updated_at": updated_at,
                "summary": summary,
            }
        )
    return items
