"""
idempotency.py — Global Idempotency Framework
==============================================
Prevents duplicate approvals, double-dispatched RFQs, and repeated external
actions across retries, network failures, and UI double-clicks.

Pattern:
  Every idempotent operation gets a stable `idempotency_key` (caller supplies it
  or one is derived from content hashing). Before executing, the caller calls
  `idempotency_guard()`. The guard either:
    - Returns ALLOW → caller proceeds, then calls `mark_completed()`.
    - Returns DUPLICATE → caller returns the cached result from the first execution.
    - Returns IN_FLIGHT → caller waits or returns 202 (depends on use case).

Storage:
  SQLite `idempotency_keys` table (same DB as incidents).

Retention:
  Keys expire after TTL_SECONDS (default 72 hours). Expired keys are pruned
  on each guard check to avoid unbounded growth.

Usage:
    from services.idempotency import idempotency_guard, mark_completed, IdempotencyResult

    # Approving an incident:
    key = f"approve:{incident_id}"
    result = idempotency_guard(key, ttl_seconds=86400)

    if result.is_duplicate:
        return result.cached_response  # Return original approval result

    # ... do the actual approval ...
    approval_response = {"status": "approved", ...}
    mark_completed(key, approval_response)
    return approval_response
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from services.local_store import DB_PATH


# ── Schema ────────────────────────────────────────────────────────────────────


def _ensure_schema() -> None:
    with sqlite3.connect(DB_PATH) as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("""
            CREATE TABLE IF NOT EXISTS idempotency_keys (
                ikey          TEXT PRIMARY KEY,
                status        TEXT NOT NULL DEFAULT 'IN_FLIGHT',
                response_json TEXT,
                owner_id      TEXT,
                created_at    TEXT NOT NULL,
                completed_at  TEXT,
                expires_at    TEXT NOT NULL
            )
        """)
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_ikey_expires ON idempotency_keys(expires_at)"
        )


_ensure_schema()

DEFAULT_TTL_SECONDS = 72 * 3600  # 72 hours


# ── Data model ────────────────────────────────────────────────────────────────


@dataclass
class IdempotencyResult:
    """Result of a guard check."""
    action: str           # "ALLOW" | "DUPLICATE" | "IN_FLIGHT"
    ikey: str
    cached_response: Any  # populated when action == "DUPLICATE"

    @property
    def is_duplicate(self) -> bool:
        return self.action == "DUPLICATE"

    @property
    def is_in_flight(self) -> bool:
        return self.action == "IN_FLIGHT"

    @property
    def is_allowed(self) -> bool:
        return self.action == "ALLOW"


# ── Internal helpers ──────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def _prune_expired() -> None:
    """Delete expired keys. Called on every guard check."""
    cutoff = _now().isoformat()
    with _conn() as con:
        con.execute("DELETE FROM idempotency_keys WHERE expires_at <= ?", (cutoff,))


def derive_key(*parts: str) -> str:
    """
    Derive a stable idempotency key from multiple string parts.

    Usage:
        key = derive_key("approve", incident_id, user_id)
        key = derive_key("rfq_dispatch", incident_id)
    """
    raw = ":".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


# ── Public API ────────────────────────────────────────────────────────────────


def idempotency_guard(
    ikey: str,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    owner_id: str = "",
) -> IdempotencyResult:
    """
    Attempt to acquire an idempotency slot for `ikey`.

    Returns IdempotencyResult:
      - ALLOW:       Key is new. Proceed with the operation.
      - DUPLICATE:   Key already COMPLETED. Return the cached response.
      - IN_FLIGHT:   Key exists but not yet completed (concurrent request).

    The caller MUST call `mark_completed(ikey, response)` after a successful
    ALLOW operation, or `mark_failed(ikey)` on failure.
    """
    _prune_expired()

    now = _now()
    expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()

    with _conn() as con:
        # Try to read existing key
        row = con.execute(
            "SELECT status, response_json FROM idempotency_keys WHERE ikey = ?",
            (ikey,),
        ).fetchone()

        if row:
            status, response_json = row
            if status == "COMPLETED":
                try:
                    cached = json.loads(response_json or "null")
                except Exception:
                    cached = None
                return IdempotencyResult(action="DUPLICATE", ikey=ikey, cached_response=cached)
            if status == "IN_FLIGHT":
                return IdempotencyResult(action="IN_FLIGHT", ikey=ikey, cached_response=None)
            # Status is FAILED — allow retry
            con.execute(
                "DELETE FROM idempotency_keys WHERE ikey = ?",
                (ikey,),
            )

        # Insert new IN_FLIGHT record using INSERT OR IGNORE for race safety
        con.execute(
            """
            INSERT OR IGNORE INTO idempotency_keys
                (ikey, status, owner_id, created_at, expires_at)
            VALUES (?, 'IN_FLIGHT', ?, ?, ?)
            """,
            (ikey, owner_id, now.isoformat(), expires_at),
        )
        # Re-check if we won the race
        status_after = con.execute(
            "SELECT status FROM idempotency_keys WHERE ikey = ?", (ikey,)
        ).fetchone()

        if status_after and status_after[0] == "IN_FLIGHT":
            return IdempotencyResult(action="ALLOW", ikey=ikey, cached_response=None)

        # Another concurrent request won — return IN_FLIGHT
        return IdempotencyResult(action="IN_FLIGHT", ikey=ikey, cached_response=None)


def mark_completed(ikey: str, response: Any = None) -> None:
    """
    Mark an idempotency key as COMPLETED with the serialized response.
    Call this after a successful operation that was GUARDed.
    """
    now = _now().isoformat()
    try:
        response_json = json.dumps(response)
    except Exception:
        response_json = json.dumps({"completed": True})

    with _conn() as con:
        con.execute(
            "UPDATE idempotency_keys SET status = 'COMPLETED', response_json = ?, completed_at = ? WHERE ikey = ?",
            (response_json, now, ikey),
        )


def mark_failed(ikey: str) -> None:
    """Mark an idempotency key as FAILED so retries are allowed."""
    with _conn() as con:
        con.execute(
            "UPDATE idempotency_keys SET status = 'FAILED' WHERE ikey = ?",
            (ikey,),
        )


def release_in_flight(ikey: str) -> None:
    """
    Release an IN_FLIGHT key without marking it complete or failed.
    Use when the operation was aborted before completing.
    """
    with _conn() as con:
        con.execute(
            "DELETE FROM idempotency_keys WHERE ikey = ? AND status = 'IN_FLIGHT'",
            (ikey,),
        )


def get_idempotency_record(ikey: str) -> dict[str, Any] | None:
    with _conn() as con:
        row = con.execute(
            "SELECT ikey, status, response_json, owner_id, created_at, completed_at, expires_at "
            "FROM idempotency_keys WHERE ikey = ?",
            (ikey,),
        ).fetchone()
    if not row:
        return None
    try:
        response = json.loads(row[2] or "null")
    except Exception:
        response = None
    return {
        "ikey": row[0],
        "status": row[1],
        "response": response,
        "owner_id": row[3],
        "created_at": row[4],
        "completed_at": row[5],
        "expires_at": row[6],
    }


# ── Decorator for functions ────────────────────────────────────────────────────


def idempotent(key_fn=None, ttl_seconds: int = DEFAULT_TTL_SECONDS):
    """
    Decorator for synchronous and async functions.

    Usage:
        @idempotent(key_fn=lambda inc_id, **kw: f"approve:{inc_id}")
        async def approve_incident(inc_id: str, user_id: str) -> dict:
            ...
    """
    import functools

    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            ikey = key_fn(*args, **kwargs) if key_fn else derive_key(func.__name__, str(args))
            result = idempotency_guard(ikey, ttl_seconds=ttl_seconds)
            if result.is_duplicate:
                return result.cached_response
            if result.is_in_flight:
                return {"status": "in_flight", "message": "Operation already in progress", "ikey": ikey}
            try:
                import asyncio
                if asyncio.iscoroutinefunction(func):
                    response = await func(*args, **kwargs)
                else:
                    response = func(*args, **kwargs)
                mark_completed(ikey, response)
                return response
            except Exception:
                mark_failed(ikey)
                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            ikey = key_fn(*args, **kwargs) if key_fn else derive_key(func.__name__, str(args))
            result = idempotency_guard(ikey, ttl_seconds=ttl_seconds)
            if result.is_duplicate:
                return result.cached_response
            if result.is_in_flight:
                return {"status": "in_flight", "message": "Operation already in progress", "ikey": ikey}
            try:
                response = func(*args, **kwargs)
                mark_completed(ikey, response)
                return response
            except Exception:
                mark_failed(ikey)
                raise

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
