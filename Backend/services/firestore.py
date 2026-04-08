from __future__ import annotations

import json
import os

from google.cloud import firestore as g_firestore

from .local_store import get_workflow_event, upsert_context, upsert_workflow_event


def is_firestore_enabled() -> bool:
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
    return None


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
