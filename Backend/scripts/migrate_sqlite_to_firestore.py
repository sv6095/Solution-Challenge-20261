from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = BACKEND_ROOT / "local_fallback.db"


def _json(value: Any, fallback: Any = None) -> Any:
    if value is None:
        return fallback
    try:
        parsed = json.loads(value)
        return parsed if parsed is not None else fallback
    except Exception:
        return fallback


def _safe_doc_id(value: Any) -> str:
    import hashlib

    raw = str(value or "").strip()
    if raw and "/" not in raw:
        return raw
    return f"key_{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"


def _table_exists(con: sqlite3.Connection, table: str) -> bool:
    row = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return bool(row)


def _rows(con: sqlite3.Connection, table: str) -> Iterable[sqlite3.Row]:
    if not _table_exists(con, table):
        return []
    return con.execute(f"SELECT * FROM {table}").fetchall()


class _DryRunFirestore:
    def collection(self, *_args: Any, **_kwargs: Any) -> "_DryRunFirestore":
        return self

    def document(self, *_args: Any, **_kwargs: Any) -> "_DryRunFirestore":
        return self


class Migrator:
    def __init__(self, db_path: Path, dry_run: bool = True, only: set[str] | None = None) -> None:
        self.db_path = db_path
        self.dry_run = dry_run
        self.only = only or set()
        if dry_run:
            self.db = _DryRunFirestore()
        else:
            from google.cloud import firestore

            self.db = firestore.Client()
        self.counts: dict[str, int] = {}

    def enabled(self, name: str) -> bool:
        return not self.only or name in self.only

    def write(self, ref: Any, payload: dict[str, Any], domain: str) -> None:
        self.counts[domain] = self.counts.get(domain, 0) + 1
        if not self.dry_run:
            ref.set(payload, merge=True)

    def run(self) -> dict[str, int]:
        if not self.db_path.exists():
            raise FileNotFoundError(f"SQLite DB not found: {self.db_path}")
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        try:
            self.users(con)
            self.contexts(con)
            self.workflow_docs(con)
            self.rfqs(con)
            self.signals(con)
            self.audit(con)
            self.cache(con)
            self.reasoning(con)
            self.incidents(con)
            self.master_data(con)
            self.orchestration(con)
            self.graph(con)
            self.action_logs(con)
            self.governance(con)
            self.thresholds(con)
            self.idempotency(con)
            self.worldmonitor(con)
        finally:
            con.close()
        return self.counts

    def users(self, con: sqlite3.Connection) -> None:
        if not self.enabled("users"):
            return
        for r in _rows(con, "users"):
            payload = dict(r)
            self.write(self.db.collection("users").document(str(r["user_id"])), payload, "users")
            self.write(self.db.collection("user_email_index").document(_safe_doc_id(str(r["email"]).lower())), {"email": str(r["email"]).lower(), "user_id": r["user_id"]}, "user_email_index")

    def contexts(self, con: sqlite3.Connection) -> None:
        if not self.enabled("contexts"):
            return
        for r in _rows(con, "contexts"):
            payload = _json(r["payload_json"], {})
            if not isinstance(payload, dict):
                payload = {}
            payload["user_id"] = r["user_id"]
            payload["updated_at"] = r["updated_at"]
            self.write(self.db.collection("contexts").document(str(r["user_id"])), payload, "contexts")

    def workflow_docs(self, con: sqlite3.Connection) -> None:
        mapping = {
            "workflow_events": "workflow_events",
            "workflow_reports": "workflow_reports",
            "workflow_checkpoints": "workflow_checkpoints",
            "workflow_outcomes": "workflow_outcomes",
        }
        for table, collection in mapping.items():
            if not self.enabled(table):
                continue
            for r in _rows(con, table):
                payload = _json(r["payload_json"], {}) if "payload_json" in r.keys() else {}
                if not isinstance(payload, dict):
                    payload = {}
                payload.update({k: r[k] for k in r.keys() if k != "payload_json"})
                self.write(self.db.collection(collection).document(str(r["workflow_id"])), payload, table)

    def rfqs(self, con: sqlite3.Connection) -> None:
        if self.enabled("rfq_events"):
            for r in _rows(con, "rfq_events"):
                self.write(self.db.collection("rfq_events").document(str(r["rfq_id"])), dict(r), "rfq_events")
        if self.enabled("rfq_messages"):
            for r in _rows(con, "rfq_messages"):
                self.write(self.db.collection("rfq_events").document(str(r["rfq_id"])).collection("messages").document(str(r["id"])), dict(r), "rfq_messages")

    def signals(self, con: sqlite3.Connection) -> None:
        for table, collection in (("signals", "signals"), ("signals_archive", "signals_archive")):
            if not self.enabled(table):
                continue
            for r in _rows(con, table):
                payload = {"signal_id": r["signal_id"], "payload": _json(r["payload_json"], {}), "created_at": r["created_at"]}
                if "archived_at" in r.keys():
                    payload["archived_at"] = r["archived_at"]
                doc_id = _safe_doc_id(f"{r['signal_id']}_{payload.get('archived_at', '')}")
                self.write(self.db.collection(collection).document(doc_id), payload, table)

    def audit(self, con: sqlite3.Connection) -> None:
        if not self.enabled("audit_log"):
            return
        for r in _rows(con, "audit_log"):
            self.write(self.db.collection("audit_entries").document(str(r["id"])), {"id": r["id"], "action": r["action"], "payload": r["payload"], "created_at": r["created_at"], "timestamp": r["created_at"]}, "audit_log")

    def cache(self, con: sqlite3.Connection) -> None:
        if not self.enabled("cache_entries"):
            return
        for r in _rows(con, "cache_entries"):
            self.write(self.db.collection("cache_entries").document(_safe_doc_id(r["cache_key"])), {"cache_key": r["cache_key"], "payload": _json(r["payload_json"], None), "expires_at": r["expires_at"], "updated_at": r["updated_at"]}, "cache_entries")

    def reasoning(self, con: sqlite3.Connection) -> None:
        if not self.enabled("reasoning_steps"):
            return
        for r in _rows(con, "reasoning_steps"):
            payload = dict(r)
            payload["output"] = _json(r["output_json"], {})
            payload.pop("output_json", None)
            self.write(self.db.collection("workflow_events").document(str(r["workflow_id"])).collection("reasoning").document(str(r["id"])), payload, "reasoning_steps")

    def incidents(self, con: sqlite3.Connection) -> None:
        if not self.enabled("incidents"):
            return
        for r in _rows(con, "incidents"):
            tenant_id = r["tenant_id"] if "tenant_id" in r.keys() else "default"
            payload = _json(r["payload_json"], {})
            if not isinstance(payload, dict):
                payload = {}
            payload.update({"id": r["id"], "tenant_id": tenant_id, "status": r["status"], "severity": r["severity"], "created_at": r["created_at"], "updated_at": r["updated_at"]})
            self.write(self.db.collection("tenants").document(str(tenant_id)).collection("incidents").document(str(r["id"])), payload, "incidents")

    def master_data(self, con: sqlite3.Connection) -> None:
        if not self.enabled("master_data_changes"):
            return
        for r in _rows(con, "master_data_changes"):
            payload = {"id": r["id"], "user_id": r["user_id"], "change_type": r["change_type"], "payload": _json(r["payload_json"], {}), "created_at": r["created_at"]}
            self.write(self.db.collection("users").document(str(r["user_id"])).collection("master_data_changes").document(str(r["id"])), payload, "master_data_changes")

    def orchestration(self, con: sqlite3.Connection) -> None:
        if not self.enabled("orchestration_runs"):
            return
        for r in _rows(con, "orchestration_runs"):
            payload = dict(r)
            payload["payload"] = _json(r["payload_json"], {})
            payload.pop("payload_json", None)
            self.write(self.db.collection("tenants").document(str(r["tenant_id"])).collection("orchestration_runs").document(str(r["run_id"])), payload, "orchestration_runs")

    def graph(self, con: sqlite3.Connection) -> None:
        if self.enabled("graph_nodes"):
            for r in _rows(con, "graph_nodes"):
                self.write(self.db.collection("tenants").document(str(r["tenant_id"])).collection("graph_nodes").document(_safe_doc_id(r["node_id"])), dict(r), "graph_nodes")
        if self.enabled("graph_edges"):
            for r in _rows(con, "graph_edges"):
                doc_id = _safe_doc_id(f"{r['from_id']}__{r['to_id']}")
                self.write(self.db.collection("tenants").document(str(r["tenant_id"])).collection("graph_edges").document(doc_id), dict(r), "graph_edges")

    def action_logs(self, con: sqlite3.Connection) -> None:
        if self.enabled("action_logs"):
            for r in _rows(con, "action_logs"):
                payload = dict(r)
                payload["payload"] = _json(r["payload_json"], {})
                payload.pop("payload_json", None)
                self.write(self.db.collection("action_logs").document(str(r["action_id"])), payload, "action_logs")
        if self.enabled("delivery_milestones"):
            for r in _rows(con, "delivery_milestones"):
                self.write(self.db.collection("action_logs").document(str(r["action_id"])).collection("milestones").document(str(r["id"])), dict(r), "delivery_milestones")

    def governance(self, con: sqlite3.Connection) -> None:
        if self.enabled("governance_checkpoints"):
            for r in _rows(con, "governance_checkpoints"):
                self.write(self.db.collection("tenants").document(str(r["tenant_id"])).collection("governance_checkpoints").document(str(r["checkpoint_id"])), dict(r), "governance_checkpoints")
        if self.enabled("governance_feedback"):
            for r in _rows(con, "governance_feedback"):
                self.write(self.db.collection("tenants").document(str(r["tenant_id"])).collection("governance_feedback").document(str(r["feedback_id"])), dict(r), "governance_feedback")

    def thresholds(self, con: sqlite3.Connection) -> None:
        if self.enabled("tenant_thresholds"):
            for r in _rows(con, "tenant_thresholds"):
                self.write(self.db.collection("tenants").document(str(r["tenant_id"])).collection("thresholds").document(f"{r['stage']}__{r['param']}"), dict(r), "tenant_thresholds")
        if self.enabled("threshold_history"):
            for r in _rows(con, "threshold_history"):
                self.write(self.db.collection("tenants").document(str(r["tenant_id"])).collection("threshold_history").document(str(r["id"])), dict(r), "threshold_history")

    def idempotency(self, con: sqlite3.Connection) -> None:
        if not self.enabled("idempotency_keys"):
            return
        for r in _rows(con, "idempotency_keys"):
            payload = dict(r)
            payload["response"] = _json(r["response_json"], None)
            payload.pop("response_json", None)
            self.write(self.db.collection("idempotency_keys").document(_safe_doc_id(r["ikey"])), payload, "idempotency_keys")

    def worldmonitor(self, con: sqlite3.Connection) -> None:
        if not self.enabled("worldmonitor_cache"):
            return
        for r in _rows(con, "worldmonitor_cache"):
            payload = {"key": r["key"], "table_name": r["table_name"], "payload": _json(r["payload"], None), "fetched_at": r["fetched_at"]}
            self.write(self.db.collection("worldmonitor_cache").document(_safe_doc_id(r["key"])), payload, "worldmonitor_cache")


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate Backend/local_fallback.db into Firestore.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--write", action="store_true", help="Actually write documents. Default is dry-run.")
    parser.add_argument("--only", action="append", default=[], help="Restrict to a table/domain. Can be repeated.")
    args = parser.parse_args()

    migrator = Migrator(args.db, dry_run=not args.write, only=set(args.only))
    counts = migrator.run()
    mode = "WRITE" if args.write else "DRY-RUN"
    print(f"{mode} complete")
    for key in sorted(counts):
        print(f"{key}: {counts[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
