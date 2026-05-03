from __future__ import annotations

import json
import sqlite3
import hashlib
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
                full_name TEXT DEFAULT '',
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
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_checkpoints (
                workflow_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_outcomes (
                workflow_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS cache_entries (
                cache_key TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                expires_at TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS reasoning_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id TEXT NOT NULL,
                agent TEXT NOT NULL,
                stage TEXT NOT NULL,
                detail TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'success',
                output_json TEXT,
                timestamp TEXT NOT NULL,
                timestamp_ms INTEGER NOT NULL
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_reasoning_workflow ON reasoning_steps(workflow_id, timestamp_ms)")

        # ── Incidents (v4 autonomous pipeline) ──
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS incidents (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL DEFAULT 'default',
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'DETECTED',
                severity TEXT NOT NULL DEFAULT 'LOW',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        try:
            con.execute("ALTER TABLE incidents ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default'")
        except Exception:
            pass
        con.execute("CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_incidents_severity ON incidents(severity)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_incidents_tenant ON incidents(tenant_id)")
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS master_data_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                change_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_master_data_user ON master_data_changes(user_id, created_at)")
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS orchestration_runs (
                run_id TEXT PRIMARY KEY,
                orchestration_path TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL DEFAULT 'default',
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_orch_runs_tenant ON orchestration_runs(tenant_id, updated_at)")

        # ── V4 Graph Normalization (Fix for Giant JSON Blobs) ──
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS graph_nodes (
                tenant_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                node_type TEXT NOT NULL,
                name TEXT NOT NULL,
                lat REAL,
                lng REAL,
                country TEXT,
                duns_number TEXT,
                tier INTEGER,
                contract_value_usd REAL,
                daily_throughput_usd REAL,
                safety_stock_days INTEGER,
                criticality TEXT,
                single_source BOOLEAN,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (tenant_id, node_id)
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS graph_edges (
                tenant_id TEXT NOT NULL,
                from_id TEXT NOT NULL,
                to_id TEXT NOT NULL,
                tier_level INTEGER,
                substitutability REAL,
                mode TEXT,
                PRIMARY KEY (tenant_id, from_id, to_id)
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


def upsert_workflow_checkpoint(workflow_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    updated_at = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        con.execute(
            """
            INSERT INTO workflow_checkpoints(workflow_id, payload_json, updated_at)
            VALUES(?, ?, ?)
            ON CONFLICT(workflow_id) DO UPDATE SET
                payload_json=excluded.payload_json,
                updated_at=excluded.updated_at
            """,
            (workflow_id, json.dumps(payload), updated_at),
        )
    return {"workflow_id": workflow_id, "updated_at": updated_at}


def get_workflow_checkpoint(workflow_id: str) -> dict[str, Any] | None:
    with _conn() as con:
        cur = con.execute("SELECT workflow_id, payload_json, updated_at FROM workflow_checkpoints WHERE workflow_id = ?", (workflow_id,))
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


def upsert_workflow_outcome(workflow_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    updated_at = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        con.execute(
            """
            INSERT INTO workflow_outcomes(workflow_id, payload_json, updated_at)
            VALUES(?, ?, ?)
            ON CONFLICT(workflow_id) DO UPDATE SET
                payload_json=excluded.payload_json,
                updated_at=excluded.updated_at
            """,
            (workflow_id, json.dumps(payload), updated_at),
        )
    return {"workflow_id": workflow_id, "updated_at": updated_at}


def list_workflow_outcomes(limit: int = 200) -> list[dict[str, Any]]:
    with _conn() as con:
        rows = con.execute(
            "SELECT workflow_id, payload_json, updated_at FROM workflow_outcomes ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    results: list[dict[str, Any]] = []
    for row in rows:
        try:
            data = json.loads(row[1] or "{}")
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}
        data.setdefault("workflow_id", row[0])
        data.setdefault("updated_at", row[2])
        results.append(data)
    return results


def create_user(user_id: str, email: str, password_hash: str, company_name: str = "", full_name: str = "") -> dict:
    created_at = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        # Backwards-compatible migration: add full_name column if missing
        try:
            con.execute("ALTER TABLE users ADD COLUMN full_name TEXT DEFAULT ''")
        except Exception:
            pass
        con.execute(
            """
            INSERT INTO users(user_id, email, password_hash, company_name, full_name, created_at)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (user_id, email.lower(), password_hash, company_name, full_name, created_at),
        )
    return {"user_id": user_id, "email": email.lower(), "company_name": company_name, "full_name": full_name, "created_at": created_at}


def get_user_by_email(email: str) -> dict | None:
    with _conn() as con:
        # Backwards-compatible migration: add full_name column if missing
        try:
            con.execute("ALTER TABLE users ADD COLUMN full_name TEXT DEFAULT ''")
        except Exception:
            pass
        with closing(
            con.execute(
                "SELECT user_id, email, password_hash, company_name, full_name, created_at FROM users WHERE email = ?",
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
        "full_name": row[4] or "",
        "created_at": row[5],
    }


def get_user_by_id(user_id: str) -> dict | None:
    """Fetch a user record by user_id for profile auto-population."""
    with _conn() as con:
        # Backwards-compatible migration: add full_name column if missing
        try:
            con.execute("ALTER TABLE users ADD COLUMN full_name TEXT DEFAULT ''")
        except Exception:
            pass
        with closing(
            con.execute(
                "SELECT user_id, email, password_hash, company_name, full_name, created_at FROM users WHERE user_id = ?",
                (user_id,),
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
        "full_name": row[4] or "",
        "created_at": row[5],
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
    sync_graph_to_sql(user_id, payload_json)
    return {"user_id": user_id, "updated_at": updated_at}


def get_context(user_id: str) -> dict | None:
    with _conn() as con:
        with closing(con.execute("SELECT user_id, payload_json, updated_at FROM contexts WHERE user_id = ?", (user_id,))) as cur:
            row = cur.fetchone()
    if not row:
        return None
    return {"user_id": row[0], "payload_json": row[1], "updated_at": row[2]}


def sync_graph_to_sql(user_id: str, payload_json: str) -> None:
    """Normalize the giant JSON blob into scalable SQL tables for efficient intersection queries."""
    try:
        data = json.loads(payload_json)
        suppliers = data.get("suppliers", [])
        logistics = data.get("logistics_nodes", [])
        now = datetime.now(timezone.utc).isoformat()

        # We'll use the user_id as the tenant_id for now, aligning with the current schema constraints.
        tenant_id = user_id 

        with _conn() as con:
            con.execute("BEGIN TRANSACTION")
            # Clear existing network for this tenant completely to avoid dangling edits
            con.execute("DELETE FROM graph_nodes WHERE tenant_id = ?", (tenant_id,))
            con.execute("DELETE FROM graph_edges WHERE tenant_id = ?", (tenant_id,))

            for s in suppliers:
                sid = s.get("id") or str(hash(s.get("name", "")))
                tier = int(str(s.get("tier", "1")).replace("Tier ", "").strip() or 1)
                con.execute(
                    """
                    INSERT INTO graph_nodes(tenant_id, node_id, node_type, name, lat, lng, country, duns_number, tier, contract_value_usd, daily_throughput_usd, safety_stock_days, criticality, single_source, updated_at)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (tenant_id, sid, "supplier", s.get("name", ""), s.get("lat"), s.get("lng"), s.get("country", ""), s.get("dunsNumber", ""), tier, s.get("contract_value_usd", 100000.0), s.get("daily_throughput_usd", 10000.0), int(s.get("safety_stock_days", 7)), s.get("criticality", "medium"), bool(s.get("single_source", False)), now)
                )
            
            for l in logistics:
                lid = l.get("id") or str(hash(l.get("name", "")))
                tier = int(str(l.get("tier", "1")).replace("Tier ", "").strip() or 1)
                con.execute(
                    """
                    INSERT INTO graph_nodes(tenant_id, node_id, node_type, name, lat, lng, country, duns_number, tier, contract_value_usd, daily_throughput_usd, safety_stock_days, criticality, single_source, updated_at)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (tenant_id, lid, "logistics", l.get("name", ""), l.get("lat"), l.get("lng"), l.get("country", ""), l.get("dunsNumber", ""), tier, 0.0, float(l.get("daily_throughput_usd") or 0.0), int(l.get("safety_stock_days") or 7), l.get("criticality", "medium"), False, now)
                )

            con.commit()
    except Exception as e:
        # If sync fails, don't break the main flow.
        pass


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
            basis = f"{item.get('source','')}|{item.get('title','')}|{item.get('location','')}|{item.get('created_at','')}"
            signal_id = f"sig_{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:16]}"
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


def insert_reasoning_step(
    workflow_id: str,
    agent: str,
    stage: str,
    detail: str,
    status: str = "success",
    output: dict[str, Any] | None = None,
    timestamp: str | None = None,
    timestamp_ms: int | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    ts = timestamp or now.isoformat()
    ms = int(now.timestamp() * 1000) if timestamp_ms is None or timestamp_ms <= 0 else timestamp_ms
    out_json = json.dumps(output or {})
    with _conn() as con:
        con.execute(
            """
            INSERT INTO reasoning_steps(workflow_id, agent, stage, detail, status, output_json, timestamp, timestamp_ms)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (workflow_id, agent, stage, detail, status, out_json, ts, ms),
        )
    return {
        "agent": agent,
        "stage": stage,
        "detail": detail,
        "status": status,
        "output": output or {},
        "timestamp": ts,
        "timestamp_ms": ms,
    }


def list_reasoning_steps(workflow_id: str, limit: int = 500) -> list[dict[str, Any]]:
    with _conn() as con:
        cur = con.execute(
            """
            SELECT agent, stage, detail, status, output_json, timestamp, timestamp_ms
            FROM reasoning_steps
            WHERE workflow_id = ?
            ORDER BY timestamp_ms ASC
            LIMIT ?
            """,
            (workflow_id, limit),
        )
        rows = cur.fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            parsed = json.loads(row[4] or "{}")
            if not isinstance(parsed, dict):
                parsed = {}
        except Exception:
            parsed = {}
        out.append(
            {
                "agent": row[0],
                "stage": row[1],
                "detail": row[2],
                "status": row[3],
                "output": parsed,
                "timestamp": row[5],
                "timestamp_ms": row[6],
            }
        )
    return out


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


def cache_set_entry(cache_key: str, payload: Any, ttl_seconds: int = 1800) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(seconds=max(0, ttl_seconds))).isoformat() if ttl_seconds > 0 else None
    serialized = json.dumps(payload)
    with _conn() as con:
        con.execute(
            """
            INSERT INTO cache_entries(cache_key, payload_json, expires_at, updated_at)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                payload_json=excluded.payload_json,
                expires_at=excluded.expires_at,
                updated_at=excluded.updated_at
            """,
            (cache_key, serialized, expires_at, now.isoformat()),
        )
    return {"cache_key": cache_key, "expires_at": expires_at}


def cache_get_entry(cache_key: str) -> Any | None:
    with _conn() as con:
        row = con.execute(
            "SELECT payload_json, expires_at FROM cache_entries WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
    if not row:
        return None
    expires_at = row[1]
    if expires_at:
        try:
            expiry = datetime.fromisoformat(expires_at)
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) >= expiry:
                cache_delete_entry(cache_key)
                return None
        except Exception:
            cache_delete_entry(cache_key)
            return None
    try:
        return json.loads(row[0] or "null")
    except Exception:
        return None


def cache_delete_entry(cache_key: str) -> None:
    with _conn() as con:
        con.execute("DELETE FROM cache_entries WHERE cache_key = ?", (cache_key,))


def cache_prune_expired() -> int:
    cutoff = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        cur = con.execute("DELETE FROM cache_entries WHERE expires_at IS NOT NULL AND expires_at <= ?", (cutoff,))
        deleted = cur.rowcount or 0
    return int(deleted)


# ── Incidents CRUD (v4 autonomous pipeline) ─────────────────────────

def upsert_incident(incident_id: str, payload: dict[str, Any], status: str, severity: str, tenant_id: str = "default") -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        con.execute(
            """
            INSERT INTO incidents(id, tenant_id, payload_json, status, severity, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                tenant_id=excluded.tenant_id,
                payload_json=excluded.payload_json,
                status=excluded.status,
                severity=excluded.severity,
                updated_at=excluded.updated_at
            """,
            (incident_id, tenant_id, json.dumps(payload), status, severity, now, now),
        )
    return {"id": incident_id, "status": status, "updated_at": now}


def get_incident(incident_id: str, tenant_id: str | None = None) -> dict[str, Any] | None:
    with _conn() as con:
        if tenant_id:
            row = con.execute(
                "SELECT id, payload_json, status, severity, created_at, updated_at FROM incidents WHERE id = ? AND tenant_id = ?",
                (incident_id, tenant_id),
            ).fetchone()
        else:
            row = con.execute(
                "SELECT id, payload_json, status, severity, created_at, updated_at FROM incidents WHERE id = ?",
                (incident_id,),
            ).fetchone()
    if not row:
        return None
    try:
        data = json.loads(row[1] or "{}")
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    data["id"] = row[0]
    data["status"] = row[2]
    data["severity"] = row[3]
    data["created_at"] = row[4]
    data["updated_at"] = row[5]
    return data


def _is_visible_incident_record(data: dict[str, Any]) -> bool:
    """
    Only real supply-chain incidents belong in the Incidents surfaces.

    Hidden records:
    - Monte Carlo / simulator artifacts
    - explicit no-impact simulations
    - zero-node records that do not intersect the customer's graph
    """
    if bool(data.get("simulation_only")):
        return False
    if str(data.get("simulation_outcome") or "").strip().lower() == "no_impact":
        return False
    try:
        affected_node_count = int(data.get("affected_node_count") or 0)
    except (TypeError, ValueError):
        affected_node_count = 0
    if affected_node_count <= 0:
        return False
    return True


def _is_simulation_incident_record(data: dict[str, Any]) -> bool:
    return bool(data.get("simulation_only"))


def delete_incident(incident_id: str, tenant_id: str | None = None) -> int:
    with _conn() as con:
        if tenant_id:
            cur = con.execute(
                "DELETE FROM incidents WHERE id = ? AND tenant_id = ?",
                (incident_id, tenant_id),
            )
        else:
            cur = con.execute(
                "DELETE FROM incidents WHERE id = ?",
                (incident_id,),
            )
        deleted = cur.rowcount or 0
    return int(deleted)


def list_incidents(
    status: str | None = None,
    limit: int = 50,
    tenant_id: str | None = None,
    visibility: str = "visible",
) -> list[dict[str, Any]]:
    with _conn() as con:
        query_base = "SELECT id, payload_json, status, severity, created_at, updated_at FROM incidents"
        conditions = []
        params = []
        if status:
            conditions.append("status = ?")
            params.append(status)
        if tenant_id:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)
            
        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        query = f"{query_base}{where_clause} ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = con.execute(query, tuple(params)).fetchall()

    results: list[dict[str, Any]] = []
    for row in rows:
        try:
            data = json.loads(row[1] or "{}")
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}
        data["id"] = row[0]
        data["status"] = row[2]
        data["severity"] = row[3]
        data["created_at"] = row[4]
        data["updated_at"] = row[5]
        if visibility == "simulation":
            if not _is_simulation_incident_record(data):
                continue
        elif visibility != "all" and not _is_visible_incident_record(data):
            continue
        results.append(data)
    return results


def list_simulation_incidents(
    status: str | None = None,
    limit: int = 50,
    tenant_id: str | None = None,
) -> list[dict[str, Any]]:
    return list_incidents(
        status=status,
        limit=limit,
        tenant_id=tenant_id,
        visibility="simulation",
    )


def update_incident_status(incident_id: str, status: str, extra_fields: dict[str, Any] | None = None, tenant_id: str | None = None) -> dict[str, Any] | None:
    existing = get_incident(incident_id, tenant_id)
    if not existing:
        return None
    if extra_fields:
        existing.update(extra_fields)
    existing["status"] = status
    # Note: we use 'default' for tenant_id parameter for backward compatibility if it's missing
    return upsert_incident(incident_id, existing, status, existing.get("severity", "LOW"), tenant_id or "default")


def count_incidents_by_status(tenant_id: str | None = None) -> dict[str, int]:
    with _conn() as con:
        if tenant_id:
            rows = con.execute(
                "SELECT id, payload_json, status FROM incidents WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchall()
        else:
            rows = con.execute("SELECT id, payload_json, status FROM incidents").fetchall()

    counts: dict[str, int] = {}
    for _, payload_json, status in rows:
        try:
            data = json.loads(payload_json or "{}")
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}
        if not _is_visible_incident_record(data):
            continue
        key = str(status or "").strip()
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
    return counts


def append_master_data_change(user_id: str, change_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    created_at = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        con.execute(
            "INSERT INTO master_data_changes(user_id, change_type, payload_json, created_at) VALUES(?, ?, ?, ?)",
            (user_id, change_type, json.dumps(payload), created_at),
        )
    return {"user_id": user_id, "change_type": change_type, "created_at": created_at}


def list_master_data_changes(user_id: str, limit: int = 200) -> list[dict[str, Any]]:
    with _conn() as con:
        rows = con.execute(
            """
            SELECT id, user_id, change_type, payload_json, created_at
            FROM master_data_changes
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row[3] or "{}")
            if not isinstance(payload, dict):
                payload = {}
        except Exception:
            payload = {}
        out.append(
            {
                "id": row[0],
                "user_id": row[1],
                "change_type": row[2],
                "payload": payload,
                "created_at": row[4],
            }
        )
    return out


def upsert_orchestration_run(
    run_id: str,
    orchestration_path: str,
    entity_id: str,
    status: str,
    payload: dict[str, Any],
    tenant_id: str = "default",
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        con.execute(
            """
            INSERT INTO orchestration_runs(run_id, orchestration_path, entity_id, tenant_id, status, payload_json, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                status=excluded.status,
                payload_json=excluded.payload_json,
                updated_at=excluded.updated_at
            """,
            (run_id, orchestration_path, entity_id, tenant_id, status, json.dumps(payload), now, now),
        )
    return {"run_id": run_id, "status": status, "updated_at": now}


def get_orchestration_run(run_id: str, tenant_id: str | None = None) -> dict[str, Any] | None:
    with _conn() as con:
        if tenant_id:
            row = con.execute(
                """
                SELECT run_id, orchestration_path, entity_id, tenant_id, status, payload_json, created_at, updated_at
                FROM orchestration_runs
                WHERE run_id = ? AND tenant_id = ?
                """,
                (run_id, tenant_id),
            ).fetchone()
        else:
            row = con.execute(
                """
                SELECT run_id, orchestration_path, entity_id, tenant_id, status, payload_json, created_at, updated_at
                FROM orchestration_runs
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
    if not row:
        return None
    try:
        payload = json.loads(row[5] or "{}")
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}
    return {
        "run_id": row[0],
        "orchestration_path": row[1],
        "entity_id": row[2],
        "tenant_id": row[3],
        "status": row[4],
        "payload": payload,
        "created_at": row[6],
        "updated_at": row[7],
    }


def list_orchestration_runs(
    entity_id: str | None = None,
    tenant_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    query = """
        SELECT run_id, orchestration_path, entity_id, tenant_id, status, payload_json, created_at, updated_at
        FROM orchestration_runs
    """
    conditions: list[str] = []
    params: list[Any] = []
    if entity_id:
        conditions.append("entity_id = ?")
        params.append(entity_id)
    if tenant_id:
        conditions.append("tenant_id = ?")
        params.append(tenant_id)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)
    with _conn() as con:
        rows = con.execute(query, tuple(params)).fetchall()
    results: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row[5] or "{}")
            if not isinstance(payload, dict):
                payload = {}
        except Exception:
            payload = {}
        results.append(
            {
                "run_id": row[0],
                "orchestration_path": row[1],
                "entity_id": row[2],
                "tenant_id": row[3],
                "status": row[4],
                "payload": payload,
                "created_at": row[6],
                "updated_at": row[7],
            }
        )
    return results


def list_reasoning_steps(workflow_id: str, limit: int = 100) -> list[dict[str, Any]]:
    """
    Return reasoning steps for a workflow/incident, ordered by timestamp_ms ASC.
    Falls back gracefully if the reasoning_steps table doesn't exist yet.
    """
    try:
        with _conn() as con:
            rows = con.execute(
                """
                SELECT agent, stage, detail, status, output_json, timestamp, timestamp_ms
                FROM reasoning_steps
                WHERE workflow_id = ?
                ORDER BY timestamp_ms ASC
                LIMIT ?
                """,
                (workflow_id, limit),
            ).fetchall()
    except Exception:
        return []

    result: list[dict[str, Any]] = []
    for row in rows:
        try:
            output = json.loads(row[4] or "{}")
        except Exception:
            output = {}
        result.append({
            "agent": row[0],
            "stage": row[1],
            "detail": row[2],
            "status": row[3],
            "output": output,
            "timestamp": row[5],
            "timestamp_ms": row[6],
        })
    return result

def get_global_impacted_tenants(duns_number: str) -> list[str]:
    """
    Solves 'Siloed Intelligence' by intersecting global risk across all tenants
    that depend on the same underlying physical entity (DUNS).
    """
    if not duns_number:
        return []
    with _conn() as con:
        rows = con.execute("SELECT DISTINCT tenant_id FROM graph_nodes WHERE duns_number = ?", (duns_number,)).fetchall()
        return [row[0] for row in rows]
