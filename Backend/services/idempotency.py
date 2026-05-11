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
  Firestore `idempotency_keys` collection.

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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from google.cloud.firestore_v1.base_query import FieldFilter

from services.firestore_store import _client, _safe_doc_id


# ── Schema ────────────────────────────────────────────────────────────────────


def _ensure_schema() -> None:
    _client()


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


def _prune_expired() -> None:
    """Delete expired keys. Called on every guard check."""
    cutoff = _now().isoformat()
    db = _client()
    docs = list(
        db.collection("idempotency_keys")
        .where(filter=FieldFilter("expires_at", "<=", cutoff))
        .limit(100)
        .stream()
    )
    batch = db.batch()
    for doc in docs:
        batch.delete(doc.reference)
    if docs:
        batch.commit()


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

    ref = _client().collection("idempotency_keys").document(_safe_doc_id(ikey))
    snap = ref.get()
    if snap.exists:
        data = snap.to_dict() or {}
        status = data.get("status")
        if status == "COMPLETED":
            return IdempotencyResult(action="DUPLICATE", ikey=ikey, cached_response=data.get("response"))
        if status == "IN_FLIGHT":
            return IdempotencyResult(action="IN_FLIGHT", ikey=ikey, cached_response=None)
        ref.delete()

    ref.set({
        "ikey": ikey,
        "status": "IN_FLIGHT",
        "owner_id": owner_id,
        "created_at": now.isoformat(),
        "expires_at": expires_at,
    })
    return IdempotencyResult(action="ALLOW", ikey=ikey, cached_response=None)


def mark_completed(ikey: str, response: Any = None) -> None:
    """
    Mark an idempotency key as COMPLETED with the serialized response.
    Call this after a successful operation that was GUARDed.
    """
    now = _now().isoformat()
    _client().collection("idempotency_keys").document(_safe_doc_id(ikey)).set(
        {"status": "COMPLETED", "response": response if response is not None else {"completed": True}, "completed_at": now},
        merge=True,
    )


def mark_failed(ikey: str) -> None:
    """Mark an idempotency key as FAILED so retries are allowed."""
    _client().collection("idempotency_keys").document(_safe_doc_id(ikey)).set({"status": "FAILED"}, merge=True)


def release_in_flight(ikey: str) -> None:
    """
    Release an IN_FLIGHT key without marking it complete or failed.
    Use when the operation was aborted before completing.
    """
    ref = _client().collection("idempotency_keys").document(_safe_doc_id(ikey))
    data = ref.get().to_dict() or {}
    if data.get("status") == "IN_FLIGHT":
        ref.delete()


def get_idempotency_record(ikey: str) -> dict[str, Any] | None:
    doc = _client().collection("idempotency_keys").document(_safe_doc_id(ikey)).get()
    if not doc.exists:
        return None
    data = doc.to_dict() or {}
    return {
        "ikey": data.get("ikey") or ikey,
        "status": data.get("status"),
        "response": data.get("response"),
        "owner_id": data.get("owner_id"),
        "created_at": data.get("created_at"),
        "completed_at": data.get("completed_at"),
        "expires_at": data.get("expires_at"),
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
