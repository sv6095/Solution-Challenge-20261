from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command, interrupt

from agents.assessment_agent import run_assessment
from agents.governance import (
    PATH_WORKFLOW,
    run_with_policy,
    validate_contract_input,
    validate_contract_output,
)
from agents.logistics_risk_agent import analyze_logistics_risk
from agents.political_risk_agent import analyze_political_risk
from agents.reasoning_logger import log_reasoning_step
from agents.rfq_agent import draft_rfq
from agents.reporting_agent import build_consolidated_report
from agents.scheduler_agent import analyze_schedule_context
from agents.supervisor_agent import build_supervisor_packet
from agents.tariff_risk_agent import analyze_tariff_risk
from agents.routing_agent import run_routing
from ml.rl_agent import recommend_mode
from services.firestore import (
    read_workflow_checkpoint,
    write_workflow_checkpoint,
    write_workflow_event,
    write_workflow_outcome,
)
from services.local_store import get_orchestration_run, upsert_orchestration_run
from workflows.state import WorkflowState


def route_after_assessment(state: WorkflowState) -> str:
    return "audit_agent" if len(state.get("affected_suppliers", [])) == 0 else "routing_agent"


def route_after_routing(state: WorkflowState) -> str:
    # Business Risk Mitigation: Never auto-send production RFQs without human vetted context.
    return "human_gate"


def route_after_human(state: WorkflowState) -> str:
    decision = str(state.get("human_decision") or "").lower()
    return "route_confirm" if decision == "reroute" else "rfq_agent"


def _decision_evidence_status(signal: dict[str, Any]) -> dict[str, Any]:
    corroboration_count = 0
    raw = signal.get("corroboration_count")
    if isinstance(raw, (int, float)):
        corroboration_count = int(raw)
    elif isinstance(signal.get("corroborated_by"), list):
        corroboration_count = len([x for x in signal.get("corroborated_by") if x])

    freshness_ok = False
    freshness_hours = None
    detected_at = signal.get("detected_at") or signal.get("timestamp") or signal.get("created_at")
    if detected_at:
        try:
            detected = datetime.fromisoformat(str(detected_at).replace("Z", "+00:00"))
            freshness_hours = (datetime.now(timezone.utc) - detected).total_seconds() / 3600.0
            freshness_ok = freshness_hours <= 24
        except Exception:
            freshness_ok = False

    return {
        "corroboration_count": corroboration_count,
        "freshness_hours": round(freshness_hours, 2) if isinstance(freshness_hours, (int, float)) else None,
        "actionable": bool(corroboration_count >= 2 and freshness_ok),
    }


