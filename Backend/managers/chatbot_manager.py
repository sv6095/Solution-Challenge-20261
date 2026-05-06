from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from uuid import uuid4

from agents.agent_definitions import ASSISTANT_AGENT, LOGISTICS_RISK_AGENT, POLITICAL_RISK_AGENT, REPORTING_AGENT, SCHEDULER_AGENT, TARIFF_RISK_AGENT
from agents.agent_protocol import AgentPacket
from agents.agent_strategies import build_agent_sequence, build_query_plan
from agents.assistant_agent import respond_as_assistant
from agents.logistics_risk_agent import analyze_logistics_risk
from agents.political_risk_agent import analyze_political_risk
from agents.reporting_agent import build_consolidated_report
from agents.scheduler_agent import analyze_schedule_context
from agents.supervisor_agent import build_supervisor_packet
from agents.tariff_risk_agent import analyze_tariff_risk
from agents.assessment_agent import run_assessment
from agents.governance import (
    PATH_CHAT,
    build_failure_record,
    run_with_policy,
    validate_agent_allowed,
    validate_contract_input,
    validate_contract_output,
)
from agents.routing_agent import run_routing
from services.firestore_store import upsert_orchestration_run


AGENT_STATUS_IDLE = "Idle"
AGENT_STATUS_RUNNING = "Running"
AGENT_STATUS_COMPLETED = "Completed"
AGENT_STATUS_FAILED = "Failed"


@dataclass
class ChatbotResult:
    conversation_id: str
    sequence: list[str]
    route: dict[str, Any]
    supervisor: dict[str, Any]
    outputs: dict[str, Any]
    final_text: str


