from __future__ import annotations

from services.firestore import read_workflow_outcomes


def load_training_rows(limit: int = 500) -> list[dict]:
    return read_workflow_outcomes(limit=limit)


def train_policy(limit: int = 500) -> dict:
    rows = load_training_rows(limit=limit)
    return {
        "status": "ready_for_offline_training",
        "rows_loaded": len(rows),
        "message": "Offline RL training scaffold is in place. Connect this to stable-baselines3 PPO in Cloud Run for production training.",
    }
