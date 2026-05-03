from __future__ import annotations

import json
import os

from google.cloud import firestore as g_firestore

from .local_store import (
    get_context,
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
    # DB_PROVIDER=sqlite forces local mode even if FIRESTORE_ENABLED=true (Section 2 dev stack).
    if os.getenv("DB_PROVIDER", "").strip().lower() == "sqlite":
        return False
    return os.getenv("FIRESTORE_ENABLED", "false").lower() == "true"


def _client() -> g_firestore.Client | None:
    if not is_firestore_enabled():
        return None
    try:
        return g_firestore.Client(project=os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GCP_PROJECT_ID"))
    except Exception:
        return None


def write_context(user_id: str, payload: dict) -> dict:
    """
    Persist onboarding/context updates.

    Rule: always write to local SQLite fallback (demo/offline durability),
    and additionally write to Firestore when enabled.
    """
    # Always keep a local copy for demo durability.
    local_result = upsert_context(user_id, json.dumps(payload))

    client = _client()
    if client is not None:
        client.collection("contexts").document(user_id).set(payload)
        return {"user_id": user_id, "updated_at": payload.get("updated_at", "")}

    return local_result


def read_context(user_id: str) -> dict | None:
    client = _client()
    if client is not None:
        doc = client.collection("contexts").document(user_id).get()
        if doc.exists:
            data = doc.to_dict() or {}
            data.setdefault("user_id", user_id)
            return data
    row = get_context(user_id)
    if not row:
        return None
    try:
        data = json.loads(row.get("payload_json") or "{}")
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("user_id", user_id)
    return data


def write_workflow_event(workflow_id: str, stage: str, confidence: float) -> dict:
    client = _client()
    if client is not None:
        payload = {"workflow_id": workflow_id, "stage": stage, "confidence": confidence}
        client.collection("workflow_events").document(workflow_id).set(payload, merge=True)
        return payload
    return upsert_workflow_event(workflow_id, stage, confidence)


def read_workflow_event(workflow_id: str) -> dict | None:
    client = _client()
    if client is not None:
        doc = client.collection("workflow_events").document(workflow_id).get()
        if doc.exists:
            data = doc.to_dict() or {}
            data.setdefault("workflow_id", workflow_id)
            return data
    return get_workflow_event(workflow_id)


def persist_reasoning_step(workflow_id: str, step: dict) -> None:
    """
    Production: workflow_events/{workflow_id}/reasoning/{auto_id}
    Fallback: SQLite reasoning_steps (always written for local durability when Firestore off).
    When Firestore is on, write only to Firestore to avoid duplicate streams in mixed setups.
    """
    client = _client()
    if client is not None:
        client.collection("workflow_events").document(workflow_id).collection("reasoning").add(step)
        return
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
    client = _client()
    if client is not None:
        try:
            coll = (
                client.collection("workflow_events")
                .document(workflow_id)
                .collection("reasoning")
                .order_by("timestamp_ms")
                .limit(limit)
            )
            return [doc.to_dict() or {} for doc in coll.stream()]
        except Exception:
            coll = client.collection("workflow_events").document(workflow_id).collection("reasoning").limit(limit)
            rows = [doc.to_dict() or {} for doc in coll.stream()]
            rows.sort(key=lambda d: int(d.get("timestamp_ms") or 0))
            return rows[:limit]
    return list_reasoning_steps(workflow_id, limit=limit)


def write_workflow_checkpoint(workflow_id: str, payload: dict) -> dict:
    client = _client()
    if client is not None:
        client.collection("workflow_checkpoints").document(workflow_id).set(payload, merge=True)
        return {"workflow_id": workflow_id, "updated_at": payload.get("updated_at", "")}
    return upsert_workflow_checkpoint(workflow_id, payload)


def read_workflow_checkpoint(workflow_id: str) -> dict | None:
    client = _client()
    if client is not None:
        doc = client.collection("workflow_checkpoints").document(workflow_id).get()
        if doc.exists:
            data = doc.to_dict() or {}
            data.setdefault("workflow_id", workflow_id)
            return data
    return get_workflow_checkpoint(workflow_id)


def write_workflow_outcome(workflow_id: str, payload: dict) -> dict:
    client = _client()
    if client is not None:
        client.collection("workflow_outcomes").document(workflow_id).set(payload, merge=True)
        return {"workflow_id": workflow_id, "updated_at": payload.get("updated_at", "")}
    return upsert_workflow_outcome(workflow_id, payload)


def read_workflow_outcomes(limit: int = 200) -> list[dict]:
    client = _client()
    if client is not None:
        try:
            coll = client.collection("workflow_outcomes").limit(limit)
            return [doc.to_dict() or {} for doc in coll.stream()]
        except Exception:
            return []
    return list_workflow_outcomes(limit=limit)
