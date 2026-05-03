from __future__ import annotations

import os
from typing import Any

from services import firestore as firestore_service


def effective_db_backend() -> str:
    """firestore when enabled by env; otherwise sqlite (local_fallback.db / contexts table)."""
    return "firestore" if firestore_service.is_firestore_enabled() else "sqlite"


class DatabaseProvider:
    """
    Single facade for persistence routing (Section 2).
    Delegates to services.firestore helpers, which already dual-write context to SQLite when needed.
    """

    @property
    def backend(self) -> str:
        return effective_db_backend()

    @property
    def auth_mode(self) -> str:
        return (os.getenv("AUTH_PROVIDER") or "local").strip().lower()

    def read_context(self, user_id: str) -> dict | None:
        return firestore_service.read_context(user_id)

    def write_context(self, user_id: str, payload: dict) -> dict:
        return firestore_service.write_context(user_id, payload)

    def write_workflow_event(self, workflow_id: str, stage: str, confidence: float) -> dict:
        return firestore_service.write_workflow_event(workflow_id, stage, confidence)

    def read_workflow_event(self, workflow_id: str) -> dict | None:
        return firestore_service.read_workflow_event(workflow_id)

    def persist_reasoning_step(self, workflow_id: str, step: dict[str, Any]) -> None:
        firestore_service.persist_reasoning_step(workflow_id, step)

    def read_reasoning_steps(self, workflow_id: str, limit: int = 500) -> list[dict]:
        return firestore_service.read_reasoning_steps(workflow_id, limit=limit)


db_provider = DatabaseProvider()