class WorkflowGraphManager:
    def __init__(self) -> None:
        self.checkpointer = InMemorySaver()
        self.app = self._build_graph()

    def _config(self, workflow_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": workflow_id}}

    def _snapshot_state(self, workflow_id: str) -> dict[str, Any]:
        snapshot = self.app.get_state(self._config(workflow_id))
        values = dict(snapshot.values or {})
        values["workflow_id"] = workflow_id
        values["updated_at"] = datetime.now(timezone.utc).isoformat()
        values["next"] = list(snapshot.next or ())
        values["interrupts"] = [
            {"id": item.id, "value": item.value}
            for item in (snapshot.interrupts or ())
        ]
        write_workflow_checkpoint(workflow_id, values)
        return values

    def _build_graph(self):
        graph = StateGraph(WorkflowState)
        graph.add_node("signal_agent", self._signal_agent)
        graph.add_node("assessment_agent", self._assessment_agent)
        graph.add_node("routing_agent", self._routing_agent)
        graph.add_node("human_gate", self._human_gate)
        graph.add_node("route_confirm", self._route_confirm)
        graph.add_node("rfq_agent", self._rfq_agent)
        graph.add_node("audit_agent", self._audit_agent)
        graph.set_entry_point("signal_agent")
        graph.add_edge("signal_agent", "assessment_agent")
        graph.add_conditional_edges("assessment_agent", route_after_assessment, {"audit_agent": "audit_agent", "routing_agent": "routing_agent"})
        graph.add_conditional_edges("routing_agent", route_after_routing, {"human_gate": "human_gate", "rfq_agent": "rfq_agent"})
        graph.add_conditional_edges("human_gate", route_after_human, {"route_confirm": "route_confirm", "rfq_agent": "rfq_agent"})
        graph.add_edge("route_confirm", "audit_agent")
        graph.add_edge("rfq_agent", "audit_agent")
        graph.add_edge("audit_agent", END)
        return graph.compile(checkpointer=self.checkpointer)

    async def _signal_agent(self, state: WorkflowState) -> dict[str, Any]:
        workflow_id = str(state["workflow_id"])
        signal = state.get("selected_signal", {}) if isinstance(state.get("selected_signal"), dict) else {}
        suppliers = state.get("affected_suppliers", []) if isinstance(state.get("affected_suppliers"), list) else []
        has_geo = isinstance(signal.get("lat"), (int, float)) and isinstance(signal.get("lng"), (int, float))
        has_event = bool(str(signal.get("event_type") or signal.get("title") or "").strip())
        has_suppliers = len(suppliers) > 0
        if not (has_geo and has_event and has_suppliers):
            log_reasoning_step(
                workflow_id,
                "signal_agent",
                "detect_validation_failed",
                "DETECT validation failed: missing event, geolocation, or affected suppliers.",
                "error",
                {"has_geo": has_geo, "has_event": has_event, "has_suppliers": has_suppliers},
            )
            raise ValueError("Invalid DETECT input context")
        write_workflow_event(workflow_id, "detect", 0.5)
        log_reasoning_step(workflow_id, "signal_agent", "detect_start", "Workflow started from signal selection.", "success")
        return {"current_stage": "ASSESS", "reasoning_steps": state.get("reasoning_steps", [])}

    async def _assessment_agent(self, state: WorkflowState) -> dict[str, Any]:
        if str(state.get("current_stage") or "").upper() not in {"DETECT", "ASSESS"}:
            raise ValueError("Invalid stage transition into ASSESS")
        validate_contract_input("assessment_agent", {"selected_signal": state.get("selected_signal"), "affected_suppliers": state.get("affected_suppliers")})
        workflow_id = str(state["workflow_id"])
        assessment = run_assessment(
            workflow_id,
            str(state.get("selected_signal", {}).get("event_type") or "unknown"),
            float(state.get("selected_signal", {}).get("severity") or 0.0),
            state.get("affected_suppliers", []),
        )
        updates = {
            "current_stage": "ASSESS",
            "affected_suppliers": assessment.get("affected_suppliers", []),
            "exposure_usd": float(assessment.get("financial_exposure_usd") or 0.0),
            "exposure_local": float(assessment.get("financial_exposure_usd") or 0.0),
            "days_at_risk": int(assessment.get("days_at_risk") or 0),
            "confidence": float(assessment.get("confidence_score") or 0.0),
            "assessment_summary": f"Assessment found {len(assessment.get('affected_suppliers', []))} affected suppliers.",
            "supplier_scores": assessment.get("supplier_scores", []),
        }
        validate_contract_output("assessment_agent", {"confidence": updates.get("confidence"), "days_at_risk": updates.get("days_at_risk")})
        write_workflow_event(workflow_id, "assess", updates["confidence"])
        return updates

    async def _routing_agent(self, state: WorkflowState) -> dict[str, Any]:
        if str(state.get("current_stage") or "").upper() not in {"ASSESS", "DECIDE"}:
            raise ValueError("Invalid stage transition into DECIDE")
        validate_contract_input("routing_agent", {"selected_signal": state.get("selected_signal"), "affected_suppliers": state.get("affected_suppliers")})
        workflow_id = str(state["workflow_id"])
        schedule_context = {
            "suppliers": state.get("affected_suppliers", []),
            "signals": state.get("signals", []),
            "project_country": state.get("selected_signal", {}).get("country") or state.get("selected_signal", {}).get("location"),
            "destination_country": state.get("selected_signal", {}).get("country") or state.get("selected_signal", {}).get("location"),
        }
        scheduler = await run_with_policy(
            agent="scheduler_agent",
            path=PATH_WORKFLOW,
            fn=analyze_schedule_context,
            kwargs={"context": schedule_context, "workflow_id": workflow_id},
        )
        political = await run_with_policy(
            agent="political_risk_agent",
            path=PATH_WORKFLOW,
            fn=analyze_political_risk,
            kwargs={"scheduler_result": scheduler, "context": schedule_context, "workflow_id": workflow_id},
        )
        tariff = await run_with_policy(
            agent="tariff_risk_agent",
            path=PATH_WORKFLOW,
            fn=analyze_tariff_risk,
            kwargs={"scheduler_result": scheduler, "context": schedule_context, "workflow_id": workflow_id},
        )
        logistics = await run_with_policy(
            agent="logistics_risk_agent",
            path=PATH_WORKFLOW,
            fn=analyze_logistics_risk,
            kwargs={"scheduler_result": scheduler, "context": schedule_context, "workflow_id": workflow_id},
        )

        origin = state.get("selected_signal", {})
        target_supplier = None
        for supplier in state.get("affected_suppliers", []):
            if isinstance(supplier, dict) and isinstance(supplier.get("lat"), (int, float)) and isinstance(supplier.get("lng"), (int, float)):
                target_supplier = supplier
                break
        if target_supplier is None:
            raise ValueError("Missing destination supplier geolocation")
        routes = await run_routing(
            float(origin.get("lat") or 0.0),
            float(origin.get("lng") or 0.0),
            str(origin.get("country_code") or "US"),
            str(origin.get("location") or "Origin"),
            float(target_supplier.get("lat") or 0.0),
            float(target_supplier.get("lng") or 0.0),
            str(target_supplier.get("country_code") or target_supplier.get("country") or "US"),
            str(target_supplier.get("location") or target_supplier.get("name") or "Destination"),
            str(state.get("local_currency") or "USD"),
        )
        network_routes = state.get("network_routes") if isinstance(state.get("network_routes"), list) else []
        if network_routes:
            mode_availability = {"sea": False, "air": False, "land": False}
            for route in network_routes:
                if not isinstance(route, dict):
                    continue
                mode = str(route.get("mode") or "").strip().lower()
                if mode in mode_availability:
                    mode_availability[mode] = True
            filtered = [
                row
                for row in routes.get("route_comparison", [])
                if isinstance(row, dict) and mode_availability.get(str(row.get("mode") or "").lower(), False)
            ]
            routes["route_comparison"] = filtered
            if str(routes.get("recommended_mode") or "").lower() not in {str(r.get("mode") or "").lower() for r in filtered}:
                routes["recommended_mode"] = filtered[0].get("mode") if filtered else ""
            routes["mode_constraints"] = mode_availability
        supplier_scores = state.get("supplier_scores") if isinstance(state.get("supplier_scores"), list) else []
        top_exposure = max([float(item.get("exposure_score") or item.get("score") or 0.0) for item in supplier_scores], default=0.0)
        rl = recommend_mode(
            disruption_severity=float(origin.get("severity") or 0.0),
            supplier_exposure_score=top_exposure,
            sea_available=bool(any(str(r.get("mode") or "").lower() == "sea" for r in routes.get("route_comparison", []))),
            air_available=bool(any(str(r.get("mode") or "").lower() == "air" for r in routes.get("route_comparison", []))),
            land_available=bool(any(str(r.get("mode") or "").lower() == "land" for r in routes.get("route_comparison", []))),
            sea_cost_delta_pct=25.0,
            land_time_delta_pct=18.0,
            air_cost_usd=next(
                (
                    float(row.get("cost", {}).get("amount") or row.get("cost_usd") or 0.0)
                    for row in routes.get("route_comparison", [])
                    if isinstance(row, dict) and row.get("mode") == "air"
                ),
                0.0,
            ),
            currency_risk_index=float(routes.get("currency_risk_index") or 0.0),
            days_to_supplier_sla=float(state.get("days_at_risk") or 0.0),
        )
        supervisor = build_supervisor_packet(
            message=f"Workflow {workflow_id} decision review",
            route_plan={"needs_scheduler": True, "needs_report": True},
            packets=[scheduler.packet],
        )
        assess_conf = float(state.get("confidence") or 0.0)
        consensus_delta = abs(assess_conf - float(rl.confidence))
        consensus_required = consensus_delta >= 0.30
        evidence = _decision_evidence_status(origin if isinstance(origin, dict) else {})
        decision_actionable = bool(evidence.get("actionable") and not consensus_required)
        updates = {
            "current_stage": "DECIDE",
            "route_comparison": routes.get("route_comparison", []),
            "recommended_mode": rl.recommended_mode,
            "currency_risk_index": float(routes.get("currency_risk_index") or 0.0),
            "rl_confidence": rl.confidence,
            "specialist_packets": {
                "scheduler": scheduler.packet.to_dict(),
                "political": political.get("packet", {}),
                "tariff": tariff.get("packet", {}),
                "logistics": logistics.get("packet", {}),
            },
            "human_gate_packet": {
                "recommended_mode": rl.recommended_mode,
                "confidence": rl.confidence,
                "auto_approve_rfq": rl.auto_approve_rfq,
                "route_comparison": routes.get("route_comparison", []),
                "assessment_summary": state.get("assessment_summary", ""),
                "currency_risk_index": float(routes.get("currency_risk_index") or 0.0),
                "assessment_confidence": assess_conf,
                "consensus_delta": round(consensus_delta, 3),
                "consensus_required": consensus_required,
                "decision_actionable": decision_actionable,
                "evidence": evidence,
            },
            "decision_brief": supervisor.to_dict(),
        }
        validate_contract_output("routing_agent", {"recommended_mode": updates.get("recommended_mode"), "route_comparison": updates.get("route_comparison")})
        write_workflow_event(workflow_id, "decide", rl.confidence)
        log_reasoning_step(
            workflow_id,
            "routing_agent",
            "rl_policy_decision",
            f"Policy recommended {rl.recommended_mode} at confidence {rl.confidence:.2f}; auto RFQ {'enabled' if rl.auto_approve_rfq else 'disabled'}.",
            "success",
            {"recommended_mode": rl.recommended_mode, "confidence": rl.confidence, "auto_approve_rfq": rl.auto_approve_rfq},
        )
        if consensus_required:
            log_reasoning_step(
                workflow_id,
                "supervisor_agent",
                "consensus_arbitration",
                "Assessment and routing confidence diverged; deterministic arbitration requires explicit human resolution.",
                "fallback",
                {"assessment_confidence": assess_conf, "routing_confidence": rl.confidence, "delta": consensus_delta},
            )
        if not evidence.get("actionable"):
            log_reasoning_step(
                workflow_id,
                "supervisor_agent",
                "decision_quality_gate",
                "DECIDE output blocked from autonomous action due to insufficient corroboration/freshness evidence.",
                "fallback",
                {"evidence": evidence},
            )
        return updates

    async def _human_gate(self, state: WorkflowState) -> dict[str, Any]:
        workflow_id = str(state["workflow_id"])
        decision = interrupt(
            {
                "workflow_id": workflow_id,
                "recommended_mode": state.get("recommended_mode"),
                "rl_confidence": state.get("rl_confidence"),
                "route_comparison": state.get("route_comparison", []),
                "assessment_summary": state.get("assessment_summary", ""),
            }
        )
        log_reasoning_step(
            workflow_id,
            "routing_agent",
            "human_gate",
            "Workflow paused for mandatory human approval before ACT execution.",
            "success",
            {"rl_confidence": state.get("rl_confidence")},
        )
        decision_map = decision if isinstance(decision, dict) else {"action": decision}
        return {
            "waiting_human": False,
            "human_decision": decision_map.get("action") or "backup_supplier",
            "selected_mode": decision_map.get("mode") or state.get("recommended_mode"),
        }

    async def _route_confirm(self, state: WorkflowState) -> dict[str, Any]:
        if str(state.get("current_stage") or "").upper() not in {"DECIDE", "ACT"}:
            raise ValueError("Invalid stage transition into ACT")
        workflow_id = str(state["workflow_id"])
        write_workflow_event(workflow_id, "act", float(state.get("rl_confidence") or 0.0))
        log_reasoning_step(workflow_id, "routing_agent", "route_confirm", "Human approved reroute execution.", "success")
        return {
            "current_stage": "ACT",
            "selected_mode": state.get("selected_mode") or state.get("recommended_mode"),
            "action_state": {
                "generated": True,
                "executed": True,
                "confirmed": True,
                "channel": "human_reroute",
            },
        }

    async def _rfq_agent(self, state: WorkflowState) -> dict[str, Any]:
        if str(state.get("current_stage") or "").upper() not in {"DECIDE", "ACT"}:
            raise ValueError("Invalid stage transition into ACT")
        workflow_id = str(state["workflow_id"])
        rfq = draft_rfq(
            str(state.get("rfq_recipient") or "backup@supplier.com"),
            str(state.get("selected_signal", {}).get("title") or "Disruption event"),
            "Expedite replacement quantities",
        )
        log_reasoning_step(workflow_id, "rfq_agent", "rfq_draft", "Drafted backup supplier RFQ from workflow context.", "success")
        if str(state.get("human_decision") or "").lower() == "both":
            log_reasoning_step(workflow_id, "rfq_agent", "dual_action_rfq", "Executed dual-action path: reroute plus backup supplier RFQ.", "success")
        log_reasoning_step(
            workflow_id,
            "rfq_agent",
            "hitl_send_required",
            "External RFQ dispatch is blocked in autonomous ACT; human operator must explicitly send.",
            "fallback",
            {"channel": "draft_only"},
        )
        write_workflow_event(workflow_id, "act", float(state.get("rl_confidence") or 0.0))
        return {
            "current_stage": "ACT",
            "rfq_sent": False,
            "rfq_email_body": rfq.get("body"),
            "action_state": {
                "generated": True,
                "executed": False,
                "confirmed": True,
                "channel": "draft_only",
                "provider_status": "human_send_required",
            },
            "rfq_requires_manual_send": True,
        }

    async def _audit_agent(self, state: WorkflowState) -> dict[str, Any]:
        action_state = state.get("action_state") if isinstance(state.get("action_state"), dict) else {}
        if not bool(action_state.get("confirmed")):
            raise ValueError("Cannot complete workflow before ACT confirmation")
        workflow_id = str(state["workflow_id"])
        packets = []
        if isinstance(state.get("specialist_packets"), dict):
            packets = [packet for packet in state["specialist_packets"].values() if isinstance(packet, dict)]
        report = build_consolidated_report(
            scheduler_markdown="",
            political_markdown="",
            tariff_markdown="",
            logistics_markdown="",
            packets=packets,
            workflow_id=workflow_id,
        )
        updates = {
            "current_stage": "AUDIT",
            "response_time_seconds": float(state.get("response_time_seconds") or 480.0),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "final_report_markdown": report.get("markdown", ""),
            "compliance_frameworks": ["EU CSDDD", "US CHIPS Act", "India DPDP Bill", "ISO 28000"],
            "waiting_human": False,
        }
        final_state = {**state, **updates}
        write_workflow_event(workflow_id, "audit", float(state.get("rl_confidence") or state.get("confidence") or 0.0))
        write_workflow_outcome(workflow_id, final_state)
        log_reasoning_step(workflow_id, "audit_agent", "audit_complete", "Workflow outcome recorded and audit stage completed.", "success")
        return updates

    async def start_workflow(self, initial_state: WorkflowState) -> dict[str, Any]:
        workflow_id = str(initial_state["workflow_id"])
        run_id = f"orch_wf_{workflow_id}"
        upsert_orchestration_run(
            run_id=run_id,
            orchestration_path=PATH_WORKFLOW,
            entity_id=workflow_id,
            status="running",
            payload={"state": initial_state},
            tenant_id=str(initial_state.get("customer_id") or initial_state.get("user_id") or "default"),
        )
        state = {
            **initial_state,
            "current_stage": initial_state.get("current_stage") or "DETECT",
            "reasoning_steps": initial_state.get("reasoning_steps", []),
            "rfq_sent": bool(initial_state.get("rfq_sent", False)),
            "action_state": {
                "generated": False,
                "executed": False,
                "confirmed": False,
            },
            "waiting_human": False,
        }
        result = await self.app.ainvoke(state, config=self._config(workflow_id))
        persisted = self._snapshot_state(workflow_id)
        if result.get("__interrupt__"):
            persisted["waiting_human"] = True
            persisted["status"] = "waiting_human"
            write_workflow_checkpoint(workflow_id, persisted)
            upsert_orchestration_run(
                run_id=run_id,
                orchestration_path=PATH_WORKFLOW,
                entity_id=workflow_id,
                status="waiting_human",
                payload={"state": persisted},
                tenant_id=str(initial_state.get("customer_id") or initial_state.get("user_id") or "default"),
            )
            return {"status": "waiting_human", "workflow_id": workflow_id, "state": persisted}
        persisted["status"] = "complete"
        write_workflow_checkpoint(workflow_id, persisted)
        upsert_orchestration_run(
            run_id=run_id,
            orchestration_path=PATH_WORKFLOW,
            entity_id=workflow_id,
            status="complete",
            payload={"state": persisted},
            tenant_id=str(initial_state.get("customer_id") or initial_state.get("user_id") or "default"),
        )
        return {"status": "complete", "workflow_id": workflow_id, "state": persisted}

    async def approve_decision(self, workflow_id: str, *, action: str, mode: str | None = None) -> dict[str, Any]:
        config = self._config(workflow_id)
        state = self.app.get_state(config)
        if not state.next:
            persisted = read_workflow_checkpoint(workflow_id) or {}
            if not persisted.get("waiting_human"):
                raise ValueError(f"No paused workflow checkpoint found for {workflow_id}")
        result = await self.app.ainvoke(Command(resume={"action": action, "mode": mode}), config=config)
        persisted = self._snapshot_state(workflow_id)
        persisted["status"] = "complete"
        write_workflow_checkpoint(workflow_id, persisted)
        upsert_orchestration_run(
            run_id=f"orch_wf_{workflow_id}",
            orchestration_path=PATH_WORKFLOW,
            entity_id=workflow_id,
            status="complete",
            payload={"state": persisted},
            tenant_id=str(persisted.get("customer_id") or persisted.get("user_id") or "default"),
        )
        return {"status": "complete", "workflow_id": workflow_id, "state": persisted}

    async def replay_workflow(self, workflow_id: str, tenant_id: str | None = None) -> dict[str, Any]:
        run = get_orchestration_run(f"orch_wf_{workflow_id}", tenant_id=tenant_id)
        if not run:
            raise ValueError(f"No orchestration run found for workflow {workflow_id}")
        payload = run.get("payload") if isinstance(run.get("payload"), dict) else {}
        state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
        if not state:
            raise ValueError(f"No replayable state found for workflow {workflow_id}")
        state["workflow_id"] = workflow_id
        return await self.start_workflow(state)  # deterministic replay from last durable state
