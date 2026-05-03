from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from services.firestore import read_workflow_checkpoint, write_workflow_checkpoint


class FirestoreSaver:
    """
    Lightweight repo-native checkpoint helper.
    This mirrors the role a LangGraph checkpointer would play, while remaining usable
    even when the optional langgraph/firestore integration package is unavailable.
    """

    collection = "workflow_checkpoints"

    def put(self, workflow_id: str, state: dict[str, Any]) -> dict[str, Any]:
        payload = {**state, "workflow_id": workflow_id, "updated_at": datetime.now(timezone.utc).isoformat()}
        write_workflow_checkpoint(workflow_id, payload)
        return payload

    def get(self, workflow_id: str) -> dict[str, Any] | None:
        return read_workflow_checkpoint(workflow_id)
