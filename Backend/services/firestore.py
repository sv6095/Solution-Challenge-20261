from __future__ import annotations

import json
import os

from google.cloud import firestore as g_firestore

from .firestore_store import (
    get_context as _get_context_row,
    get_workflow_checkpoint,
    get_workflow_event,
    insert_reasoning_step,
    list_reasoning_steps,
    list_workflow_outcomes,
    upsert_context,
    upsert_workflow_checkpoint,
    upsert_workflow_event,
    upsert_workflow_outcome,
)


def is_firestore_enabled() -> bool:
    return os.getenv("DB_PROVIDER", "firestore").strip().lower() == "firestore"


def _client() -> g_firestore.Client | None:
    if not is_firestore_enabled():
        raise RuntimeError("Firestore-only backend requires DB_PROVIDER=firestore")
    try:
        return g_firestore.Client(project=os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GCP_PROJECT_ID"))
    except Exception as exc:
        raise RuntimeError("Firestore client could not be initialized") from exc


def write_context(user_id: str, payload: dict) -> dict:
    """Persist onboarding/context updates to Firestore."""
    return upsert_context(user_id, json.dumps(payload))


def read_context(user_id: str) -> dict | None:
    row = _get_context_row(user_id)
    if not row:
        return None
    data = json.loads(row.get("payload_json") or "{}")
    if not isinstance(data, dict):
        data = {}
    data.setdefault("user_id", user_id)
    return data


def write_workflow_event(workflow_id: str, stage: str, confidence: float) -> dict:
    return upsert_workflow_event(workflow_id, stage, confidence)


def read_workflow_event(workflow_id: str) -> dict | None:
    return get_workflow_event(workflow_id)


def persist_reasoning_step(workflow_id: str, step: dict) -> None:
    """Persist workflow reasoning to Firestore."""
    insert_reasoning_step(
        workflow_id,
        str(step.get("agent") or ""),
        str(step.get("stage") or ""),
        str(step.get("detail") or ""),
        str(step.get("status") or "success"),
        step.get("output") if isinstance(step.get("output"), dict) else {},
        str(step.get("timestamp") or ""),
        int(step.get("timestamp_ms") or 0),
    )


def read_reasoning_steps(workflow_id: str, limit: int = 500) -> list[dict]:
    return list_reasoning_steps(workflow_id, limit=limit)


def write_workflow_checkpoint(workflow_id: str, payload: dict) -> dict:
    return upsert_workflow_checkpoint(workflow_id, payload)


def read_workflow_checkpoint(workflow_id: str) -> dict | None:
    return get_workflow_checkpoint(workflow_id)


def write_workflow_outcome(workflow_id: str, payload: dict) -> dict:
    return upsert_workflow_outcome(workflow_id, payload)


def read_workflow_outcomes(limit: int = 200) -> list[dict]:
    return list_workflow_outcomes(limit=limit)
