from __future__ import annotations

import json
import os
import time
from typing import Any

from .local_store import cache_get_entry, cache_prune_expired, cache_set_entry

CACHE_PROVIDER = (os.getenv("CACHE_PROVIDER") or "memory").strip().lower()

# In-memory: value -> (payload, expires_at_monotonic or None)
_memory: dict[str, tuple[Any, float | None]] = {}


def _memory_get(key: str) -> Any | None:
    row = _memory.get(key)
    if row is None:
        return None
    val, exp = row
    if exp is not None and time.monotonic() > exp:
        _memory.pop(key, None)
        return None
    return val


def _memory_set(key: str, value: Any, ttl_seconds: int) -> None:
    exp = time.monotonic() + float(ttl_seconds) if ttl_seconds > 0 else None
    _memory[key] = (value, exp)


async def cache_get(key: str) -> Any | None:
    if CACHE_PROVIDER == "redis":
        try:
            from upstash_redis import Redis

            url = (os.getenv("UPSTASH_REDIS_REST_URL") or "").strip()
            token = (os.getenv("UPSTASH_REDIS_REST_TOKEN") or "").strip()
            r = Redis(url=url, token=token) if url and token else Redis.from_env()
            raw = r.get(key)
            if raw is None:
                return None
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8", errors="replace")
            try:
                return json.loads(raw)
            except Exception:
                return raw
        except Exception:
            sqlite_value = cache_get_entry(key)
            if sqlite_value is not None:
                return sqlite_value
            return _memory_get(key)
    sqlite_value = cache_get_entry(key)
    if sqlite_value is not None:
        return sqlite_value
    return _memory_get(key)


async def cache_set(key: str, value: Any, ttl_seconds: int = 1800) -> None:
    if CACHE_PROVIDER == "redis":
        try:
            from upstash_redis import Redis

            url = (os.getenv("UPSTASH_REDIS_REST_URL") or "").strip()
            token = (os.getenv("UPSTASH_REDIS_REST_TOKEN") or "").strip()
            r = Redis(url=url, token=token) if url and token else Redis.from_env()
            payload = json.dumps(value) if not isinstance(value, (str, bytes)) else value
            r.set(key, payload, ex=ttl_seconds)
            cache_set_entry(key, value, ttl_seconds)
            return
        except Exception:
            cache_set_entry(key, value, ttl_seconds)
            _memory_set(key, value, ttl_seconds)
            return
    cache_prune_expired()
    cache_set_entry(key, value, ttl_seconds)
    _memory_set(key, value, ttl_seconds)