class ChatbotManager:
    async def process_message(
        self,
        *,
        message: str,
        workflow_id: str | None = None,
        session_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> ChatbotResult:
        ctx = context or {}
        conversation_id = session_id or uuid4().hex
        run_id = f"orch_chat_{conversation_id}"
        upsert_orchestration_run(
            run_id=run_id,
            orchestration_path=PATH_CHAT,
            entity_id=workflow_id or conversation_id,
            status="running",
            payload={"message": message, "sequence": []},
        )
        plan = build_query_plan(message)
        sequence = build_agent_sequence(plan)
        outputs: dict[str, Any] = {}
        packets: list[AgentPacket] = []
        audit_log: list[dict[str, Any]] = []

        shared_state: dict[str, Any] = {
            "event_id": str(ctx.get("event_id") or ctx.get("workflow_id") or conversation_id),
            "signal": ctx.get("signal") if isinstance(ctx.get("signal"), dict) else {},
            "geo_location": ctx.get("geo_location") if isinstance(ctx.get("geo_location"), dict) else {},
            "affected_routes": [],
            "political_risk": {},
            "tariff_impact": {},
            "logistics_status": {},
            "exposure_score": None,
            "impact_level": None,
            "alternative_routes": [],
            "recommended_action": None,
            "execution_status": "running",
            "audit_log": [],
        }
        agent_statuses: dict[str, str] = {
            "supervisor_agent": AGENT_STATUS_IDLE,
            "signal_agent": AGENT_STATUS_IDLE,
            "assessment_agent": AGENT_STATUS_IDLE,
            "routing_agent": AGENT_STATUS_IDLE,
            POLITICAL_RISK_AGENT: AGENT_STATUS_IDLE,
            TARIFF_RISK_AGENT: AGENT_STATUS_IDLE,
            LOGISTICS_RISK_AGENT: AGENT_STATUS_IDLE,
            REPORTING_AGENT: AGENT_STATUS_IDLE,
            ASSISTANT_AGENT: AGENT_STATUS_IDLE,
        }

        def _log(issue: str, *, agent: str, severity: str = "info", meta: dict[str, Any] | None = None) -> None:
            entry = {"agent": agent, "severity": severity, "issue": issue, "meta": meta or {}}
            audit_log.append(entry)
            shared_state["audit_log"] = audit_log

        if sequence == [ASSISTANT_AGENT]:
            validate_agent_allowed(PATH_CHAT, ASSISTANT_AGENT)
            agent_statuses[ASSISTANT_AGENT] = AGENT_STATUS_RUNNING
            assistant = await respond_as_assistant(message, workflow_id)
            agent_statuses[ASSISTANT_AGENT] = AGENT_STATUS_COMPLETED
            outputs[ASSISTANT_AGENT] = assistant
            agent_statuses["supervisor_agent"] = AGENT_STATUS_RUNNING
            supervisor = build_supervisor_packet(message=message, route_plan=asdict(plan), packets=[])
            agent_statuses["supervisor_agent"] = AGENT_STATUS_COMPLETED
            shared_state["execution_status"] = "complete"
            upsert_orchestration_run(
                run_id=run_id,
                orchestration_path=PATH_CHAT,
                entity_id=workflow_id or conversation_id,
                status="complete",
                payload={"sequence": sequence, "agent_statuses": agent_statuses},
            )
            return ChatbotResult(
                conversation_id=conversation_id,
                sequence=sequence,
                route=asdict(plan),
                supervisor={**supervisor.to_dict(), "agent_statuses": agent_statuses},
                outputs={**outputs, "agent_statuses": agent_statuses, "shared_state": shared_state, "audit_log": audit_log},
                final_text=assistant["text"],
            )

        # Stage 1: Signal must run first (strict gate)
        agent_statuses["signal_agent"] = AGENT_STATUS_RUNNING
        signal = {}
        if isinstance(ctx.get("signal"), dict):
            signal = dict(ctx["signal"])
        elif isinstance(ctx.get("selected_signal"), dict):
            signal = dict(ctx["selected_signal"])
        elif isinstance(ctx.get("event"), dict):
            signal = dict(ctx["event"])

        if not signal:
            agent_statuses["signal_agent"] = AGENT_STATUS_FAILED
            _log("signal_missing_input", agent="signal_agent", severity="error")
            shared_state["execution_status"] = "failed"
            shared_state["signal"] = {}
            shared_state["recommended_action"] = "alert"
            upsert_orchestration_run(
                run_id=run_id,
                orchestration_path=PATH_CHAT,
                entity_id=workflow_id or conversation_id,
                status="failed",
                payload=build_failure_record(
                    workflow_or_incident_id=workflow_id or conversation_id,
                    path=PATH_CHAT,
                    agent="signal_agent",
                    error="signal_missing_input",
                    terminal=True,
                ),
            )
            return ChatbotResult(
                conversation_id=conversation_id,
                sequence=["signal_agent"],
                route=asdict(plan),
                supervisor={"recommended_path": "halt_missing_signal", "agent_statuses": agent_statuses, "global_confidence": 0.0},
                outputs={"agent_statuses": agent_statuses, "shared_state": shared_state, "audit_log": audit_log},
                final_text="Signal stage failed: missing disruption input.",
            )

        shared_state["signal"] = signal
        shared_state["geo_location"] = {
            "lat": signal.get("lat"),
            "lng": signal.get("lng"),
            "location": signal.get("location") or signal.get("region"),
        }
        agent_statuses["signal_agent"] = AGENT_STATUS_COMPLETED
        _log("signal_detected", agent="signal_agent", meta={"event_type": signal.get("event_type"), "severity": signal.get("severity")})

        scheduler_result = None
        if SCHEDULER_AGENT in sequence:
            agent_statuses[SCHEDULER_AGENT] = AGENT_STATUS_RUNNING
        if SCHEDULER_AGENT in sequence:
            scheduler_result = analyze_schedule_context(ctx, workflow_id=workflow_id)
            agent_statuses[SCHEDULER_AGENT] = AGENT_STATUS_COMPLETED
            outputs[SCHEDULER_AGENT] = {
                "summary": scheduler_result.summary,
                "equipment_items": scheduler_result.equipment_items,
                "manufacturing_locations": scheduler_result.manufacturing_locations,
                "shipping_ports": scheduler_result.shipping_ports,
                "receiving_ports": scheduler_result.receiving_ports,
                "search_query": scheduler_result.search_query,
                "markdown": scheduler_result.markdown,
            }
            packets.append(scheduler_result.packet)
            _log("scheduler_complete", agent=SCHEDULER_AGENT)

        # Stage 2: enrichment agents in parallel section (sequential execution, same stage)
        if scheduler_result and POLITICAL_RISK_AGENT in sequence:
            agent_statuses[POLITICAL_RISK_AGENT] = AGENT_STATUS_RUNNING
            try:
                outputs[POLITICAL_RISK_AGENT] = await run_with_policy(
                    agent=POLITICAL_RISK_AGENT,
                    path=PATH_CHAT,
                    fn=analyze_political_risk,
                    kwargs={"scheduler_result": scheduler_result, "context": ctx, "workflow_id": workflow_id},
                )
                agent_statuses[POLITICAL_RISK_AGENT] = AGENT_STATUS_COMPLETED
            except Exception as exc:
                _log("political_agent_failed_retrying", agent=POLITICAL_RISK_AGENT, severity="warning", meta={"error": str(exc)})
                try:
                    outputs[POLITICAL_RISK_AGENT] = await analyze_political_risk(scheduler_result, ctx, workflow_id=workflow_id)
                    agent_statuses[POLITICAL_RISK_AGENT] = AGENT_STATUS_COMPLETED
                    _log("political_agent_recovered", agent=POLITICAL_RISK_AGENT)
                except Exception as retry_exc:
                    outputs[POLITICAL_RISK_AGENT] = {"error": str(retry_exc)}
                    agent_statuses[POLITICAL_RISK_AGENT] = AGENT_STATUS_FAILED
                    _log("political_agent_failed", agent=POLITICAL_RISK_AGENT, severity="error", meta={"error": str(retry_exc)})
            if isinstance(outputs[POLITICAL_RISK_AGENT].get("packet"), dict):
                p = outputs[POLITICAL_RISK_AGENT]["packet"]
                packets.append(
                    AgentPacket(
                        agent=str(p.get("agent")),
                        confidence=float(p.get("confidence") or 0.0),
                        summary=str(p.get("summary") or ""),
                        findings=[],
                        key_metrics=p.get("key_metrics") if isinstance(p.get("key_metrics"), dict) else {},
                        markdown=str(p.get("markdown") or ""),
                        escalation_required=bool(p.get("escalation_required")),
                    )
                )
                shared_state["political_risk"] = p
        if scheduler_result and TARIFF_RISK_AGENT in sequence:
            agent_statuses[TARIFF_RISK_AGENT] = AGENT_STATUS_RUNNING
            try:
                outputs[TARIFF_RISK_AGENT] = await run_with_policy(
                    agent=TARIFF_RISK_AGENT,
                    path=PATH_CHAT,
                    fn=analyze_tariff_risk,
                    kwargs={"scheduler_result": scheduler_result, "context": ctx, "workflow_id": workflow_id},
                )
                agent_statuses[TARIFF_RISK_AGENT] = AGENT_STATUS_COMPLETED
            except Exception as exc:
                _log("tariff_agent_failed_retrying", agent=TARIFF_RISK_AGENT, severity="warning", meta={"error": str(exc)})
                try:
                    outputs[TARIFF_RISK_AGENT] = await analyze_tariff_risk(scheduler_result, ctx, workflow_id=workflow_id)
                    agent_statuses[TARIFF_RISK_AGENT] = AGENT_STATUS_COMPLETED
                    _log("tariff_agent_recovered", agent=TARIFF_RISK_AGENT)
                except Exception as retry_exc:
                    outputs[TARIFF_RISK_AGENT] = {"error": str(retry_exc)}
                    agent_statuses[TARIFF_RISK_AGENT] = AGENT_STATUS_FAILED
                    _log("tariff_agent_failed", agent=TARIFF_RISK_AGENT, severity="error", meta={"error": str(retry_exc)})
            if isinstance(outputs[TARIFF_RISK_AGENT].get("packet"), dict):
                p = outputs[TARIFF_RISK_AGENT]["packet"]
                packets.append(
                    AgentPacket(
                        agent=str(p.get("agent")),
                        confidence=float(p.get("confidence") or 0.0),
                        summary=str(p.get("summary") or ""),
                        findings=[],
                        key_metrics=p.get("key_metrics") if isinstance(p.get("key_metrics"), dict) else {},
                        markdown=str(p.get("markdown") or ""),
                        escalation_required=bool(p.get("escalation_required")),
                    )
                )
                shared_state["tariff_impact"] = p
        if scheduler_result and LOGISTICS_RISK_AGENT in sequence:
            agent_statuses[LOGISTICS_RISK_AGENT] = AGENT_STATUS_RUNNING
            try:
                outputs[LOGISTICS_RISK_AGENT] = await run_with_policy(
                    agent=LOGISTICS_RISK_AGENT,
                    path=PATH_CHAT,
                    fn=analyze_logistics_risk,
                    kwargs={"scheduler_result": scheduler_result, "context": ctx, "workflow_id": workflow_id},
                )
                agent_statuses[LOGISTICS_RISK_AGENT] = AGENT_STATUS_COMPLETED
            except Exception as exc:
                _log("logistics_agent_failed_retrying", agent=LOGISTICS_RISK_AGENT, severity="warning", meta={"error": str(exc)})
                try:
                    outputs[LOGISTICS_RISK_AGENT] = await analyze_logistics_risk(scheduler_result, ctx, workflow_id=workflow_id)
                    agent_statuses[LOGISTICS_RISK_AGENT] = AGENT_STATUS_COMPLETED
                    _log("logistics_agent_recovered", agent=LOGISTICS_RISK_AGENT)
                except Exception as retry_exc:
                    outputs[LOGISTICS_RISK_AGENT] = {"error": str(retry_exc)}
                    agent_statuses[LOGISTICS_RISK_AGENT] = AGENT_STATUS_FAILED
                    _log("logistics_agent_failed", agent=LOGISTICS_RISK_AGENT, severity="error", meta={"error": str(retry_exc)})
            if isinstance(outputs[LOGISTICS_RISK_AGENT].get("packet"), dict):
                p = outputs[LOGISTICS_RISK_AGENT]["packet"]
                packets.append(
                    AgentPacket(
                        agent=str(p.get("agent")),
                        confidence=float(p.get("confidence") or 0.0),
                        summary=str(p.get("summary") or ""),
                        findings=[],
                        key_metrics=p.get("key_metrics") if isinstance(p.get("key_metrics"), dict) else {},
                        markdown=str(p.get("markdown") or ""),
                        escalation_required=bool(p.get("escalation_required")),
                    )
                )
                shared_state["logistics_status"] = p

        # Stage 3: Assessment after enrichment
        agent_statuses["assessment_agent"] = AGENT_STATUS_RUNNING
        try:
            validate_contract_input("assessment_agent", {"selected_signal": signal, "affected_suppliers": ctx.get("suppliers", [])})
            assessment = run_assessment(
                workflow_id or conversation_id,
                str(signal.get("event_type") or "unknown"),
                float(signal.get("severity") or 0.0),
                ctx.get("suppliers") if isinstance(ctx.get("suppliers"), list) else [],
            )
            shared_state["exposure_score"] = assessment.get("confidence_score")
            shared_state["impact_level"] = assessment.get("days_at_risk")
            outputs["assessment_agent"] = assessment
            validate_contract_output("assessment_agent", {"confidence": assessment.get("confidence_score"), "days_at_risk": assessment.get("days_at_risk")})
            agent_statuses["assessment_agent"] = AGENT_STATUS_COMPLETED
        except Exception as exc:
            _log("assessment_failed_retrying", agent="assessment_agent", severity="warning", meta={"error": str(exc)})
            try:
                assessment = run_assessment(
                    workflow_id or conversation_id,
                    str(signal.get("event_type") or "unknown"),
                    float(signal.get("severity") or 0.0),
                    ctx.get("suppliers") if isinstance(ctx.get("suppliers"), list) else [],
                )
                shared_state["exposure_score"] = assessment.get("confidence_score")
                shared_state["impact_level"] = assessment.get("days_at_risk")
                outputs["assessment_agent"] = assessment
                agent_statuses["assessment_agent"] = AGENT_STATUS_COMPLETED
                _log("assessment_recovered", agent="assessment_agent")
            except Exception as retry_exc:
                outputs["assessment_agent"] = {"error": str(retry_exc)}
                agent_statuses["assessment_agent"] = AGENT_STATUS_FAILED
                _log("assessment_failed", agent="assessment_agent", severity="error", meta={"error": str(retry_exc)})

        # Stage 4: Routing after Assessment
        agent_statuses["routing_agent"] = AGENT_STATUS_RUNNING
        try:
            validate_contract_input("routing_agent", {"selected_signal": signal, "affected_suppliers": ctx.get("suppliers", [])})
            lat = float(signal.get("lat") or 0.0)
            lng = float(signal.get("lng") or 0.0)
            routing = await run_routing(
                lat,
                lng,
                str(signal.get("country_code") or "US"),
                str(signal.get("location") or "origin"),
                lat,
                lng,
                str(signal.get("country_code") or "US"),
                str(signal.get("location") or "destination"),
                str(ctx.get("target_currency") or "USD"),
            )
            outputs["routing_agent"] = routing
            validate_contract_output("routing_agent", {"recommended_mode": routing.get("recommended_mode"), "route_comparison": routing.get("route_comparison")})
            shared_state["alternative_routes"] = routing.get("route_comparison", [])
            shared_state["affected_routes"] = routing.get("route_comparison", [])
            agent_statuses["routing_agent"] = AGENT_STATUS_COMPLETED
        except Exception as exc:
            _log("routing_failed_retrying", agent="routing_agent", severity="warning", meta={"error": str(exc)})
            try:
                lat = float(signal.get("lat") or 0.0)
                lng = float(signal.get("lng") or 0.0)
                routing = await run_routing(
                    lat,
                    lng,
                    str(signal.get("country_code") or "US"),
                    str(signal.get("location") or "origin"),
                    lat,
                    lng,
                    str(signal.get("country_code") or "US"),
                    str(signal.get("location") or "destination"),
                    str(ctx.get("target_currency") or "USD"),
                )
                outputs["routing_agent"] = routing
                shared_state["alternative_routes"] = routing.get("route_comparison", [])
                shared_state["affected_routes"] = routing.get("route_comparison", [])
                agent_statuses["routing_agent"] = AGENT_STATUS_COMPLETED
                _log("routing_recovered", agent="routing_agent")
            except Exception as retry_exc:
                outputs["routing_agent"] = {"error": str(retry_exc)}
                agent_statuses["routing_agent"] = AGENT_STATUS_FAILED
                _log("routing_failed", agent="routing_agent", severity="error", meta={"error": str(retry_exc)})

        # Duplicate reasoning detection
        summaries = []
        for key in (POLITICAL_RISK_AGENT, TARIFF_RISK_AGENT, LOGISTICS_RISK_AGENT):
            if isinstance(outputs.get(key), dict):
                summaries.append(str(outputs[key].get("summary") or "").strip().lower())
        non_empty = [s for s in summaries if s]
        if len(non_empty) >= 2 and len(set(non_empty)) == 1:
            _log("duplicate_reasoning_detected", agent="supervisor_agent", severity="warning")

        # Missing shared-state fields detection
        missing_fields = [key for key, value in shared_state.items() if key != "audit_log" and value in (None, {}, [], "")]
        if missing_fields:
            _log("missing_state_fields", agent="supervisor_agent", severity="warning", meta={"fields": missing_fields})

        # Stage 5: Supervisor validates decisions
        agent_statuses["supervisor_agent"] = AGENT_STATUS_RUNNING
        supervisor = build_supervisor_packet(message=message, route_plan=asdict(plan), packets=packets)
        agent_statuses["supervisor_agent"] = AGENT_STATUS_COMPLETED
        outputs["supervisor"] = {**supervisor.to_dict(), "agent_statuses": agent_statuses}

        # Choose action with strict final action guarantee
        if agent_statuses["routing_agent"] == AGENT_STATUS_COMPLETED:
            shared_state["recommended_action"] = "reroute"
        elif agent_statuses["assessment_agent"] == AGENT_STATUS_COMPLETED:
            shared_state["recommended_action"] = "rfq"
        else:
            shared_state["recommended_action"] = "alert"

        # Stage 6: Reporting finalizes output
        if REPORTING_AGENT in sequence:
            agent_statuses[REPORTING_AGENT] = AGENT_STATUS_RUNNING
            try:
                report = build_consolidated_report(
                    scheduler_markdown=outputs.get(SCHEDULER_AGENT, {}).get("markdown"),
                    political_markdown=outputs.get(POLITICAL_RISK_AGENT, {}).get("markdown"),
                    tariff_markdown=outputs.get(TARIFF_RISK_AGENT, {}).get("markdown"),
                    logistics_markdown=outputs.get(LOGISTICS_RISK_AGENT, {}).get("markdown"),
                    packets=[
                        value["packet"]
                        for key, value in outputs.items()
                        if isinstance(value, dict) and isinstance(value.get("packet"), dict)
                    ],
                    workflow_id=workflow_id,
                )
                outputs[REPORTING_AGENT] = report
                final_text = report["markdown"]
                agent_statuses[REPORTING_AGENT] = AGENT_STATUS_COMPLETED
            except Exception as exc:
                outputs[REPORTING_AGENT] = {"error": str(exc)}
                final_text = "Reporting failed."
                agent_statuses[REPORTING_AGENT] = AGENT_STATUS_FAILED
                _log("reporting_failed", agent=REPORTING_AGENT, severity="error", meta={"error": str(exc)})
        else:
            final_text = outputs.get(SCHEDULER_AGENT, {}).get("markdown", "")

        shared_state["execution_status"] = (
            "failed" if any(status == AGENT_STATUS_FAILED for status in agent_statuses.values()) else "complete"
        )
        outputs["agent_statuses"] = agent_statuses
        outputs["shared_state"] = shared_state
        outputs["audit_log"] = audit_log
        upsert_orchestration_run(
            run_id=run_id,
            orchestration_path=PATH_CHAT,
            entity_id=workflow_id or conversation_id,
            status=shared_state["execution_status"],
            payload={"sequence": sequence, "agent_statuses": agent_statuses, "audit_log": audit_log},
        )

        return ChatbotResult(
            conversation_id=conversation_id,
            sequence=sequence,
            route=asdict(plan),
            supervisor={**supervisor.to_dict(), "agent_statuses": agent_statuses},
            outputs=outputs,
            final_text=final_text,
        )
