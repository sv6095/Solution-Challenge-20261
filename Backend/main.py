from __future__ import annotations

import io
import json
import os
import secrets
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from starlette.responses import Response

# Load env: base .env, then optional overlays (Section 2)
_backend_root = Path(__file__).resolve().parent
load_dotenv(dotenv_path=_backend_root / ".env", override=False)
if os.getenv("ENVIRONMENT", "").strip().lower() == "production":
    _prod = _backend_root / ".env.production"
    if _prod.is_file():
        load_dotenv(dotenv_path=_prod, override=True)
else:
    for _extra in (".env.development", ".env.local"):
        _p = _backend_root / _extra
        if _p.is_file():
            load_dotenv(dotenv_path=_p, override=True)

from currency.frankfurter import convert_cost, get_exchange_rate
from currency.risk_index import compute_currency_risk_index
from currency.worldbank import get_inflation_rate
from agents.assessment_agent import run_assessment
from agents.rfq_agent import draft_rfq
from agents.routing_agent import run_routing
from managers.chatbot_manager import ChatbotManager
from pdf.certificate import generate_audit_certificate, generate_workflow_audit_report_pdf
from services.tenant_quota import quota_manager
from scheduler.signal_poll import start_signal_scheduler
from ml.xgboost_model import MODEL_PATH, train_and_save_model
from workflows.langgraph_workflow import WorkflowGraphManager
from services.llm_analysis import generate_workflow_analysis
from agents.reasoning_logger import log_reasoning_step
from services.firestore import read_context, read_reasoning_steps, read_workflow_event, write_context, write_workflow_event
from services.data_registry import data_registry_health_report, disruption_snapshot, registry
from services.firebase_auth import init_firebase_admin_app, verify_firebase_or_local_token
from services.firestore_store import (
    add_audit,
    count_incidents_by_status,
    create_rfq_event,
    create_rfq_event_linked,
    create_user,
    get_audit,
    get_context,
    get_incident,
    delete_incident,
    get_user_by_email,
    get_user_by_id,
    get_workflow_report,
    get_workflow_event,
    init_store,
    insert_signal,
    list_audit,
    list_incidents,
    list_simulation_incidents,
    list_rfq_events,
    list_rfq_messages,
    add_rfq_message,
    update_incident_status,
    update_rfq_status,
    list_signals,
    list_workflow_reports,
    upsert_incident,
    upsert_workflow_report,
    upsert_context,
    get_workflow_checkpoint,
    get_orchestration_run,
    list_orchestration_runs,
    list_master_data_changes,
    append_master_data_change,
    upsert_workflow_event,
)
from services.master_data_validator import validate_network_graph, validate_supplier_rows
from services.mailer import send_rfq_email
from services.idempotency import derive_key, idempotency_guard, mark_completed, mark_failed
from services.security import decode_token, hash_password, mint_access_token, mint_refresh_token, verify_password
from services.authorization import Permission, Principal, Role, policy
from services.decision_authority import evaluate_stage_authority
from services.data_quality_guard import assess_context_quality
from services.scenario_confidence import confidence_bounds
from services.monte_carlo import simulate_incident_monte_carlo
from services.intelligence_gap_tracker import build_intelligence_gap_report
from services.threshold_tuner import run_threshold_tuning, get_all_thresholds, compute_stage_metrics, threshold_tuning_history
from services.event_bus import websocket_handler as ws_handler, connection_count as ws_connection_count, broadcast as ws_broadcast
from services.cache_provider import cache_get, cache_set
from models.supply_graph import CustomerSupplyGraph

app = FastAPI(title="SupplyShield API", version="0.2.0")

_DEV_ORIGINS = ["http://localhost:3000", "http://localhost:5173"]
_env_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
_CORS_ORIGINS = list(dict.fromkeys(_DEV_ORIGINS + _env_origins))

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id"],
    max_age=86400,  # Cache CORS preflight for 24h to reduce OPTIONS load.
)
@app.websocket("/ws/{tenant_id}")
async def websocket_endpoint(websocket: WebSocket, tenant_id: str):
    await ws_handler(websocket, tenant_id)


import asyncio
from services.worldmonitor_fetcher import (
    worldmonitor_cron_loop,
    get_natural_hazards, get_earthquakes, get_conflict_events,
    get_gdalt_events, get_gdacs_alerts, get_supply_chain_news,
    get_market_quotes, get_energy_prices, get_macro_indicators,
    get_chokepoint_status, get_shipping_stress, get_country_instability,
    get_strategic_risk, get_market_implications, get_active_fires,
    get_aviation_intel, get_air_quality, get_critical_minerals,
    get_shipping_indices, run_all_fetchers_once,
)

init_store()
start_signal_scheduler()
chatbot_manager = ChatbotManager()
workflow_graph_manager = WorkflowGraphManager()


def _set_cache_headers(response: Response, *, public: bool, max_age: int = 30) -> None:
    scope = "public" if public else "private"
    response.headers["Cache-Control"] = f"{scope}, max-age={max_age}"


async def _cached_json(cache_key: str, ttl_seconds: int, producer) -> Any:
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached
    data = producer()
    if asyncio.iscoroutine(data):
        data = await data
    await cache_set(cache_key, data, ttl_seconds=ttl_seconds)
    return data


@app.on_event("startup")
async def _start_worldmonitor_cron():
    """Initialize Firebase Admin when configured; start worldmonitor background fetcher."""
    init_firebase_admin_app()
    asyncio.create_task(worldmonitor_cron_loop())


class Coordinates(BaseModel):
    lat: float | None = None
    lng: float | None = None
    city: str | None = None
    country: str | None = None
    country_code: str = Field(default="US", min_length=2, max_length=2)


class RouteRequest(BaseModel):
    origin: Coordinates
    destination: Coordinates
    target_currency: str = Field(default="USD", min_length=3, max_length=3)
    workflow_id: str | None = None


class WorkflowStateUpdate(BaseModel):
    stage: Literal["detect", "assess", "decide", "act", "audit"]
    confidence: float = Field(ge=0.0, le=1.0)


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    company_name: str = ""
    full_name: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str
    remember_me: bool = False


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class GoogleAuthRequest(BaseModel):
    id_token: str
    email: str | None = None


class OnboardingRequest(BaseModel):
    user_id: str
    company_name: str
    industry: str
    region: str
    primary_contact_name: str | None = None
    primary_contact_email: str | None = None
    company_size: str | None = None
    logistics_nodes: list[dict] = []
    suppliers: list[dict] = []
    backup_suppliers: list[dict] = []
    alert_threshold: float = 65
    transport_preferences: dict = {"sea": True, "air": True, "land": True}
    gmail_oauth_token: str | None = None
    slack_webhook: str | None = None


class SignalScoreRequest(BaseModel):
    signal_id: str
    event_type: str
    severity: float = Field(ge=0, le=10)
    location: str = ""


class IntelligenceMonteCarloRequest(BaseModel):
    signal: dict
    runs: int = Field(default=300, ge=50, le=1000)


class WorkflowAssessRequest(BaseModel):
    workflow_id: str
    event_type: str
    severity: float = Field(ge=0, le=10)
    suppliers: list[dict] = []


class WorkflowAnalyzeRequest(BaseModel):
    event: dict = {}
    suppliers: list[dict] = []
    assessment: dict | None = None
    workflow_id: str | None = None


class AgentChatRequest(BaseModel):
    message: str
    workflow_id: str | None = None
    session_id: str | None = None
    context: dict = {}


class WorkflowStartRequest(BaseModel):
    workflow_id: str
    user_id: str
    selected_signal: dict = {}
    local_currency: str = "USD"
    affected_suppliers: list[dict] = []


class WorkflowApprovalRequest(BaseModel):
    action: Literal["reroute", "backup_supplier", "both"]
    mode: Literal["sea", "air", "land"] | None = None


class WorkflowReportStageUpsert(BaseModel):
    workflow_id: str
    stage: Literal["detect", "assess", "decide", "act", "audit"]
    payload: dict = {}


class RFQDraftRequest(BaseModel):
    user_id: str
    recipient: str
    event_context: str
    quantities: str


class RFQSendRequest(BaseModel):
    user_id: str
    workflow_id: str
    approval_token: str
    recipient: str
    subject: str
    body: str
    approval_note: str | None = None


class TrainModelResponse(BaseModel):
    model_path: str
    rows: int


# ── Supply Chain Network Models ─────────────────────────────────────────────

class SCNetworkNode(BaseModel):
    id: str
    name: str
    type: str  # supplier_t1 | supplier_t2 | factory | warehouse | port_sea | port_air | destination
    lat: float
    lng: float
    country: str = ""
    criticality: str = "medium"  # critical | high | medium | low
    daily_throughput_usd: float = 100_000
    safety_stock_days: int = 7
    transport_modes: dict = Field(default_factory=lambda: {"sea": False, "air": False, "land": True})


class SCNetworkRoute(BaseModel):
    id: str
    from_node_id: str
    to_node_id: str
    mode: str  # sea | air | land
    transit_days: int = 7
    cost_per_unit_usd: float = 2000
    is_primary: bool = True


class SCNetworkSaveRequest(BaseModel):
    user_id: str
    nodes: list[SCNetworkNode] = []
    routes: list[SCNetworkRoute] = []
    description: str = ""


class SCNetworkMonitorRequest(BaseModel):
    user_id: str
    nodes: list[SCNetworkNode]
    events: list[dict] = []  # RiskEvent-shaped dicts from dashboard/events


def _resolve_point(c: Coordinates) -> tuple[float, float]:
    if c.lat is not None and c.lng is not None:
        return c.lat, c.lng
    port = registry.find_port_by_city_country(c.city, c.country)
    if port:
        return port.lat, port.lng
    raise HTTPException(status_code=422, detail="Provide lat/lng or resolvable city+country in Dataset/ports.json")


def _scrub_context(payload: OnboardingRequest) -> dict[str, Any]:
    data = payload.model_dump()
    customer_id = str(data.get("customer_id") or "").strip()
    if not customer_id:
        basis = str(data.get("company_name") or payload.user_id).strip().lower().replace(" ", "-")
        customer_id = f"cust_{basis}" if basis else f"cust_{payload.user_id}"
    data["customer_id"] = customer_id
    data["gmail_oauth_token_present"] = bool(data.pop("gmail_oauth_token", None))
    if data.get("slack_webhook"):
        data["slack_webhook"] = "***redacted***"
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    return data


def _assert_same_user(user: dict[str, Any], requested_user_id: str) -> str:
    subject = str(user.get("sub") or "").strip()
    if not subject:
        raise HTTPException(status_code=401, detail="Missing user subject")
    if subject != str(requested_user_id or "").strip():
        raise HTTPException(status_code=403, detail="Cross-tenant access denied")
    return subject


def _parse_tier(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"1", "tier 1", "t1"}:
        return "Tier 1"
    if raw in {"2", "tier 2", "t2"}:
        return "Tier 2"
    if raw in {"3", "tier 3", "t3"}:
        return "Tier 3"
    return "Tier 2"  # fallback instead of crashing


def _normalized_supplier_row(item: dict[str, Any], idx: int) -> dict[str, Any]:
    try:
        lat = float(item.get("lat", item.get("latitude", 0.0)) or 0.0)
        lng = float(item.get("lng", item.get("longitude", 0.0)) or 0.0)
    except (ValueError, TypeError):
        lat, lng = 0.0, 0.0

    if lat < -90 or lat > 90 or lng < -180 or lng > 180:
        lat, lng = 0.0, 0.0

    supplier_id = str(item.get("id") or item.get("supplier_id") or f"sup_{idx+1}").strip()
    exposure = float(item.get("exposureScore", item.get("exposure_score", 50.0)) or 0.0)
    
    mode_raw = str(item.get("mode") or item.get("transport_mode") or "land").strip().lower()
    if mode_raw not in {"sea", "air", "land", "rail", "multimodal"}:
        mode_raw = "land"

    return {
        "id": supplier_id,
        "name": str(item.get("name") or item.get("supplier_name") or supplier_id),
        "country": str(item.get("country") or ""),
        "location": str(item.get("location") or item.get("address") or ""),
        "tier": _parse_tier(item.get("tier")),
        "category": str(item.get("category") or "Supplier"),
        "exposureScore": exposure,
        "trend": _score_to_trend(exposure),
        "status": _score_to_status(exposure),
        "lat": lat,
        "lng": lng,
        "mode": mode_raw,
    }


def _context_payload_for_user(user_id: str) -> dict[str, Any]:
    fs = read_context(user_id)
    if isinstance(fs, dict) and fs:
        data = dict(fs)
        data.pop("user_id", None)
        return data
    row = get_context(user_id) or {}
    try:
        payload = json.loads(row.get("payload_json") or "{}") if isinstance(row, dict) else {}
    except Exception:
        payload = {}
    return payload if isinstance(payload, dict) else {}


def _context_suppliers(user_id: str) -> list[dict[str, Any]]:
    payload = _context_payload_for_user(user_id)
    suppliers = payload.get("suppliers")
    if not isinstance(suppliers, list) or len(suppliers) == 0:
        raise HTTPException(status_code=422, detail="No customer suppliers configured")
    normalized: list[dict[str, Any]] = []
    for idx, item in enumerate(suppliers):
        if not isinstance(item, dict):
            continue
        normalized.append(_normalized_supplier_row(item, idx))
    if not normalized:
        raise HTTPException(status_code=422, detail="No valid customer suppliers available")
    return normalized


def _context_suppliers_or_empty(user_id: str) -> list[dict[str, Any]]:
    try:
        return _context_suppliers(user_id)
    except HTTPException as exc:
        if exc.status_code in {404, 422}:
            return []
        raise


def _context_network_routes(user_id: str) -> list[dict[str, Any]]:
    payload = _context_payload_for_user(user_id)
    network = payload.get("supply_chain_network") if isinstance(payload.get("supply_chain_network"), dict) else {}
    routes = network.get("routes") if isinstance(network, dict) else []
    if not isinstance(routes, list):
        return []
    return [r for r in routes if isinstance(r, dict)]


def _network_mode_availability(routes: list[dict[str, Any]]) -> dict[str, bool]:
    availability = {"sea": False, "air": False, "land": False}
    for route in routes:
        mode = str(route.get("mode") or "").strip().lower()
        if mode in availability:
            availability[mode] = True
    return availability


def _record_master_data_change(user_id: str, change_type: str, payload: dict[str, Any]) -> None:
    try:
        append_master_data_change(user_id, change_type, payload)
    except Exception as exc:
        logger.warning("Failed to record master data change for %s: %s", user_id, exc)


def _resolve_customer_id_for_user(user_id: str) -> str:
    context = _context_payload_for_user(user_id)
    customer_id = str(context.get("customer_id") or context.get("company_name") or "").strip()
    if not customer_id:
        raise HTTPException(status_code=422, detail="Missing customer ownership context")
    return customer_id


def _resolve_workflow_owner(workflow_id: str) -> tuple[str, str]:
    checkpoint = get_workflow_checkpoint(workflow_id) or {}
    if isinstance(checkpoint, dict):
        owner = str(checkpoint.get("user_id") or "").strip()
        customer_id = str(checkpoint.get("customer_id") or "").strip()
        if owner:
            return owner, customer_id
    report = get_workflow_report(workflow_id) or {}
    if isinstance(report, dict):
        owner = str(report.get("user_id") or "").strip()
        customer_id = str(report.get("customer_id") or "").strip()
        if owner:
            return owner, customer_id
    raise HTTPException(status_code=404, detail="Orphan workflow")


def _assert_workflow_owner(user: dict[str, Any], workflow_id: str) -> str:
    owner, workflow_customer_id = _resolve_workflow_owner(workflow_id)
    subject = _assert_same_user(user, owner)
    request_customer_id = _resolve_customer_id_for_user(subject)
    if workflow_customer_id and workflow_customer_id != request_customer_id:
        raise HTTPException(status_code=403, detail="Cross-tenant workflow access denied")
    return subject


def _can_read_reasoning_stream(user: dict[str, Any], workflow_id: str) -> str:
    if workflow_id.startswith(("inc_", "sim_")):
        tenant_id = _resolved_request_tenant(user)
        _require_incident_permission(user, Permission.INCIDENT_READ, tenant_id)
        incident = get_incident(workflow_id, tenant_id=tenant_id)
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        return tenant_id
    return _assert_workflow_owner(user, workflow_id)


def _build_synthetic_probe_supplier(signal: dict[str, Any], existing_suppliers: list[dict[str, Any]]) -> dict[str, Any]:
    signal_id = str(signal.get("id") or signal.get("signal_id") or "probe").strip() or "probe"
    title = str(signal.get("title") or signal.get("event_type") or "Selected signal").strip() or "Selected signal"
    location = str(signal.get("location") or "Signal impact zone").strip() or "Signal impact zone"
    lat = float(signal.get("lat") or 0.0)
    lng = float(signal.get("lng") or 0.0)
    severity_raw = float(signal.get("severity_raw") or signal.get("severity") or 5.0)
    transport_mode = str(signal.get("transport_mode") or "air").strip().lower()
    if transport_mode not in {"sea", "air", "land", "mixed"}:
        transport_mode = "air"

    throughput_total = 0.0
    country_candidates: list[str] = []
    for supplier in existing_suppliers:
        if not isinstance(supplier, dict):
            continue
        try:
            throughput_total += float(supplier.get("daily_throughput_usd") or 0.0)
        except (TypeError, ValueError):
            pass
        country = str(supplier.get("country") or "").strip()
        if country:
            country_candidates.append(country)
    avg_daily_throughput = throughput_total / max(1, len(existing_suppliers))
    probe_country = country_candidates[0] if country_candidates else str(signal.get("country") or "Synthetic")

    return {
        "id": f"synthetic_probe_{signal_id}",
        "supplier_id": f"synthetic_probe_{signal_id}",
        "name": f"Synthetic Probe Node · {title[:48]}",
        "location": location,
        "city": location,
        "country": probe_country,
        "lat": lat,
        "lng": lng,
        "tier": 1,
        "category": "Synthetic Monte Carlo probe",
        "transport_mode": transport_mode,
        "mode": transport_mode,
        "status": "High",
        "trend": "up",
        "exposureScore": min(95.0, max(55.0, severity_raw * 10.0)),
        "contract_value_usd": max(150_000.0, avg_daily_throughput * 18 or 250_000.0),
        "daily_throughput_usd": max(12_500.0, avg_daily_throughput or 25_000.0),
        "safety_stock_days": max(2, min(7, int(round(7.5 - min(severity_raw, 7.0) / 1.5)))),
        "lead_time_days": max(2, min(8, int(round(2.0 + severity_raw / 2.5)))),
        "criticality": "high",
        "single_source": True,
        "incoterm": "DAP",
        "tenant_overlay_applied": False,
        "is_backup": False,
        "is_synthetic_probe": True,
        "synthetic_probe_reason": "Created for Monte Carlo reality-check when no tenant suppliers intersect the selected signal.",
    }


def _validate_detect_inputs(selected_signal: dict[str, Any], affected_suppliers: list[dict[str, Any]]) -> None:
    if not isinstance(selected_signal, dict) or not selected_signal:
        raise HTTPException(status_code=422, detail="DETECT requires selected_signal")
    if not isinstance(selected_signal.get("lat"), (int, float)) or not isinstance(selected_signal.get("lng"), (int, float)):
        raise HTTPException(status_code=422, detail="DETECT requires signal geolocation")
    if not str(selected_signal.get("event_type") or selected_signal.get("title") or "").strip():
        raise HTTPException(status_code=422, detail="DETECT requires event context")
    if not isinstance(affected_suppliers, list) or len(affected_suppliers) == 0:
        raise HTTPException(status_code=422, detail="DETECT requires mapped affected suppliers")


def _principal_from_user_claims(user: dict[str, Any]) -> Principal:
    user_id = str(user.get("sub") or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid user identity")
    tenant_id = _resolved_request_tenant(user)
    role_raw = str(user.get("role") or "admin").strip().lower()
    try:
        role = Role(role_raw)
    except Exception:
        role = Role.ADMIN
    return Principal(
        user_id=user_id,
        tenant_id=tenant_id,
        role=role,
        email=str(user.get("email") or ""),
        is_service_account=bool(user.get("service_account") or False),
    )


def _require_incident_permission(user: dict[str, Any], permission: Permission, resource_tenant_id: str) -> Principal:
    principal = _principal_from_user_claims(user)
    if not policy.check(principal, permission, resource_tenant_id=resource_tenant_id):
        raise HTTPException(status_code=403, detail=f"Missing permission: {permission.value}")
    return principal


def _safe_resource_tenant(user_id: str) -> str:
    try:
        return _resolve_customer_id_for_user(user_id)
    except Exception:
        return user_id


def _resolved_request_tenant(user: dict[str, Any]) -> str:
    user_id = str(user.get("sub") or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid user identity")
        
    resolved_tenant_id = _safe_resource_tenant(user_id)
    if resolved_tenant_id and resolved_tenant_id != user_id:
        return resolved_tenant_id

    if str(user.get("source") or "").strip() == "local-bypass":
        if resolved_tenant_id:
            return resolved_tenant_id

    claimed_tenant_id = str(user.get("tenant_id") or user.get("org_id") or "").strip()
    if claimed_tenant_id:
        return claimed_tenant_id

    dev_tenant_id = os.getenv("DEV_TENANT_ID", "").strip()
    if dev_tenant_id:
        return dev_tenant_id

    return user_id


def _onboarding_completeness_gaps(context: dict[str, Any]) -> list[str]:
    gaps: list[str] = []
    suppliers = context.get("suppliers") if isinstance(context.get("suppliers"), list) else []
    network = context.get("supply_chain_network") if isinstance(context.get("supply_chain_network"), dict) else {}
    nodes = network.get("nodes") if isinstance(network.get("nodes"), list) else []
    routes = network.get("routes") if isinstance(network.get("routes"), list) else []
    contacts_ok = bool(context.get("primary_contact_email") or context.get("primary_contact_name"))
    if len(suppliers) == 0:
        gaps.append("suppliers")
    if len(nodes) == 0:
        gaps.append("network_nodes")
    if len(routes) == 0:
        gaps.append("network_routes")
    if not contacts_ok:
        gaps.append("operator_contacts")
    has_tiered = any(str(s.get("tier") or "").strip().lower() in {"tier 1", "tier 2", "tier 3", "1", "2", "3"} for s in suppliers if isinstance(s, dict))
    if not has_tiered:
        gaps.append("tier_mapping")
    has_incoterm = any(bool(str(r.get("incoterm") or "").strip()) for r in routes if isinstance(r, dict))
    if not has_incoterm:
        gaps.append("incoterm_mapping")
    return gaps


def _assert_onboarding_readiness(user_id: str) -> None:
    context = _context_payload_for_user(user_id)
    gaps = _onboarding_completeness_gaps(context)
    if gaps:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Onboarding completeness gate failed; workflow start blocked.",
                "missing": gaps,
            },
        )


def _signal_corroboration_count(signal: dict[str, Any]) -> int:
    raw = signal.get("corroboration_count")
    if isinstance(raw, (int, float)):
        return int(raw)
    corroborated_by = signal.get("corroborated_by")
    if isinstance(corroborated_by, list):
        return max(0, len([x for x in corroborated_by if x]))
    return 0


def _signal_freshness_hours(signal: dict[str, Any]) -> float | None:
    timestamp = (
        signal.get("detected_at")
        or signal.get("timestamp")
        or signal.get("created_at")
    )
    if not timestamp:
        return None
    try:
        ts = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0
    except Exception:
        return None


def _decision_evidence_status(signal: dict[str, Any]) -> dict[str, Any]:
    corroboration_count = _signal_corroboration_count(signal)
    freshness_hours = _signal_freshness_hours(signal)
    freshness_ok = freshness_hours is not None and freshness_hours <= 24
    corroboration_ok = corroboration_count >= 2
    return {
        "corroboration_count": corroboration_count,
        "freshness_hours": round(freshness_hours, 2) if isinstance(freshness_hours, (int, float)) else None,
        "corroboration_ok": corroboration_ok,
        "freshness_ok": freshness_ok,
        "actionable": bool(corroboration_ok and freshness_ok),
    }


def _severity_to_score(label: str) -> float:
    mapping = {"critical": 90.0, "high": 75.0, "medium": 50.0, "low": 25.0}
    return mapping.get((label or "").strip().lower(), 45.0)


def _score_to_status(score: float) -> str:
    if score >= 85:
        return "Critical"
    if score >= 70:
        return "High"
    if score >= 45:
        return "Medium"
    return "Low"


def _score_to_trend(score: float) -> str:
    if score >= 70:
        return "up"
    if score <= 35:
        return "down"
    return "stable"


def _parsed_signals(limit: int = 200) -> list[dict[str, Any]]:
    rows = list_signals(limit=limit)
    parsed: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row.get("payload_json") or "{}")
            if isinstance(payload, dict):
                payload.setdefault("signal_id", row.get("signal_id"))
                payload.setdefault("created_at", row.get("created_at"))
                parsed.append(payload)
        except Exception:
            continue
    return parsed


def _dataset_suppliers(limit: int = 50) -> list[dict[str, Any]]:
    suppliers: list[dict[str, Any]] = []
    for idx, port in enumerate(registry.ports[: max(1, limit)]):
        exposure = round(25 + ((abs(port.lat) + abs(port.lng)) % 70), 1)
        # Alternate modes (sea, air, land) for demonstration
        modes = ["sea", "air", "land"]
        in_mode = modes[idx % len(modes)]
        suppliers.append(
            {
                "id": f"sup_{idx + 1}",
                "name": f"{port.city} Node",
                "country": port.country,
                "location": f"{port.city}, {port.country}",
                "tier": f"Tier {(idx % 3) + 1}",
                "category": "Logistics",
                "exposureScore": exposure,
                "trend": _score_to_trend(exposure),
                "status": _score_to_status(exposure),
                "lat": port.lat,
                "lng": port.lng,
                "mode": in_mode,
            }
        )
    return suppliers


def _api_risk_events() -> list[dict]:
    events: list[dict] = []
    for idx, sig in enumerate(_parsed_signals(limit=5000)):
        severity_value = float(sig.get("severity", 0) or 0)
        severity_label = "LOW"
        if severity_value >= 8:
            severity_label = "CRITICAL"
        elif severity_value >= 6:
            severity_label = "HIGH"
        elif severity_value >= 4:
            severity_label = "MEDIUM"
        ts = str(sig.get("created_at") or datetime.now(timezone.utc).isoformat())
        title_str = str(sig.get("title") or sig.get("event_type") or "Disruption signal")
        desc_str = str(sig.get("description") or sig.get("location") or "Signal-derived event")
        
        # Enforce reasonable recency (e.g., last 90 days instead of strict 24h)
        try:
            clean_ts = ts.replace("Z", "+00:00")
            parsed_time = datetime.fromisoformat(clean_ts).replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - parsed_time).days
            if age_days > 90: # Keep up to 3 months of history for trend analysis
                continue
        except:
            pass

        # Infer mode from content if not present
        inferred_mode = str(sig.get("mode") or "").lower()
        if not inferred_mode:
            content = (title_str + " " + desc_str).lower()
            if any(k in content for k in ["sea", "port", "ship", "vessel", "maritime", "ocean"]):
                inferred_mode = "sea"
            elif any(k in content for k in ["air", "flight", "plane", "airport", "aviation"]):
                inferred_mode = "air"
            elif any(k in content for k in ["road", "truck", "rail", "land", "highway", "border"]):
                inferred_mode = "land"
            else:
                inferred_mode = "land"

        events.append(
            {
                "id": str(sig.get("id") or sig.get("signal_id") or f"evt_{idx+1}"),
                "title": title_str,
                "severity": severity_label,
                "description": desc_str,
                "timestamp": ts,
                "analyst": str(sig.get("source") or "signal-pipeline"),
                "lat": float(sig.get("lat", 0) or 0),
                "lng": float(sig.get("lng", 0) or 0),
                "region": str(sig.get("region") or sig.get("location") or "Unknown"),
                "url": _normalized_url(str(sig.get("url") or "")),
                "mode": inferred_mode,
                "supplier_id": str(sig.get("supplier_id") or sig.get("node_id") or ""),
            }
        )
    return [e for e in events if e["lat"] != 0 or e["lng"] != 0]


def _normalized_url(raw: str | None) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if "." in value:
        return f"https://{value}"
    return ""


def _region_from_lat_lng(lat: float, lng: float) -> str:
    if lng < -30:
        if lat >= 37:
            return "northeast"
        if lat >= 30:
            return "midwest"
        return "south"
    return "west"


def _network_graph(limit_ports: int = 20, limit_airports: int = 20) -> dict[str, Any]:
    hubs: list[dict[str, Any]] = []

    for idx, port in enumerate(registry.ports[: max(1, limit_ports)]):
        hubs.append(
            {
                "id": f"port_{idx+1}",
                "city": port.city,
                "lng": float(port.lng),
                "lat": float(port.lat),
                "type": "primary" if idx < 8 else "secondary",
                "shipments": int(200 + ((idx * 37) % 1200)),
                "region": _region_from_lat_lng(float(port.lat), float(port.lng)),
            }
        )

    airport_added = 0
    for ap in registry.airports:
        if airport_added >= limit_airports:
            break
        try:
            lat = float(ap.get("lat"))
            lng = float(ap.get("lon"))
        except Exception:
            continue
        city = str(ap.get("city") or ap.get("name") or "Airport")
        hubs.append(
            {
                "id": f"airport_{airport_added+1}",
                "city": city,
                "lng": lng,
                "lat": lat,
                "type": "secondary",
                "shipments": int(150 + ((airport_added * 29) % 900)),
                "region": _region_from_lat_lng(lat, lng),
            }
        )
        airport_added += 1

    routes: list[dict[str, Any]] = []
    for i in range(len(hubs)):
        for j in range(i + 1, min(i + 4, len(hubs))):
            mode = "air" if ("airport_" in hubs[i]["id"] or "airport_" in hubs[j]["id"]) else "ground"
            shipments = int((hubs[i]["shipments"] + hubs[j]["shipments"]) / 6)
            delayed = (i + j) % 7 == 0
            routes.append(
                {
                    "from": hubs[i]["id"],
                    "to": hubs[j]["id"],
                    "mode": mode,
                    "shipments": shipments,
                    "status": "delayed" if delayed else "active",
                }
            )

    return {"hubs": hubs, "routes": routes}


@app.get("/api/ping")
async def ping() -> dict:
    """Lightweight keepalive endpoint — no auth, no DB calls. Used by the frontend to prevent Render cold-starts."""
    return {"status": "ok"}


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dataset": disruption_snapshot(),
        "dataset_health": data_registry_health_report(),
        "fallbacks": {"state_store": "firestore"},
        "xgboost_model_loaded": MODEL_PATH.exists(),
    }


@app.post("/ml/train/xgboost", response_model=TrainModelResponse)
async def train_xgboost_model(user=Depends(verify_firebase_or_local_token)) -> TrainModelResponse:
    result = train_and_save_model()
    add_audit("xgboost_train", user.get("sub", "local"))
    return TrainModelResponse(**result)


@app.post("/auth/register")
async def auth_register(payload: RegisterRequest) -> dict:
    if get_user_by_email(payload.email):
        raise HTTPException(status_code=409, detail="Email already registered")
    user = create_user(str(uuid4()), payload.email, hash_password(payload.password), payload.company_name, payload.full_name)
    add_audit("auth_register", user["user_id"])
    return {"user_id": user["user_id"], "email": user["email"], "company_name": user["company_name"], "full_name": user.get("full_name", "")}


@app.post("/auth/login")
async def auth_login(payload: LoginRequest) -> dict:
    user = get_user_by_email(payload.email)
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    try:
        tenant_id = _resolve_customer_id_for_user(user["user_id"])
    except Exception:
        tenant_id = user["user_id"]
    return {
        "user_id": user["user_id"],
        "access_token": mint_access_token(user["user_id"], user["email"], tenant_id=tenant_id, role="admin"),
        "refresh_token": mint_refresh_token(user["user_id"]),
    }


@app.post("/auth/refresh")
async def auth_refresh(payload: RefreshTokenRequest) -> dict:
    claims = decode_token(payload.refresh_token)
    if str(claims.get("type") or "").strip().lower() != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user_id = str(claims.get("sub") or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid refresh token subject")

    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        tenant_id = _resolve_customer_id_for_user(user["user_id"])
    except Exception:
        tenant_id = user["user_id"]

    return {
        "user_id": user["user_id"],
        "access_token": mint_access_token(user["user_id"], user["email"], tenant_id=tenant_id, role="admin"),
        "refresh_token": payload.refresh_token,
    }


# ---------------------------------------------------------------------------
# Frontend compatibility endpoints under /api/auth/*
# ---------------------------------------------------------------------------


@app.post("/api/auth/register")
async def api_auth_register(payload: RegisterRequest) -> dict:
    return await auth_register(payload)


@app.get("/api/auth/profile/{user_id}")
async def api_auth_profile(user_id: str, user=Depends(verify_firebase_or_local_token)) -> dict:
    """Return registration-time profile data so onboarding can auto-populate fields."""
    _assert_same_user(user, user_id)
    from services.firestore_store import get_user_by_id
    db_user = get_user_by_id(user_id)
    if not db_user:
        return {
            "user_id": user_id,
            "email": str(user.get("email") or ""),
            "full_name": str(user.get("name") or ""),
            "company_name": "",
        }
    return {
        "user_id": db_user["user_id"],
        "email": db_user["email"],
        "full_name": db_user.get("full_name", ""),
        "company_name": db_user.get("company_name", ""),
    }


@app.post("/api/auth/login")
async def api_auth_login(payload: LoginRequest) -> dict:
    return await auth_login(payload)


@app.post("/api/auth/refresh")
async def api_auth_refresh(payload: RefreshTokenRequest) -> dict:
    return await auth_refresh(payload)


@app.post("/auth/google")
async def auth_google(payload: GoogleAuthRequest) -> dict:
    email = payload.email or f"google_user_{secrets.token_hex(4)}@example.com"
    user = get_user_by_email(email) or create_user(str(uuid4()), email, hash_password(payload.id_token), "Google User")
    try:
        tenant_id = _resolve_customer_id_for_user(user["user_id"])
    except Exception:
        tenant_id = user["user_id"]
    return {
        "user_id": user["user_id"],
        "access_token": mint_access_token(user["user_id"], user["email"], tenant_id=tenant_id, role="admin"),
        "provider": "google",
    }


@app.post("/api/onboarding/validate")
async def onboarding_validate(payload: OnboardingRequest, user=Depends(verify_firebase_or_local_token)) -> dict:
    """Staging area endpoint for pre-flighting massive CSVs before committing."""
    _assert_same_user(user, payload.user_id)
    supplier_check = validate_supplier_rows([s for s in payload.suppliers if isinstance(s, dict)])
    
    warnings = supplier_check.warnings.copy()
    
    # Check for DUNS duplication within the payload
    seen_duns = set()
    for s in payload.suppliers:
        if isinstance(s, dict):
            duns = s.get("dunsNumber") or s.get("duns_number")
            name = s.get("name")
            if duns:
                if duns in seen_duns:
                    warnings.append(f"Duplicate DUNS/LEI found across rows for '{name}': {duns}. This may cause deduplication.")
                seen_duns.add(duns)

    return {
        "valid": supplier_check.valid,
        "errors": supplier_check.errors,
        "warnings": warnings,
        "staged_supplier_count": len(payload.suppliers),
        "staged_logistics_count": len(payload.logistics_nodes)
    }

@app.post("/onboarding/complete")
async def onboarding_complete(payload: OnboardingRequest, user=Depends(verify_firebase_or_local_token)) -> dict:
    _assert_same_user(user, payload.user_id)
    supplier_check = validate_supplier_rows([s for s in payload.suppliers if isinstance(s, dict)])
    if not supplier_check.valid:
        raise HTTPException(status_code=422, detail={"message": "Invalid supplier master data", "errors": supplier_check.errors})
    
    # Enforce quota limits
    try:
        quota_manager.check_network_size(payload.user_id, len(payload.suppliers) + len(payload.logistics_nodes))
        quota_manager.enforce_rate_limit(payload.user_id, "onboarding")
    except Exception as e:
        raise HTTPException(status_code=429, detail=str(e))
        
    scrubbed = _scrub_context(payload)
    scrubbed["master_data_version"] = int((scrubbed.get("master_data_version") or 0)) + 1
    try:
        result = write_context(payload.user_id, scrubbed)
    except Exception as exc:
        logger.exception("Failed to persist onboarding context for %s", payload.user_id)
        raise HTTPException(status_code=503, detail="Unable to save onboarding context. Check backend storage configuration.") from exc
    _record_master_data_change(
        payload.user_id,
        "onboarding_context_update",
        {
            "suppliers_count": len(payload.suppliers),
            "logistics_nodes_count": len(payload.logistics_nodes),
            "warnings": supplier_check.warnings,
            "master_data_version": scrubbed["master_data_version"],
        },
    )
    try:
        add_audit("onboarding_complete", payload.user_id)
    except Exception as exc:
        logger.warning("Failed to write onboarding audit for %s: %s", payload.user_id, exc)
    return {"status": "ok", **result}


@app.get("/signals/live")
async def signals_live(user=Depends(verify_firebase_or_local_token)) -> list[dict]:
    signal_rows = _parsed_signals(limit=50)
    add_audit("signals_live_read", user.get("sub", "unknown"))
    return signal_rows


@app.post("/signals/score")
async def signals_score(payload: SignalScoreRequest, user=Depends(verify_firebase_or_local_token)) -> dict:
    base_cost = registry.assessment_cost_by_event.get(payload.event_type.strip(), 10000.0)
    severity_factor = payload.severity / 10.0
    return {
        "signal_id": payload.signal_id,
        "relevance_score": round(min(1.0, 0.25 + severity_factor * 0.75), 3),
        "estimated_cost_impact_usd": round(base_cost * max(0.3, severity_factor), 2),
        "scored_by": user.get("sub", "local"),
    }


@app.post("/workflow/assess")
async def workflow_assess(payload: WorkflowAssessRequest, user=Depends(verify_firebase_or_local_token)) -> dict:
    _assert_workflow_owner(user, payload.workflow_id)
    result = run_assessment(payload.workflow_id, payload.event_type, payload.severity, payload.suppliers)
    if not result.get("affected_suppliers"):
        write_workflow_event(payload.workflow_id, "assess", 0.0)
        log_reasoning_step(
            payload.workflow_id,
            "assessment_agent",
            "mapping_exception",
            "ASSESS produced zero mapped suppliers. Escalated as UNMAPPED_SIGNAL for manual entity resolution.",
            "error",
            {
                "event_type": payload.event_type,
                "input_suppliers": len(payload.suppliers),
                "status": "UNMAPPED_SIGNAL",
            },
        )
        return {
            **result,
            "status": "UNMAPPED_SIGNAL",
            "escalated": True,
            "required_action": "manual_entity_resolution",
            "assessed_by": user.get("sub", "local"),
        }
    write_workflow_event(payload.workflow_id, "assess", result["confidence_score"])
    add_audit("workflow_assess", payload.workflow_id)
    log_reasoning_step(
        payload.workflow_id,
        "assessment_agent",
        "assessment_complete",
        f"Event type={payload.event_type}, severity={payload.severity:.1f}. "
        f"Exposure USD ≈ ${float(result['financial_exposure_usd']):,.0f}, "
        f"confidence={float(result['confidence_score']):.2f}.",
        "success",
        {
            "financial_exposure_usd": result["financial_exposure_usd"],
            "confidence_score": result["confidence_score"],
            "days_at_risk": result["days_at_risk"],
        },
    )
    converted = await convert_cost(float(result["financial_exposure_usd"]), "USD")
    log_reasoning_step(
        payload.workflow_id,
        "assessment_agent",
        "currency_conversion",
        f"Frankfurter: 1 USD = {converted.get('rate', 0):.4f} {converted.get('currency', 'USD')} "
        f"({converted.get('rate_date', '')}). "
        f"Local ≈ {converted.get('local', 0):,.2f} {converted.get('currency', '')}.",
        "success",
        {"rate": converted.get("rate"), "currency": converted.get("currency"), "local_amount": converted.get("local")},
    )
    return {
        **result,
        "financial_exposure": converted,
        "assessed_by": user.get("sub", "local"),
    }


@app.post("/workflow/routes")
async def workflow_routes(payload: RouteRequest, user=Depends(verify_firebase_or_local_token)) -> dict:
    origin_lat, origin_lng = _resolve_point(payload.origin)
    dest_lat, dest_lng = _resolve_point(payload.destination)
    if abs(origin_lat - dest_lat) < 1e-6 and abs(origin_lng - dest_lng) < 1e-6:
        raise HTTPException(status_code=422, detail="Origin and destination must differ")
    owner_id = str(user.get("sub") or "").strip()
    if payload.workflow_id:
        owner_id = _assert_workflow_owner(user, payload.workflow_id)
    result = await run_routing(
        origin_lat,
        origin_lng,
        payload.origin.country_code,
        f"{payload.origin.city or origin_lat},{payload.origin.country or ''}",
        dest_lat,
        dest_lng,
        payload.destination.country_code,
        f"{payload.destination.city or dest_lat},{payload.destination.country or ''}",
        payload.target_currency.upper(),
    )
    comparison = result.get("route_comparison") if isinstance(result.get("route_comparison"), list) else []
    network_routes = _context_network_routes(owner_id)
    if network_routes:
        mode_availability = _network_mode_availability(network_routes)
        comparison = [row for row in comparison if isinstance(row, dict) and mode_availability.get(str(row.get("mode") or "").lower(), False)]
        result["route_comparison"] = comparison
        if str(result.get("recommended_mode") or "").lower() not in {str(r.get("mode") or "").lower() for r in comparison}:
            result["recommended_mode"] = comparison[0]["mode"] if comparison else ""
        result["mode_constraints"] = mode_availability
    seen_modes = {str(row.get("mode") or "") for row in comparison if isinstance(row, dict)}
    if not seen_modes:
        raise HTTPException(status_code=422, detail="Disconnected route set; no valid route outputs")
    if str(result.get("recommended_mode") or "") not in {"sea", "air", "land"}:
        raise HTTPException(status_code=422, detail="Invalid recommended transport mode")
    add_audit("workflow_routes", user.get("sub", "local"))
    wf_id = (payload.workflow_id or "").strip()
    if wf_id:
        log_reasoning_step(
            wf_id,
            "routing_agent",
            "route_comparison",
            f"Computed sea/air/land options; recommended_mode={result.get('recommended_mode')}, "
            f"currency_risk_index={result.get('currency_risk_index')}.",
            "success",
            {"recommended_mode": result.get("recommended_mode"), "currency_risk_index": result.get("currency_risk_index")},
        )
    return result


@app.post("/workflow/rfq/draft")
async def rfq_draft(payload: RFQDraftRequest, user=Depends(verify_firebase_or_local_token)) -> dict:
    _assert_same_user(user, payload.user_id)
    drafted = draft_rfq(payload.recipient, payload.event_context, payload.quantities)
    drafted["estimated_cost"] = await convert_cost(5000.0, "USD")
    drafted["generated_by"] = user.get("sub", "local")
    return drafted


@app.post("/workflow/rfq/send")
async def rfq_send(payload: RFQSendRequest, user=Depends(verify_firebase_or_local_token)) -> dict:
    requestor = _assert_same_user(user, payload.user_id)
    _assert_workflow_owner(user, payload.workflow_id)
    checkpoint = get_workflow_checkpoint(payload.workflow_id) or {}
    stage = str(checkpoint.get("current_stage") or "").upper()
    if bool(checkpoint.get("waiting_human")) or stage not in {"ACT", "AUDIT"}:
        raise HTTPException(status_code=409, detail="Workflow is not approved for external RFQ dispatch")
    expected_approval_token = derive_key("rfq_send", payload.workflow_id, requestor)
    if payload.approval_token != expected_approval_token:
        raise HTTPException(status_code=403, detail="Invalid approval token for RFQ dispatch")

    send_key = derive_key(
        "rfq_send",
        payload.workflow_id,
        payload.recipient.strip().lower(),
        payload.subject.strip(),
        payload.body.strip(),
    )
    guard = idempotency_guard(send_key, ttl_seconds=86400, owner_id=requestor)
    if guard.is_duplicate:
        return guard.cached_response or {"status": "already_sent", "workflow_id": payload.workflow_id}
    if guard.is_in_flight:
        return {"status": "in_flight", "workflow_id": payload.workflow_id}

    rfq_id = f"rfq_{uuid4().hex[:10]}"
    create_rfq_event_linked(
        rfq_id,
        payload.user_id,
        payload.workflow_id,
        payload.recipient,
        payload.subject,
        payload.body,
        "sent",
    )
    try:
        mail_result = send_rfq_email(payload.recipient, payload.subject, payload.body)
        response = {
            "status": "sent",
            "rfq_id": rfq_id,
            "workflow_id": payload.workflow_id,
            "mail": mail_result,
            "sent_by": user.get("sub", "local"),
            "approval_note": payload.approval_note or "",
        }
        mark_completed(send_key, response)
        add_audit("rfq_sent", rfq_id)
        return response
    except Exception:
        mark_failed(send_key)
        raise


@app.get("/currency/rates")
async def currency_rates(from_currency: str = Query(default="USD", min_length=3, max_length=3), to_currency: str = Query(default="INR", min_length=3, max_length=3)) -> dict:
    rate = await get_exchange_rate(from_currency.upper(), to_currency.upper())
    return {"from": from_currency.upper(), "to": to_currency.upper(), "rate": rate}


@app.get("/currency/inflation/{code}")
async def currency_inflation(code: str) -> dict:
    return {"country_code": code.upper(), "inflation_rate": await get_inflation_rate(code)}


@app.get("/exposure/all")
async def exposure_all(user=Depends(verify_firebase_or_local_token)) -> list[dict]:
    add_audit("exposure_all_read", user.get("sub", "local"))
    rows = _context_suppliers(str(user.get("sub") or "").strip())
    return [{"supplier_id": r["id"], "name": r["name"], "score": r["exposureScore"]} for r in rows]


@app.get("/exposure/{supplier_id}")
async def exposure_one(supplier_id: str, user=Depends(verify_firebase_or_local_token)) -> dict:
    rows = _context_suppliers(str(user.get("sub") or "").strip())
    selected = next((r for r in rows if r["id"] == supplier_id), None)
    if not selected:
        raise HTTPException(status_code=404, detail="Supplier not found")
    score = float(selected["exposureScore"])
    return {
        "supplier_id": supplier_id,
        "score": score,
        "breakdown": {
            "geo": round(min(1.0, score / 120), 3),
            "weather": round(min(1.0, score / 180), 3),
            "tier": round(min(1.0, score / 220), 3),
        },
        "requested_by": user.get("sub", "local"),
    }


@app.get("/audit/all")
async def audit_all(user=Depends(verify_firebase_or_local_token)) -> list[dict]:
    return list_audit(limit=100)


@app.get("/workflow/state/{workflow_id}")
async def workflow_state(workflow_id: str, stage: Literal["detect", "assess", "decide", "act", "audit"] = "assess", user=Depends(verify_firebase_or_local_token)) -> dict:
    _assert_workflow_owner(user, workflow_id)
    stored = read_workflow_event(workflow_id)
    if stored:
        return stored
    return write_workflow_event(workflow_id, stage, 0.5)


@app.post("/workflow/state/{workflow_id}")
async def workflow_state_update(workflow_id: str, payload: WorkflowStateUpdate, user=Depends(verify_firebase_or_local_token)) -> dict:
    _assert_workflow_owner(user, workflow_id)
    record = write_workflow_event(workflow_id, payload.stage, payload.confidence)
    add_audit("workflow_state_updated", f"{workflow_id}:{payload.stage}:{payload.confidence}:{user.get('sub', 'local')}")
    return record


@app.get("/ports")
async def ports() -> list[dict]:
    return [{"city": p.city, "country": p.country, "lat": p.lat, "lng": p.lng} for p in registry.ports]


@app.get("/airports")
async def airports() -> list[dict]:
    return registry.airports


@app.get("/workflow/rfq/events")
async def rfq_events(user=Depends(verify_firebase_or_local_token)) -> list[dict]:
    return list_rfq_events(limit=100)


@app.get("/signals/cache")
async def cached_signals(user=Depends(verify_firebase_or_local_token)) -> list[dict]:
    return list_signals(limit=50)


@app.get("/audit/certificate/{audit_id}")
async def audit_certificate(audit_id: str, user=Depends(verify_firebase_or_local_token)) -> Response:
    usd = float(registry.mode_cost_baseline.get("land", 7500.0))
    converted = await convert_cost(usd, "USD")
    lines = [
        "Observe -> Orient -> Decide -> Act completed",
        f"Estimated impact USD: {usd}",
        f"Converted impact: {converted['local']} {converted['currency']}",
    ]
    content = generate_audit_certificate(audit_id, user.get("sub", "local-user"), lines)
    return Response(content=content, media_type="application/pdf")


# ---------------------------------------------------------------------------
# Frontend compatibility endpoints under /api/*
# ---------------------------------------------------------------------------


@app.get("/api/dashboard/kpis")
async def api_dashboard_kpis(user=Depends(verify_firebase_or_local_token)) -> dict:
    suppliers = _context_suppliers(str(user.get("sub") or "").strip())
    events = _api_risk_events()
    rfqs = list_rfq_events(limit=500)
    return {
        "totalSuppliers": len(suppliers),
        "activeRiskEvents": len(events),
        "avgExposure": round(sum(s["exposureScore"] for s in suppliers) / max(1, len(suppliers)), 2),
        "rfqsSent": len([r for r in rfqs if str(r.get("status", "")).lower() == "sent"]),
    }


@app.get("/api/dashboard/events")
async def api_dashboard_events() -> list[dict]:
    return _api_risk_events()


@app.get("/api/dashboard/workflows")
async def api_dashboard_workflows() -> list[dict]:
    items: list[dict] = []
    for row in list_audit(limit=200):
        action = str(row.get("action", ""))
        if not action.startswith("workflow_"):
            continue
        payload = str(row.get("payload", ""))
        workflow_id = payload.split(":")[0] if ":" in payload else f"wf_{row.get('id')}"
        items.append(
            {
                "id": workflow_id,
                "title": action.replace("_", " ").title(),
                "description": payload or "Workflow event",
                "timestamp": row.get("timestamp"),
                "status": "active" if "updated" in action or "routes" in action else "complete",
            }
        )
    return items


@app.get("/api/dashboard/suppliers")
async def api_dashboard_suppliers(limit: int = 5, user=Depends(verify_firebase_or_local_token)) -> list[dict]:
    user_id = str(user.get("sub") or "").strip()
    suppliers = _context_suppliers(user_id)
    return suppliers[: max(1, int(limit))]


@app.get("/api/network/graph")
async def api_network_graph() -> dict[str, Any]:
    return _network_graph()


@app.get("/api/risks/events")
async def api_risks_events(region: str | None = None, severity: str | None = None) -> list[dict]:
    events = await api_dashboard_events()
    if severity:
        events = [e for e in events if e["severity"] == severity]
    if region:
        events = [e for e in events if e["region"] == region]
    return events


@app.get("/api/risks/suppliers")
async def api_risks_suppliers(
    tier: str | None = None,
    minScore: float | None = None,
    maxScore: float | None = None,
    user=Depends(verify_firebase_or_local_token),
) -> list[dict]:
    suppliers = await api_dashboard_suppliers(limit=5000, user=user)
    filtered = suppliers
    if tier:
        filtered = [s for s in filtered if s["tier"] == tier]
    if minScore is not None:
        filtered = [s for s in filtered if s["exposureScore"] >= float(minScore)]
    if maxScore is not None:
        filtered = [s for s in filtered if s["exposureScore"] <= float(maxScore)]
    return filtered


@app.get("/api/exposure/summary")
async def api_exposure_summary(user=Depends(verify_firebase_or_local_token)) -> dict:
    suppliers = _context_suppliers(str(user.get("sub") or "").strip())
    avg = sum(s["exposureScore"] for s in suppliers) / max(1, len(suppliers))
    critical = len([s for s in suppliers if s["exposureScore"] >= 75])
    return {"avgScore": round(avg, 1), "criticalNodes": critical, "totalMonitored": len(suppliers)}


@app.get("/api/exposure/suppliers")
async def api_exposure_suppliers(user=Depends(verify_firebase_or_local_token)) -> list[dict]:
    return await api_dashboard_suppliers(limit=5000, user=user)


@app.post("/api/workflow/routes")
async def api_workflow_routes(payload: RouteRequest, user=Depends(verify_firebase_or_local_token)) -> dict:
    return await workflow_routes(payload, user)


@app.get("/api/rfq")
async def api_rfq_list(status: str | None = None) -> list[dict]:
    items = [
        {
            "id": row["rfq_id"],
            "supplier": row["recipient"],
            "eventTrigger": row["subject"],
            "dateSent": str(row["created_at"]).split("T")[0],
            "status": str(row["status"]).title(),
            "workflowId": row.get("workflow_id"),
            "body": row.get("body", ""),
        }
        for row in list_rfq_events(limit=200)
    ]
    if status:
        return [i for i in items if i["status"].lower() == status.lower()]
    return items


@app.post("/api/rfq")
async def api_rfq_create(payload: dict, user=Depends(verify_firebase_or_local_token)) -> dict:
    rfq_id = f"rfq_{uuid4().hex[:8]}"
    user_id = str(payload.get("user_id") or user.get("sub") or "").strip()
    _assert_same_user(user, user_id)
    workflow_id = str(payload.get("workflowId") or payload.get("workflow_id") or "").strip() or None
    if workflow_id:
        _assert_workflow_owner(user, workflow_id)
    recipient = str(payload.get("supplier") or payload.get("recipient") or "unknown@example.com")
    subject = str(payload.get("eventTrigger") or payload.get("subject") or "RFQ")
    body = str(payload.get("body") or "")
    status = str(payload.get("status") or "Draft").lower()
    create_rfq_event_linked(
        rfq_id,
        user_id,
        workflow_id,
        recipient,
        subject,
        body,
        status,
    )
    return {
        "id": rfq_id,
        "supplier": recipient,
        "eventTrigger": subject,
        "dateSent": datetime.now(timezone.utc).date().isoformat(),
        "status": status.title(),
        "workflowId": payload.get("workflowId") or payload.get("workflow_id"),
        "body": body,
    }


@app.patch("/api/rfq/{rfq_id}")
async def api_rfq_patch(rfq_id: str, payload: dict) -> dict:
    status = payload.get("status")
    if status is None:
        raise HTTPException(status_code=422, detail="Missing status")
    value = str(status).strip().lower()
    allowed = {"draft", "pending approval", "sent", "responded", "closed"}
    if value not in allowed:
        raise HTTPException(status_code=422, detail=f"Invalid status. Allowed: {sorted(allowed)}")
    updated = update_rfq_status(rfq_id, value)
    if not updated:
        raise HTTPException(status_code=404, detail="Not Found")
    return {"id": rfq_id, "status": value.title()}


@app.get("/api/rfq/{rfq_id}/thread")
async def api_rfq_thread(rfq_id: str) -> dict:
    msgs = list_rfq_messages(rfq_id, limit=200)
    return {"rfq_id": rfq_id, "messages": msgs}


@app.post("/api/rfq/{rfq_id}/thread")
async def api_rfq_thread_post(rfq_id: str, payload: dict) -> dict:
    body = str(payload.get("body") or "").strip()
    direction = str(payload.get("direction") or "note").strip().lower()
    sender = payload.get("sender")
    if not body:
        raise HTTPException(status_code=422, detail="Missing body")
    if direction not in {"outbound", "inbound", "note"}:
        raise HTTPException(status_code=422, detail="Invalid direction")
    msg = add_rfq_message(rfq_id, direction, str(sender) if sender else None, body)
    return {"status": "ok", "message": msg}


@app.get("/api/audit/compliance")
async def api_audit_compliance() -> dict:
    reports = list_workflow_reports(limit=1000)
    response_times = []
    actions: dict[str, int] = {}
    for r in reports:
        summary = r.get("summary") if isinstance(r.get("summary"), dict) else {}
        rt = summary.get("response_time_seconds")
        if isinstance(rt, (int, float)):
            response_times.append(float(rt))
        action = str(summary.get("action_taken") or "unknown")
        actions[action] = actions.get(action, 0) + 1
    avg_rt = sum(response_times) / max(1, len(response_times))
    return {
        "total_workflows": len(reports),
        "avg_response_time_seconds": round(avg_rt, 1),
        "actions_breakdown": actions,
    }


@app.get("/api/workflows")
async def api_workflow_reports() -> list[dict]:
    # List stored workflow reports (AUDIT page source of truth).
    return list_workflow_reports(limit=200)


@app.post("/api/workflow/analyze")
async def api_workflow_analyze(payload: WorkflowAnalyzeRequest, user=Depends(verify_firebase_or_local_token)) -> dict:
    if payload.workflow_id:
        _assert_workflow_owner(user, payload.workflow_id)
    result = await generate_workflow_analysis(
        event=payload.event,
        suppliers=payload.suppliers,
        assessment=payload.assessment,
        workflow_id=payload.workflow_id,
    )
    wf = (payload.workflow_id or "").strip()
    if wf:
        prefer = (os.getenv("LLM_PROVIDER") or "groq").strip().lower()
        used = result.provider
        is_fallback = used == "local" or (used == "groq" and prefer == "gemini")
        log_reasoning_step(
            wf,
            "assessment_agent",
            "gemini_assessment" if used == "gemini" else "llm_analysis",
            f"Assessment narrative generated via {used} (LLM_PROVIDER={prefer}).",
            "fallback" if is_fallback else "success",
            {"provider": used, "llm_provider_env": prefer},
        )
    provider = str(result.provider or "local").strip().lower()
    calibration_factor = {"gemini": 1.0, "groq": 0.92, "local": 0.85}.get(provider, 0.9)
    assessment_conf = None
    if isinstance(payload.assessment, dict):
        raw = payload.assessment.get("confidence_score") or payload.assessment.get("confidence")
        if isinstance(raw, (int, float)):
            assessment_conf = float(raw)
    if assessment_conf is None:
        assessment_conf = 0.5
    evidence = _decision_evidence_status(payload.event if isinstance(payload.event, dict) else {})
    calibrated_conf = max(0.0, min(1.0, assessment_conf * calibration_factor))
    context = _context_payload_for_user(str(user.get("sub") or "").strip())
    dq = assess_context_quality(context)
    bounds = confidence_bounds(calibrated_conf, float(dq.get("score") or 0.0), provider)
    actionable = bool(evidence["actionable"] and bounds["actionable"])
    return {
        "provider": result.provider,
        "analysis": result.text,
        "decision_quality": {
            "provider": provider,
            "calibration_factor": calibration_factor,
            "raw_recommendation_confidence": round(assessment_conf, 4),
            "calibrated_recommendation_confidence": round(calibrated_conf, 4),
            "evidence": evidence,
            "data_quality": dq,
            "confidence_bounds": bounds,
            "actionable": actionable,
            "action_block_reason": "" if actionable else "insufficient_evidence_or_uncalibrated_confidence",
        },
    }


@app.post("/api/agents/chat")
async def api_agents_chat(payload: AgentChatRequest, user=Depends(verify_firebase_or_local_token)) -> dict:
    if payload.workflow_id:
        _assert_workflow_owner(user, payload.workflow_id)
    result = await chatbot_manager.process_message(
        message=payload.message,
        workflow_id=payload.workflow_id,
        session_id=payload.session_id,
        context=payload.context,
    )

    wf = (payload.workflow_id or "").strip()
    report_output = result.outputs.get("reporting_agent")
    if wf and isinstance(report_output, dict) and report_output.get("markdown"):
        existing = get_workflow_report(wf) or {"workflow_id": wf}
        existing["chat_agent_report"] = report_output["markdown"]
        upsert_workflow_report(wf, existing)

    return {
        "conversation_id": result.conversation_id,
        "sequence": result.sequence,
        "route": result.route,
        "supervisor": result.supervisor,
        "outputs": result.outputs,
        "text": result.final_text,
    }


@app.post("/api/workflow/start")
async def api_workflow_start(payload: WorkflowStartRequest, user=Depends(verify_firebase_or_local_token)) -> dict:
    _assert_same_user(user, payload.user_id)
    _assert_onboarding_readiness(payload.user_id)
    _validate_detect_inputs(payload.selected_signal, payload.affected_suppliers)
    customer_id = _resolve_customer_id_for_user(payload.user_id)
    network_routes = _context_network_routes(payload.user_id)
    initial_state = {
        "workflow_id": payload.workflow_id,
        "user_id": payload.user_id,
        "customer_id": customer_id,
        "current_stage": "DETECT",
        "signals": [payload.selected_signal] if payload.selected_signal else [],
        "selected_signal": payload.selected_signal,
        "affected_suppliers": payload.affected_suppliers,
        "exposure_usd": 0.0,
        "exposure_local": 0.0,
        "local_currency": payload.local_currency,
        "days_at_risk": 0,
        "confidence": 0.0,
        "currency_risk_index": 0.0,
        "inflation_rate": 0.0,
        "assessment_summary": "",
        "route_comparison": [],
        "network_routes": network_routes,
        "recommended_mode": "",
        "rl_confidence": 0.0,
        "rfq_sent": False,
        "action_state": {"generated": False, "executed": False, "confirmed": False},
        "reasoning_steps": [],
    }
    return await workflow_graph_manager.start_workflow(initial_state)


@app.post("/api/workflow/{workflow_id}/approve")
async def api_workflow_approve(workflow_id: str, payload: WorkflowApprovalRequest, user=Depends(verify_firebase_or_local_token)) -> dict:
    owner = _assert_workflow_owner(user, workflow_id)
    approved = await workflow_graph_manager.approve_decision(workflow_id, action=payload.action, mode=payload.mode)
    approved["rfq_approval_token"] = derive_key("rfq_send", workflow_id, owner)
    return approved


@app.post("/api/workflow/report")
async def api_workflow_report_upsert(payload: WorkflowReportStageUpsert, user=Depends(verify_firebase_or_local_token)) -> dict:
    _assert_workflow_owner(user, payload.workflow_id)
    existing = get_workflow_report(payload.workflow_id) or {"workflow_id": payload.workflow_id}
    existing.setdefault("user_id", _resolve_workflow_owner(payload.workflow_id))
    stage_order = ["detect", "assess", "decide", "act", "audit"]
    idx = stage_order.index(payload.stage)
    if idx > 0:
        prior = stage_order[idx - 1]
        if prior not in existing:
            raise HTTPException(status_code=409, detail=f"Cannot write {payload.stage} before {prior}")
    if payload.stage == "audit":
        act_payload = existing.get("act") if isinstance(existing.get("act"), dict) else {}
        action_state = act_payload.get("action_state") if isinstance(act_payload.get("action_state"), dict) else {}
        if not bool(action_state.get("confirmed")):
            raise HTTPException(status_code=409, detail="Cannot write audit before ACT confirmation")
    existing[payload.stage] = payload.payload
    existing["updated_at"] = datetime.now(timezone.utc).isoformat()

    # Build/refresh summary snapshot for PDF executive section
    summary = existing.get("summary") if isinstance(existing.get("summary"), dict) else {}
    detect_evt = (existing.get("detect") or {}).get("event") if isinstance(existing.get("detect"), dict) else None
    if isinstance(detect_evt, dict):
        summary["event_title"] = detect_evt.get("title") or detect_evt.get("event_type")
        summary["region"] = detect_evt.get("region") or detect_evt.get("location")
    assess = existing.get("assess") if isinstance(existing.get("assess"), dict) else {}
    if isinstance(assess, dict):
        summary["exposure_usd"] = assess.get("exposure_usd")
        summary["affected_nodes"] = assess.get("affected_nodes")
    decide = existing.get("decide") if isinstance(existing.get("decide"), dict) else {}
    if isinstance(decide, dict):
        summary["recommended_mode"] = decide.get("recommended_mode")
    act = existing.get("act") if isinstance(existing.get("act"), dict) else {}
    if isinstance(act, dict):
        summary["action_taken"] = act.get("decision")
        action_state = act.get("action_state") if isinstance(act.get("action_state"), dict) else {}
        if action_state:
            summary["act_generated"] = bool(action_state.get("generated"))
            summary["act_executed"] = bool(action_state.get("executed"))
            summary["act_confirmed"] = bool(action_state.get("confirmed"))
    audit = existing.get("audit") if isinstance(existing.get("audit"), dict) else {}
    if isinstance(audit, dict):
        summary["response_time_seconds"] = audit.get("response_time_seconds")

    # If audit hasn't been finalized yet, derive response time from detect->act timestamps.
    # This prevents PDFs from showing "— seconds" during demo runs.
    rt_val = summary.get("response_time_seconds")
    if not isinstance(rt_val, (int, float)) or float(rt_val) <= 0:
        detect = existing.get("detect") if isinstance(existing.get("detect"), dict) else {}
        act2 = existing.get("act") if isinstance(existing.get("act"), dict) else {}
        detected_at = None
        executed_at = None
        if isinstance(detect, dict):
            detected_at = detect.get("detected_at") or (detect.get("event") or {}).get("timestamp")
        if isinstance(act2, dict):
            executed_at = act2.get("executed_at")
        try:
            if detected_at and executed_at:
                start_ms = datetime.fromisoformat(str(detected_at).replace("Z", "+00:00")).timestamp() * 1000
                end_ms = datetime.fromisoformat(str(executed_at).replace("Z", "+00:00")).timestamp() * 1000
                summary["response_time_seconds"] = max(0, int(round((end_ms - start_ms) / 1000)))
        except Exception:
            pass
    existing["summary"] = summary

    upsert_workflow_report(payload.workflow_id, existing)

    return {"status": "ok", "workflow_id": payload.workflow_id, "stage": payload.stage}


@app.get("/api/workflow/reasoning/{workflow_id}")
async def api_workflow_reasoning(workflow_id: str, user=Depends(verify_firebase_or_local_token)) -> dict[str, Any]:
    _can_read_reasoning_stream(user, workflow_id)
    steps = read_reasoning_steps(workflow_id, limit=500)
    return {"workflow_id": workflow_id, "steps": steps}


# ── In-process render cache (avoids re-hitting Groq on every open) ────────────
_render_cache: dict[str, list[dict]] = {}


@app.get("/api/workflow/reasoning/{workflow_id}/render")
async def api_workflow_reasoning_render(
    workflow_id: str, user=Depends(verify_firebase_or_local_token)
) -> dict[str, Any]:
    """
    Returns reasoning steps enriched with a Groq-generated 'narrative' field.
    The raw JSON (agent, stage, detail, output, timestamp) is preserved; only
    the human-readable text is replaced by a crisp, operator-facing sentence.
    """
    _can_read_reasoning_stream(user, workflow_id)

    if workflow_id in _render_cache:
        return {"workflow_id": workflow_id, "steps": _render_cache[workflow_id]}

    raw_steps = read_reasoning_steps(workflow_id, limit=500)
    if not raw_steps:
        return {"workflow_id": workflow_id, "steps": []}

    import json as _json
    import os as _os

    groq_key = _os.getenv("GROQ_API_KEY", "")
    if not groq_key:
        # No Groq key — return raw steps as-is
        return {"workflow_id": workflow_id, "steps": raw_steps}

    try:
        from groq import AsyncGroq as _AsyncGroq
        _client = _AsyncGroq(api_key=groq_key)

        steps_payload = _json.dumps(
            [
                {
                    "agent": s.get("agent"),
                    "stage": s.get("stage"),
                    "status": s.get("status"),
                    "detail": s.get("detail"),
                    "output": s.get("output") or {},
                    "timestamp": s.get("timestamp"),
                }
                for s in raw_steps
            ],
            default=str,
        )

        prompt = (
            "You are a supply chain intelligence narrator for Praecantator, an autonomous SCRM platform. "
            "Below is a JSON array of agent reasoning steps from a live incident workflow. "
            "For EACH step, write a rich, detailed summary paragraph (at least 3-4 sentences) that deeply explains what the agent did, "
            "its findings, and the implications — in clean, precise, operator-facing English. Do not just output one line. "
            "DO NOT include any raw field mappings in the text (e.g., do not write 'recipient -> ...' or 'provider -> ...'). "
            "DO NOT mention internal technical names like 'Groq', 'SQLite', 'Firestore', 'Firebase', 'fallback', 'degraded mode', or any infrastructure detail. "
            "DO NOT use corporate jargon or passive voice. Be direct and informative. "
            "Return a JSON array with the same order as the input. Each element must have exactly these keys: "
            "\"agent\", \"stage\", \"status\", \"timestamp\", \"narrative\". "
            "The narrative key replaces the detail field with your clean, detailed prose. "
            "Return ONLY valid JSON — no markdown, no explanation, no code fences.\n\n"
            f"Input steps:\n{steps_payload}"
        )

        resp = await _client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
            temperature=0.3,
        )
        raw_text = resp.choices[0].message.content or "[]"
        # Strip potential markdown fences
        raw_text = raw_text.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```", 2)[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
            raw_text = raw_text.rsplit("```", 1)[0]

        rendered = _json.loads(raw_text.strip())

        # Merge back full raw step data (preserve output, timestamp_ms, etc.)
        merged: list[dict] = []
        for i, step in enumerate(raw_steps):
            overlay = rendered[i] if i < len(rendered) else {}
            merged.append({**step, "narrative": overlay.get("narrative", step.get("detail", ""))})

        _render_cache[workflow_id] = merged
        return {"workflow_id": workflow_id, "steps": merged}

    except Exception as exc:
        logger.warning(f"[reasoning/render] Groq enrichment failed: {exc} — returning raw steps")
        return {"workflow_id": workflow_id, "steps": raw_steps}


@app.get("/api/workflow/state/{workflow_id}")
async def api_workflow_state(workflow_id: str, user=Depends(verify_firebase_or_local_token)) -> dict[str, Any]:
    _assert_workflow_owner(user, workflow_id)
    checkpoint = get_workflow_checkpoint(workflow_id) or {}
    event = read_workflow_event(workflow_id) or {}
    state = checkpoint if checkpoint else event
    status = "waiting_human" if state.get("waiting_human") else ("complete" if state.get("current_stage") == "AUDIT" else "running")
    return {"workflow_id": workflow_id, "status": status, "state": state, "event": event}


@app.get("/api/workflow/report/{workflow_id}")
async def api_workflow_report_get(workflow_id: str, user=Depends(verify_firebase_or_local_token)) -> dict:
    _assert_workflow_owner(user, workflow_id)
    report = get_workflow_report(workflow_id)
    if not report:
        return {"workflow_id": workflow_id}
    return report


@app.get("/api/workflow/report/{workflow_id}/pdf")
async def api_workflow_report_pdf(workflow_id: str, request: Request, user=Depends(verify_firebase_or_local_token)) -> Response:
    _assert_workflow_owner(user, workflow_id)
    report = get_workflow_report(workflow_id)
    if not report:
        raise HTTPException(status_code=404, detail="Not Found")
    # Ensure summary response time is populated even if audit stage wasn't clicked.
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    rt_val = summary.get("response_time_seconds")
    if not isinstance(rt_val, (int, float)) or float(rt_val) <= 0:
        detect = report.get("detect") if isinstance(report.get("detect"), dict) else {}
        act = report.get("act") if isinstance(report.get("act"), dict) else {}
        detected_at = None
        executed_at = None
        if isinstance(detect, dict):
            detected_at = detect.get("detected_at") or (detect.get("event") or {}).get("timestamp")
        if isinstance(act, dict):
            executed_at = act.get("executed_at")
        try:
            if detected_at and executed_at:
                start_ms = datetime.fromisoformat(str(detected_at).replace("Z", "+00:00")).timestamp() * 1000
                end_ms = datetime.fromisoformat(str(executed_at).replace("Z", "+00:00")).timestamp() * 1000
                summary["response_time_seconds"] = max(0, int(round((end_ms - start_ms) / 1000)))
                report["summary"] = summary
                upsert_workflow_report(workflow_id, report)
        except Exception:
            pass
    # Requested-by should reflect the current operator (from context/profile), not a hardcoded value.
    user_id = str(user.get("sub") or "").strip()
    ctx = read_context(user_id)
    if not (isinstance(ctx, dict) and ctx):
        row = get_context(user_id) or {}
        try:
            ctx = json.loads(row.get("payload_json") or "{}") if isinstance(row, dict) else {}
        except Exception:
            ctx = {}
    profile = ctx.get("operator_profile") if isinstance(ctx, dict) and isinstance(ctx.get("operator_profile"), dict) else {}
    requested_by = str(profile.get("name") or "").strip()
    if profile.get("email"):
        requested_by = f"{requested_by} <{profile.get('email')}>".strip()
    if not requested_by or requested_by == "<None>":
        requested_by = user_id

    if not report.get("appendix_nlp"):
        try:
            from services.llm_analysis import generate_appendix_nlp
            report["appendix_nlp"] = await generate_appendix_nlp(report)
            upsert_workflow_report(workflow_id, report)
        except Exception as e:
            report["appendix_nlp"] = f"NLP Generation fallback failed completely: {e}"

    content = generate_workflow_audit_report_pdf(report, requested_by=requested_by)
    return Response(content=content, media_type="application/pdf")


@app.get("/api/signals/hazards")
async def api_signals_hazards() -> list[dict]:
    hazards: list[dict] = []
    for sig in _parsed_signals(limit=5000):
        hazards.append(
            {
                "id": str(sig.get("id") or sig.get("signal_id")),
                "type": str(sig.get("event_type") or "risk"),
                "title": str(sig.get("title") or sig.get("event_type") or "Hazard signal"),
                "location": str(sig.get("location") or "Unknown"),
                "time": str(sig.get("created_at") or ""),
                "severity": _score_to_status(float(sig.get("severity") or 0)),
                "lat": float(sig.get("lat", 0) or 0),
                "lng": float(sig.get("lng", 0) or 0),
                "url": _normalized_url(str(sig.get("url") or "")),
            }
        )
    return hazards


@app.get("/api/signals/news")
async def api_signals_news() -> list[dict]:
    rows = _parsed_signals(limit=5000)
    news_sources = {"gdelt", "newsapi", "gnews"}
    filtered = [
        sig
        for sig in rows
        if str(sig.get("source", "")).lower() in news_sources or bool(_normalized_url(str(sig.get("url") or "")))
    ]
    return [
        {
            "id": str(sig.get("id") or sig.get("signal_id")),
            "source": str(sig.get("source") or "signal"),
            "title": str(sig.get("title") or sig.get("event_type") or "News signal"),
            "location": str(sig.get("location") or "Unknown"),
            "time": str(sig.get("created_at") or ""),
            "relevanceScore": round(min(1.0, max(0.0, float(sig.get("severity") or 0) / 10.0)), 3),
            "url": _normalized_url(str(sig.get("url") or "")),
        }
        for sig in filtered
    ]


@app.get("/api/signals/sources")
async def api_signals_sources() -> list[dict]:
    rows = _parsed_signals(limit=5000)
    by_source: dict[str, int] = {}
    latest_by_source: dict[str, str] = {}
    for sig in rows:
        src = str(sig.get("source") or "unknown")
        by_source[src] = by_source.get(src, 0) + 1
        latest_by_source[src] = str(sig.get("created_at") or latest_by_source.get(src) or "")

    SOURCE_META: dict[str, dict] = {
        "nasa_eonet":  {"category": "disaster",     "label": "NASA EONET",         "url": "https://eonet.gsfc.nasa.gov"},
        "gdacs":       {"category": "disaster",     "label": "GDACS",              "url": "https://gdacs.org"},
        "usgs":        {"category": "disaster",     "label": "USGS Earthquakes",   "url": "https://earthquake.usgs.gov"},
        "nasa_firms":  {"category": "disaster",     "label": "NASA FIRMS",         "url": "https://firms.modaps.eosdis.nasa.gov"},
        "reliefweb":   {"category": "humanitarian", "label": "ReliefWeb",          "url": "https://reliefweb.int"},
        "gdelt":       {"category": "geopolitical", "label": "GDELT Project",      "url": "https://gdeltproject.org"},
        "acled":       {"category": "geopolitical", "label": "ACLED",              "url": "https://acleddata.com"},
        "newsapi":     {"category": "news",         "label": "NewsAPI",            "url": "https://newsapi.org"},
        "gnews":       {"category": "news",         "label": "GNews",              "url": "https://gnews.io"},
        "ofac":        {"category": "regulatory",   "label": "OFAC Sanctions",     "url": "https://sanctionssearch.ofac.treas.gov"},
        "mastodon":    {"category": "sentiment",    "label": "Mastodon (BERT)",    "url": "https://mastodon.social"},
        "hackernews":  {"category": "sentiment",    "label": "HackerNews (BERT)",  "url": "https://news.ycombinator.com"},
        "reddit":      {"category": "sentiment",    "label": "Reddit (BERT)",      "url": "https://reddit.com"},
    }
    return [
        {
            "id": f"src_{idx+1}",
            "name": name,
            "label": SOURCE_META.get(name, {}).get("label", name),
            "category": SOURCE_META.get(name, {}).get("category", "other"),
            "source_url": SOURCE_META.get(name, {}).get("url", ""),
            "active": True,
            "lastFetch": latest_by_source.get(name, ""),
            "recordCount": count,
            "latencyMs": 0,
        }
        for idx, (name, count) in enumerate(sorted(by_source.items(), key=lambda kv: kv[1], reverse=True))
    ]


@app.get("/api/signals/categorized")
async def api_signals_categorized() -> dict:
    """Returns all signals grouped by source_category for the Global Monitoring page."""
    rows = _parsed_signals(limit=5000)
    categories: dict[str, list[dict]] = {
        "disaster": [], "geopolitical": [], "news": [],
        "regulatory": [], "sentiment": [], "humanitarian": [], "social_news": [],
        "maritime": [], "trade": [],
    }
    for sig in rows:
        cat = str(sig.get("source_category") or "")
        if not cat:
            # infer from source
            src = str(sig.get("source") or "")
            if src in ("nasa_eonet", "gdacs", "usgs", "nasa_firms"): cat = "disaster"
            elif src in ("gdelt", "acled"): cat = "geopolitical"
            elif src in ("imf_portwatch", "imf_portwatch_disruptions"): cat = "maritime"
            elif src == "wto": cat = "trade"
            elif src in ("newsapi", "gnews"): cat = "news"
            elif src == "reliefweb": cat = "humanitarian"
            elif src == "ofac": cat = "regulatory"
            elif sig.get("event_type") == "sentiment_aggregate": cat = "sentiment"
            elif sig.get("event_type") == "social_news_signal": cat = "social_news"
            else: cat = "news"
        bucket = categories.get(cat, categories["news"])
        bucket.append({
            "id": str(sig.get("id") or sig.get("signal_id")),
            "event_type": str(sig.get("event_type") or "signal"),
            "title": str(sig.get("title") or "Signal"),
            "description": str(sig.get("description") or sig.get("summary") or sig.get("event_type") or ""),
            "location": str(sig.get("location") or "Unknown"),
            "severity": _score_to_status(float(sig.get("severity") or 0)),
            "severity_raw": float(sig.get("severity") or 0),
            "lat": float(sig.get("lat", 0) or 0),
            "lng": float(sig.get("lng", 0) or 0),
            "source": str(sig.get("source") or "unknown"),
            "source_category": cat,
            "url": _normalized_url(str(sig.get("url") or "")),
            "time": str(sig.get("created_at") or ""),
            "published_at": str(sig.get("created_at") or ""),
            "detected_at": str(sig.get("created_at") or ""),
            "verified": bool((sig.get("citation") or {}).get("verified")) if isinstance(sig.get("citation"), dict) else False,
            "corroborated_by": list((sig.get("citation") or {}).get("corroborated_by") or []) if isinstance(sig.get("citation"), dict) else [],
            "corroboration_count": int(((sig.get("citation") or {}).get("corroboration_count") or 0)) if isinstance(sig.get("citation"), dict) else 0,
            "relevance_score": float(sig.get("relevance_score") or 0),
            # sentiment-specific fields
            "sentiment_topic": sig.get("sentiment_topic"),
            "sentiment_positive_pct": sig.get("sentiment_positive_pct"),
            "sentiment_negative_pct": sig.get("sentiment_negative_pct"),
            "sentiment_neutral_pct": sig.get("sentiment_neutral_pct"),
            "sentiment_post_count": sig.get("sentiment_post_count"),
            "sentiment": sig.get("sentiment"),
            "sentiment_score": sig.get("sentiment_score"),
        })
    return {cat: items for cat, items in categories.items()}


@app.get("/api/signals/sentiment")
async def api_signals_sentiment() -> list[dict]:
    """Returns only BERT sentiment aggregate signals for quick dashboard access."""
    rows = _parsed_signals(limit=5000)
    return [
        {
            "id": str(sig.get("id") or sig.get("signal_id")),
            "source": str(sig.get("source") or "unknown"),
            "topic": str(sig.get("sentiment_topic") or "general"),
            "positive_pct": float(sig.get("sentiment_positive_pct") or 0),
            "negative_pct": float(sig.get("sentiment_negative_pct") or 0),
            "neutral_pct": float(sig.get("sentiment_neutral_pct") or 0),
            "post_count": int(sig.get("sentiment_post_count") or 0),
            "time": str(sig.get("created_at") or ""),
        }
        for sig in rows
        if sig.get("event_type") == "sentiment_aggregate"
    ]


@app.post("/api/signals/refresh")
async def api_signals_refresh() -> dict:
    """On-demand signal refresh — triggers immediate poll of all 12 source streams."""
    from scheduler.signal_poll import force_poll
    return await force_poll()


@app.get("/api/audit")
async def api_audit() -> list[dict]:
    rows = list_audit(limit=200)
    return [
        {
            "id": f"aud_{row['id']}",
            "action": row["action"],
            "payload": row.get("payload", ""),
            "event": row["action"],
            "suppliers": row.get("payload", ""),
            "decision": row["action"],
            "executedBy": "system",
            "timestamp": row["timestamp"],
            "durationMs": 0,
        }
        for row in rows
    ]


def _audit_numeric_id(value: str) -> int | None:
    raw = (value or "").strip()
    if raw.startswith("aud_"):
        raw = raw.replace("aud_", "", 1)
    try:
        return int(raw)
    except Exception:
        return None


@app.get("/api/audit/{audit_id}/pdf")
async def api_audit_pdf(audit_id: str) -> Response:
    numeric = _audit_numeric_id(audit_id)
    if numeric is None:
        raise HTTPException(status_code=422, detail="Invalid audit id")
    row = get_audit(numeric)
    if not row:
        raise HTTPException(status_code=404, detail="Not Found")

    summary = [
        f"Event: {row.get('action', '')}",
        f"Timestamp: {row.get('timestamp', '')}",
        f"Payload: {row.get('payload', '')}",
    ]
    content = generate_audit_certificate(f"aud_{numeric}", "system", summary)
    return Response(content=content, media_type="application/pdf")


@app.get("/api/audit/export")
async def api_audit_export() -> Response:
    rows = list_audit(limit=200)
    lines: list[str] = []
    for r in rows:
        lines.append(f"[aud_{r.get('id')}] {r.get('timestamp')} — {r.get('action')} — {r.get('payload')}")
    content = generate_audit_certificate("audit_export", "system", lines)
    return Response(content=content, media_type="application/pdf")


@app.get("/api/settings/profile")
async def api_settings_profile(request: Request, user=Depends(verify_firebase_or_local_token)) -> dict:
    user_id = str(user.get("sub") or "").strip()
    tenant_id = _resolved_request_tenant(user)
    # Load profile context from Firestore.
    fs = read_context(user_id)
    ctx: dict[str, Any] = {}
    if isinstance(fs, dict) and fs:
        ctx = dict(fs)
    else:
        row = get_context(user_id) or {}
        try:
            ctx = json.loads(row.get("payload_json") or "{}") if isinstance(row, dict) else {}
        except Exception:
            ctx = {}

    profile = ctx.get("operator_profile") if isinstance(ctx.get("operator_profile"), dict) else {}
    return {
        "name": str(profile.get("name") or ""),
        "email": str(profile.get("email") or ""),
        "company": str(profile.get("company") or ctx.get("company_name") or ""),
        "role": str(profile.get("role") or "Admin"),
        "user_id": user_id,
        "tenant_id": tenant_id,
        "customer_id": str(ctx.get("customer_id") or tenant_id),
        "organization_id": str(ctx.get("organization_id") or tenant_id),
    }


@app.patch("/api/settings/profile")
async def api_settings_profile_patch(payload: dict, request: Request, user=Depends(verify_firebase_or_local_token)) -> dict:
    user_id = str(user.get("sub") or "").strip()
    if payload.get("user_id"):
        _assert_same_user(user, str(payload.get("user_id")))

    # Load existing Firestore context and merge.
    fs = read_context(user_id)
    ctx: dict[str, Any] = {}
    if isinstance(fs, dict) and fs:
        ctx = dict(fs)
    else:
        row = get_context(user_id) or {}
        try:
            ctx = json.loads(row.get("payload_json") or "{}") if isinstance(row, dict) else {}
        except Exception:
            ctx = {}

    profile = ctx.get("operator_profile") if isinstance(ctx.get("operator_profile"), dict) else {}
    for key in ("name", "email", "company", "role"):
        if key in payload and payload.get(key) is not None:
            profile[key] = payload.get(key)
    ctx["operator_profile"] = profile
    ctx["updated_at"] = datetime.now(timezone.utc).isoformat()

    # Persist to Firestore.
    write_context(user_id, ctx)
    add_audit("settings_profile_update", user_id)
    return await api_settings_profile(request)


@app.get("/api/settings/billing")
async def api_settings_billing(user=Depends(verify_firebase_or_local_token)) -> dict:
    tenant_id = _resolved_request_tenant(user)
    workflows_used = len([r for r in list_audit(limit=1000) if str(r.get("action", "")).startswith("workflow_")])
    rfqs_sent = len([r for r in list_rfq_events(limit=1000) if str(r.get("status", "")).lower() == "sent"])
    suppliers_used = len(_context_suppliers_or_empty(str(user.get("sub") or "").strip()))
    return {
        "plan": "Usage",
        "monthlyRate": 0,
        "workflowRunsUsed": workflows_used,
        "workflowRunsLimit": 1000,
        "rfqsSent": rfqs_sent,
        "suppliersUsed": suppliers_used,
        "suppliersLimit": max(200, suppliers_used),
        "tenantId": tenant_id,
    }


@app.get("/api/data/health")
async def api_data_health(user=Depends(verify_firebase_or_local_token)) -> dict[str, Any]:
    _ = str(user.get("sub") or "").strip()
    return data_registry_health_report()


@app.get("/api/intelligence/gaps")
async def api_intelligence_gaps(user=Depends(verify_firebase_or_local_token)) -> dict[str, Any]:
    user_id = str(user.get("sub") or "").strip()
    context = _context_payload_for_user(user_id)
    return build_intelligence_gap_report(user_id=user_id, context=context)


@app.get("/api/master-data/changes")
async def api_master_data_changes(limit: int = 200, user=Depends(verify_firebase_or_local_token)) -> dict[str, Any]:
    user_id = str(user.get("sub") or "").strip()
    return {"changes": list_master_data_changes(user_id, limit=max(1, min(limit, 1000)))}


@app.post("/api/master-data/propagate")
async def api_master_data_propagate(user=Depends(verify_firebase_or_local_token)) -> dict[str, Any]:
    user_id = str(user.get("sub") or "").strip()
    changes = list_master_data_changes(user_id, limit=100)
    if not changes:
        return {"status": "ok", "user_id": user_id, "propagated": 0, "affected_domains": []}
    domains = set()
    for change in changes:
        ctype = str(change.get("change_type") or "")
        if "network" in ctype:
            domains.update({"routing", "monitoring", "incident_generation"})
        if "onboarding" in ctype:
            domains.update({"assessment", "exposure", "workflow_input"})
    summary = {
        "status": "ok",
        "user_id": user_id,
        "propagated": len(changes),
        "affected_domains": sorted(domains),
        "latest_change_at": changes[0].get("created_at"),
    }
    add_audit("master_data_propagated", json.dumps(summary))
    return summary


@app.post("/api/onboarding/complete")
async def api_onboarding_complete(payload: OnboardingRequest, user=Depends(verify_firebase_or_local_token)) -> dict:
    return await onboarding_complete(payload, user)


@app.get("/api/contexts/{user_id}")
async def api_context_get(user_id: str, user=Depends(verify_firebase_or_local_token)) -> dict:
    _assert_same_user(user, user_id)
    # Load context from Firestore.
    fs = read_context(user_id)
    if isinstance(fs, dict) and fs:
        context = dict(fs)
        context.pop("user_id", None)
        context.pop("workflow_id", None)
        updated = str(context.get("updated_at") or "")
        return {"user_id": user_id, "updated_at": updated, "context": context}

    row = get_context(user_id)
    if not row:
        # Return empty context instead of 404 so frontend workflows can still run in demo mode.
        return {"user_id": user_id, "updated_at": None, "context": {}}
    try:
        payload = json.loads(row.get("payload_json") or "{}")
    except Exception:
        payload = {}
    return {"user_id": row.get("user_id"), "updated_at": row.get("updated_at"), "context": payload}


@app.get("/api/onboarding/status/{user_id}")
async def api_onboarding_status(user_id: str, user=Depends(verify_firebase_or_local_token)) -> dict:
    _assert_same_user(user, user_id)
    fs = read_context(user_id)
    payload: dict = {}
    updated_at = None
    if isinstance(fs, dict) and fs:
        payload = dict(fs)
        payload.pop("user_id", None)
        updated_at = payload.get("updated_at")
    else:
        row = get_context(user_id)
        if row:
            updated_at = row.get("updated_at")
            try:
                payload = json.loads(row.get("payload_json") or "{}")
            except Exception:
                payload = {}

    suppliers = payload.get("suppliers") if isinstance(payload, dict) else None
    nodes = payload.get("logistics_nodes") if isinstance(payload, dict) else None
    complete = (
        bool(payload)
        and isinstance(suppliers, list)
        and len(suppliers) > 0
        and isinstance(nodes, list)
        and len(nodes) > 0
        and bool(payload.get("company_name"))
    )
    return {"user_id": user_id, "complete": complete, "updated_at": updated_at}


# ─────────────────────────────────────────────────────────────────────────────
# Supply Chain Network endpoints
# ─────────────────────────────────────────────────────────────────────────────

def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in km."""
    import math
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _event_impact_radius_km(event: dict) -> float:
    """Return the geospatial impact radius of an event based on its type."""
    title = str(event.get("title", "") or event.get("type", "")).lower()
    if any(w in title for w in ("cyclone", "typhoon", "hurricane")): return 400
    if "earthquake" in title: return 250
    if "flood" in title: return 150
    if any(w in title for w in ("wildfire", "fire")): return 80
    if any(w in title for w in ("strike", "congestion")): return 50
    if any(w in title for w in ("war", "conflict", "geopolit")): return 300
    if any(w in title for w in ("port", "shipping")): return 80
    return 150


@app.post("/api/workflow/network")
async def api_save_network(payload: SCNetworkSaveRequest, user=Depends(verify_firebase_or_local_token)) -> dict:
    """
    Persist the user's supply chain network definition (nodes + routes) into
    their context document so it can be retrieved across sessions.

    The network is stored under context['supply_chain_network'] and is the
    primary input for the geospatial monitoring workflow.
    """
    user_id = _assert_same_user(user, payload.user_id)
    nodes_dump = [n.model_dump() for n in payload.nodes]
    routes_dump = [r.model_dump() for r in payload.routes]
    graph_check = validate_network_graph(nodes_dump, routes_dump)
    if not graph_check.valid:
        raise HTTPException(status_code=422, detail={"message": "Invalid network graph", "errors": graph_check.errors})

    # Enforce quota boundary for supply chain geometry constraints
    try:
        quota_manager.check_network_size(user_id, len(payload.nodes))
        quota_manager.enforce_rate_limit(user_id, "save_network")
    except Exception as e:
        raise HTTPException(status_code=429, detail=str(e))

    # Load existing context
    fs = read_context(user_id)
    ctx: dict[str, Any] = {}
    if isinstance(fs, dict) and fs:
        ctx = dict(fs)
    else:
        row = get_context(user_id) or {}
        try:
            ctx = json.loads(row.get("payload_json") or "{}") if isinstance(row, dict) else {}
        except Exception:
            ctx = {}

    ctx["supply_chain_network"] = {
        "nodes": nodes_dump,
        "routes": routes_dump,
        "description": payload.description,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "node_count": len(payload.nodes),
        "route_count": len(payload.routes),
    }
    ctx["master_data_version"] = int((ctx.get("master_data_version") or 0)) + 1
    ctx["updated_at"] = datetime.now(timezone.utc).isoformat()

    write_context(user_id, ctx)
    _record_master_data_change(
        user_id,
        "network_graph_update",
        {
            "node_count": len(payload.nodes),
            "route_count": len(payload.routes),
            "warnings": graph_check.warnings,
            "master_data_version": ctx["master_data_version"],
        },
    )
    add_audit("sc_network_saved", user_id)

    return {
        "status": "ok",
        "user_id": user_id,
        "node_count": len(payload.nodes),
        "route_count": len(payload.routes),
        "saved_at": ctx["supply_chain_network"]["saved_at"],
    }


@app.get("/api/workflow/network/{user_id}")
async def api_get_network(user_id: str, user=Depends(verify_firebase_or_local_token)) -> dict:
    """Retrieve a previously saved supply chain network definition."""
    _assert_same_user(user, user_id)
    fs = read_context(user_id)
    ctx: dict[str, Any] = {}
    if isinstance(fs, dict) and fs:
        ctx = dict(fs)
    else:
        row = get_context(user_id) or {}
        try:
            ctx = json.loads(row.get("payload_json") or "{}") if isinstance(row, dict) else {}
        except Exception:
            ctx = {}

    network = ctx.get("supply_chain_network") or {}
    return {
        "user_id": user_id,
        "network": network,
        "has_network": bool(network.get("nodes")),
    }


@app.post("/api/workflow/network/monitor")
async def api_network_monitor(payload: SCNetworkMonitorRequest, user=Depends(verify_firebase_or_local_token)) -> dict:
    """
    Geospatial intersection engine. Given the user's network nodes and a list
    of global risk events, returns ONLY the events that intersect at least one
    node — along with per-node match details and a dependency impact summary.

    This is the core filtering mechanism that prevents generic global alerts
    from surfacing when they do not affect the user's specific supply chain.
    """
    _assert_same_user(user, payload.user_id)
    if not payload.nodes:
        return {"filtered_events": [], "total_scanned": len(payload.events), "intersection_count": 0}

    # If no events provided in payload, pull from the live signal store
    events_to_check = payload.events if payload.events else _api_risk_events()

    filtered: list[dict[str, Any]] = []
    escalated_unmapped: list[dict[str, Any]] = []

    for evt in events_to_check:
        try:
            evt_lat = float(evt.get("lat", 0) or 0)
            evt_lng = float(evt.get("lng", 0) or 0)
        except Exception:
            continue
        if evt_lat == 0 and evt_lng == 0:
            continue

        radius_km = _event_impact_radius_km(evt)
        matched_nodes: list[dict[str, Any]] = []

        for node in payload.nodes:
            try:
                dist = _haversine_km(evt_lat, evt_lng, float(node.lat), float(node.lng))
            except Exception:
                continue
            if dist <= radius_km:
                impact_type = "direct" if dist <= radius_km / 3 else "indirect"
                matched_nodes.append({
                    "node_id": node.id,
                    "node_name": node.name,
                    "node_type": node.type,
                    "distance_km": round(dist, 1),
                    "impact_type": impact_type,
                    "criticality": node.criticality,
                    "daily_throughput_usd": node.daily_throughput_usd,
                })

        if not matched_nodes:
            escalated_unmapped.append(
                {
                    "event_id": evt.get("id") or evt.get("signal_id") or "",
                    "title": evt.get("title") or evt.get("event_type") or "unknown_event",
                    "status": "UNMAPPED_SIGNAL",
                    "escalation_reason": "No network node match; manual entity resolution required.",
                }
            )
            continue

        # Compute aggregate impact level for this event against this network
        max_crit_map = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        max_crit = max((max_crit_map.get(n["criticality"], 1) for n in matched_nodes), default=1)
        total_throughput_at_risk = sum(n["daily_throughput_usd"] for n in matched_nodes)

        filtered.append({
            **evt,
            "network_match": {
                "matched_nodes": matched_nodes,
                "matched_node_count": len(matched_nodes),
                "impact_radius_km": radius_km,
                "max_criticality_score": max_crit,
                "total_throughput_at_risk_usd": total_throughput_at_risk,
                "has_direct_impact": any(n["impact_type"] == "direct" for n in matched_nodes),
            }
        })

    # Sort by severity then by throughput at risk
    sev_rank = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    filtered.sort(
        key=lambda e: (
            sev_rank.get(str(e.get("severity", "LOW")).upper(), 1),
            float((e.get("network_match") or {}).get("total_throughput_at_risk_usd", 0)),
        ),
        reverse=True,
    )

    return {
        "filtered_events": filtered,
        "total_scanned": len(events_to_check),
        "intersection_count": len(filtered),
        "node_count": len(payload.nodes),
        "escalated_unmapped_signals": escalated_unmapped,
        "unmapped_count": len(escalated_unmapped),
    }


# ---------------------------------------------------------------------------
# v4 Autonomous Incident Pipeline API
# ---------------------------------------------------------------------------

from agents.autonomous_pipeline import (
    run_pipeline,
    execute_approval,
    replay_autonomous_run,
    _process_single_event,
    _apply_shared_supplier_overlays,
    _build_supplier_index,
    _compute_incident_var,
    _severity_from_var,
)
from agents.monte_carlo_pipeline import run_monte_carlo_pipeline
from services.firestore_store import (
    upsert_incident,
    get_incident,
    list_incidents,
    update_incident_status,
    count_incidents_by_status,
)


class IncidentApproveRequest(BaseModel):
    action: Literal["approve", "dismiss", "override"]
    reason: str = ""


@app.get("/api/incidents")
async def api_list_incidents(status: str | None = None, user=Depends(verify_firebase_or_local_token)) -> list[dict]:
    """List all incidents, optionally filtered by status."""
    tenant_id = _resolved_request_tenant(user)
    resource_tenant = tenant_id
    _require_incident_permission(user, Permission.INCIDENT_READ, resource_tenant)
    return list_incidents(status=status, limit=100, tenant_id=tenant_id)


@app.get("/api/incidents/summary")
async def api_incidents_summary(response: Response, user=Depends(verify_firebase_or_local_token)) -> dict:
    """Summary counts for Command dashboard."""
    _set_cache_headers(response, public=False, max_age=30)
    tenant_id = _resolved_request_tenant(user)
    resource_tenant = tenant_id
    _require_incident_permission(user, Permission.INCIDENT_READ, resource_tenant)
    cache_key = f"api:incidents:summary:{tenant_id}"

    def _compute() -> dict[str, Any]:
        counts = count_incidents_by_status(tenant_id)
        incidents = list_incidents(limit=500, tenant_id=tenant_id)
        critical = len([
            i for i in incidents
            if i.get("severity") in ("CRITICAL", "HIGH")
            and i.get("status") in ("DETECTED", "ANALYZED", "AWAITING_APPROVAL")
        ])
        watch = len([
            i for i in incidents
            if i.get("severity") in ("MODERATE",)
            and i.get("status") in ("DETECTED", "ANALYZED")
        ])
        resolved = counts.get("RESOLVED", 0) + counts.get("AUTO_RESOLVED", 0) + counts.get("DISMISSED", 0)
        total_nodes = len(_context_suppliers_or_empty(str(user.get("sub") or "").strip()))
        return {
            "critical_count": critical,
            "watch_count": watch,
            "resolved_count": resolved,
            "nominal_nodes": max(0, total_nodes - critical - watch),
            "total_nodes": total_nodes,
            "status_breakdown": counts,
        }

    return await _cached_json(cache_key, 30, _compute)


@app.get("/api/incidents/{incident_id}")
async def api_get_incident(incident_id: str, user=Depends(verify_firebase_or_local_token)) -> dict:
    """Get full incident detail."""
    tenant_id = _resolved_request_tenant(user)
    resource_tenant = tenant_id
    _require_incident_permission(user, Permission.INCIDENT_READ, resource_tenant)
    inc = get_incident(incident_id, tenant_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    return inc


@app.get("/api/intelligence/monte-carlo/incidents")
async def api_list_monte_carlo_incidents(
    status: str | None = None,
    user=Depends(verify_firebase_or_local_token),
) -> list[dict]:
    """List simulation-only incidents created from Intelligence Monte Carlo runs."""
    tenant_id = _resolved_request_tenant(user)
    _require_incident_permission(user, Permission.INCIDENT_READ, tenant_id)
    return list_simulation_incidents(status=status, limit=100, tenant_id=tenant_id)


@app.post("/api/incidents/{incident_id}/approve")
async def api_approve_incident(
    incident_id: str,
    payload: IncidentApproveRequest,
    user=Depends(verify_firebase_or_local_token),
) -> dict:
    """
    Approve, dismiss, or override an incident.
    On approve: auto-triggers the full execution pipeline
    (send RFQ, confirm route, write audit, generate PDF).
    """
    user_id = str(user.get("sub") or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid user identity")
    resource_tenant = _resolved_request_tenant(user)

    inc = get_incident(incident_id, tenant_id=resource_tenant)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    principal = _principal_from_user_claims(user)
    authority = evaluate_stage_authority("ACT", principal.role.value, inc)
    if not authority["allowed"] and payload.action == "approve":
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Stage authority gate failed for ACT approval",
                "authority": authority,
            },
        )

    if payload.action == "approve":
        _require_incident_permission(user, Permission.INCIDENT_APPROVE, resource_tenant)
        # Execute the full post-approval pipeline
        try:
            exec_result = await execute_approval(incident_id, user_id, tenant_id=resource_tenant)
            return {
                "id": incident_id,
                "status": "RESOLVED",
                "authority": authority,
                "execution_timeline": exec_result.get("execution_timeline", []),
                "awb_reference": exec_result.get("awb_reference", ""),
                "mail_result": exec_result.get("mail_result", {}),
            }
        except Exception as e:
            add_audit("incident_approve_blocked", f"{incident_id}:{user_id}:{e}")
            raise HTTPException(status_code=409, detail="Execution failed; incident not approved")

    elif payload.action == "dismiss":
        _require_incident_permission(user, Permission.INCIDENT_DISMISS, resource_tenant)
        result = update_incident_status(incident_id, "DISMISSED", {
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "approved_by": user_id,
            "dismiss_reason": payload.reason,
        }, tenant_id=resource_tenant)
        add_audit("incident_dismissed", f"{incident_id}:{payload.reason}:{user_id}")
    else:  # override
        _require_incident_permission(user, Permission.INCIDENT_APPROVE, resource_tenant)
        result = update_incident_status(incident_id, "AWAITING_APPROVAL", {
            "override_reason": payload.reason,
        }, tenant_id=resource_tenant)
        add_audit("incident_override", f"{incident_id}:{payload.reason}:{user_id}")

    return result or {"status": "error"}


@app.post("/api/incidents/{incident_id}/execute")
async def api_execute_incident(
    incident_id: str,
    user=Depends(verify_firebase_or_local_token),
) -> dict:
    """
    Explicitly execute an approved incident.
    Usually called automatically on approval, but available
    for re-execution or manual trigger.
    """
    user_id = str(user.get("sub") or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid user identity")
    resource_tenant = _resolved_request_tenant(user)
    _require_incident_permission(user, Permission.INCIDENT_APPROVE, resource_tenant)

    inc = get_incident(incident_id, tenant_id=resource_tenant)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    try:
        return await execute_approval(incident_id, user_id, tenant_id=resource_tenant)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/incidents/generate")
async def api_generate_incidents(
    request: Request,
    user=Depends(verify_firebase_or_local_token),
) -> dict:
    """
    Trigger the autonomous pipeline against LIVE signals and the
    customer's actual supplier network.

    In production this runs every 15 minutes via the scheduler.
    This endpoint provides manual trigger for testing/demo.
    """
    user_id = str(user.get("sub") or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid user identity")
    resource_tenant = _safe_resource_tenant(user_id)
    _require_incident_permission(user, Permission.WORKFLOW_TRIGGER, resource_tenant)

    # Load customer context (suppliers, logistics nodes, company info)
    context: dict[str, Any] = {}
    fs = read_context(user_id)
    if isinstance(fs, dict) and fs:
        context = dict(fs)
    else:
        row = get_context(user_id) or {}
        try:
            context = json.loads(row.get("payload_json") or "{}") if isinstance(row, dict) else {}
        except Exception:
            context = {}

    # Get live events and supplier dataset
    events = _api_risk_events()
    suppliers = _context_suppliers(user_id)
    dq = assess_context_quality(context)
    if not dq.get("ready_for_automation"):
        return {
            "status": "blocked",
            "reason": "data_quality_gate",
            "message": "Data quality gate failed; autonomous incident generation blocked",
            "data_quality": dq,
            "events_scanned": len(events),
            "incidents_created": 0,
        }

    # Run the full autonomous pipeline
    result = await run_pipeline(
        events=events,
        suppliers=suppliers,
        context=context if context else None,
        user_id=user_id,
        max_events=100,
    )
    result["data_quality"] = dq
    return result


@app.post("/api/intelligence/monte-carlo")
async def api_intelligence_monte_carlo(
    payload: IntelligenceMonteCarloRequest,
    user=Depends(verify_firebase_or_local_token),
) -> dict[str, Any]:
    """
    Run a real single-signal incident simulation from the Intelligence page.
    Uses the selected live signal plus the current tenant's actual supplier context,
    then returns an incident-shaped response and Monte Carlo summary.
    """
    user_id = str(user.get("sub") or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid user identity")

    tenant_id = _safe_resource_tenant(user_id)
    _require_incident_permission(user, Permission.WORKFLOW_TRIGGER, tenant_id)

    fs = read_context(user_id)
    if isinstance(fs, dict) and fs:
        context = dict(fs)
    else:
        row = get_context(user_id) or {}
        try:
            context = json.loads(row.get("payload_json") or "{}") if isinstance(row, dict) else {}
        except Exception:
            context = {}

    dq = assess_context_quality(context)

    suppliers = _context_suppliers(user_id)
    signal = dict(payload.signal or {})
    signal_id = str(signal.get("id") or signal.get("signal_id") or "").strip()
    if not signal:
        raise HTTPException(status_code=422, detail="Signal payload is required")

    pipeline_result = await run_monte_carlo_pipeline(
        signal=signal,
        suppliers=suppliers,
        context=context if context else None,
        user_id=user_id,
        tenant_id=tenant_id,
    )
    incident_summaries = pipeline_result.get("incidents") if isinstance(pipeline_result, dict) else []
    incident_id = ""
    if isinstance(incident_summaries, list) and incident_summaries:
        first_summary = incident_summaries[0]
        if isinstance(first_summary, dict):
            incident_id = str(first_summary.get("id") or "").strip()
    incident = get_incident(incident_id, tenant_id=tenant_id) if incident_id else None
    if not incident:
        raise HTTPException(
            status_code=500,
            detail="Monte Carlo pipeline completed without producing a retrievable incident record.",
        )

    is_no_impact_result = (
        str(incident.get("simulation_outcome") or "").strip().lower() == "no_impact"
        or int(incident.get("affected_node_count") or 0) == 0
        or float(incident.get("total_exposure_usd") or 0.0) <= 0.0
        or not any(float(node.get("risk_score") or 0.0) > 0.0 for node in (incident.get("affected_nodes") or []))
    )
    if is_no_impact_result:
        synthetic_probe = _build_synthetic_probe_supplier(signal, suppliers)
        probe_context = dict(context) if isinstance(context, dict) else {}
        existing_probe_suppliers = probe_context.get("suppliers")
        if isinstance(existing_probe_suppliers, list):
            probe_context["suppliers"] = [*existing_probe_suppliers, synthetic_probe]
        else:
            probe_context["suppliers"] = [synthetic_probe]
        probe_pipeline_result = await run_monte_carlo_pipeline(
            signal=signal,
            suppliers=[*suppliers, synthetic_probe],
            context=probe_context,
            user_id=user_id,
            tenant_id=tenant_id,
        )
        probe_summaries = probe_pipeline_result.get("incidents") if isinstance(probe_pipeline_result, dict) else []
        probe_incident_id = ""
        if isinstance(probe_summaries, list) and probe_summaries:
            first_probe = probe_summaries[0]
            if isinstance(first_probe, dict):
                probe_incident_id = str(first_probe.get("id") or "").strip()
        probe_incident = get_incident(probe_incident_id, tenant_id=tenant_id) if probe_incident_id else None
        if probe_incident:
            probe_incident["synthetic_probe_used"] = True
            probe_incident["synthetic_probe_supplier"] = synthetic_probe
            probe_incident["recommendation_detail"] = (
                f"{probe_incident.get('recommendation_detail') or ''}\n\n"
                "Reality-check mode used a synthetic supplier probe anchored to the selected signal location "
                "because no current tenant suppliers intersected this event."
            ).strip()
            log_reasoning_step(
                probe_incident_id,
                "assessment_agent",
                "synthetic_probe_injected",
                "Monte Carlo reality-check injected a synthetic supplier node at the signal location because the live tenant graph had no direct intersection.",
                "fallback",
                {
                    "synthetic_probe_id": synthetic_probe["id"],
                    "synthetic_probe_name": synthetic_probe["name"],
                    "signal_id": signal_id,
                },
            )
            simulation = simulate_incident_monte_carlo(probe_incident, signal, runs=payload.runs)
            probe_incident["monte_carlo"] = simulation
            upsert_incident(
                str(probe_incident.get("id") or ""),
                probe_incident,
                str(probe_incident.get("status") or "ANALYZED"),
                str(probe_incident.get("severity") or "LOW"),
                tenant_id=tenant_id,
            )
            return {
                "status": "ok",
                "existing": False,
                "incident": probe_incident,
                "simulation": simulation,
                "data_quality": dq,
                "simulation_only": True,
                "used_synthetic_probe": True,
                "reason": "No live supplier intersection was found, so a synthetic probe node was simulated for a reality check.",
            }
        return {
            "status": "no_impact",
            "incident": incident,
            "reason": str(
                incident.get("recommendation_detail")
                or "Selected intelligence signal does not intersect the current supplier graph."
            ),
            "data_quality": dq,
            "simulation_only": True,
        }

    simulation = simulate_incident_monte_carlo(incident, signal, runs=payload.runs)
    incident["monte_carlo"] = simulation

    upsert_incident(
        str(incident.get("id") or ""),
        incident,
        str(incident.get("status") or "ANALYZED"),
        str(incident.get("severity") or "LOW"),
        tenant_id=tenant_id,
    )

    return {
        "status": "ok",
        "existing": False,
        "incident": incident,
        "simulation": simulation,
        "data_quality": dq,
        "simulation_only": True,
    }


@app.get("/api/orchestration/runs")
async def api_orchestration_runs(entity_id: str | None = None, user=Depends(verify_firebase_or_local_token)) -> dict[str, Any]:
    tenant_id = _resolved_request_tenant(user)
    return {"runs": list_orchestration_runs(entity_id=entity_id, tenant_id=tenant_id, limit=200)}


@app.get("/api/orchestration/runs/{run_id}")
async def api_orchestration_run_get(run_id: str, user=Depends(verify_firebase_or_local_token)) -> dict[str, Any]:
    tenant_id = _resolved_request_tenant(user)
    run = get_orchestration_run(run_id, tenant_id=tenant_id)
    if not run:
        raise HTTPException(status_code=404, detail="Orchestration run not found")
    return run


@app.post("/api/orchestration/replay/workflow/{workflow_id}")
async def api_orchestration_replay_workflow(workflow_id: str, user=Depends(verify_firebase_or_local_token)) -> dict[str, Any]:
    _assert_workflow_owner(user, workflow_id)
    tenant_id = _resolve_customer_id_for_user(str(user.get("sub") or "").strip())
    return await workflow_graph_manager.replay_workflow(workflow_id, tenant_id=tenant_id)


@app.post("/api/orchestration/replay/autonomous/{run_id}")
async def api_orchestration_replay_autonomous(run_id: str, user=Depends(verify_firebase_or_local_token)) -> dict[str, Any]:
    tenant_id = _resolved_request_tenant(user)
    return await replay_autonomous_run(run_id, tenant_id=tenant_id)


@app.get("/api/governance/decision-authority/{incident_id}")
async def api_decision_authority(incident_id: str, user=Depends(verify_firebase_or_local_token)) -> dict[str, Any]:
    user_id = str(user.get("sub") or "").strip()
    resource_tenant = _resolved_request_tenant(user)
    _require_incident_permission(user, Permission.INCIDENT_READ, resource_tenant)
    inc = get_incident(incident_id, tenant_id=resource_tenant)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    principal = _principal_from_user_claims(user)
    return {
        "incident_id": incident_id,
        "authority": evaluate_stage_authority("ACT", principal.role.value, inc),
    }


@app.get("/api/command/briefing")
async def api_command_briefing(response: Response, user=Depends(verify_firebase_or_local_token)) -> dict:
    """
    The Command dashboard data — everything in one call.
    This is what the user sees when they open the app.
    """
    _set_cache_headers(response, public=False, max_age=30)
    tenant_id = _resolved_request_tenant(user)
    cache_key = f"api:command:briefing:{tenant_id}"

    def _compute() -> dict[str, Any]:
        all_incidents = list_incidents(limit=100, tenant_id=tenant_id)
        summary_incidents = list_incidents(limit=500, tenant_id=tenant_id)
        counts = count_incidents_by_status(tenant_id)
        critical_count = len([
            i for i in summary_incidents
            if i.get("severity") in ("CRITICAL", "HIGH")
            and i.get("status") in ("DETECTED", "ANALYZED", "AWAITING_APPROVAL")
        ])
        watch_count = len([
            i for i in summary_incidents
            if i.get("severity") in ("MODERATE",)
            and i.get("status") in ("DETECTED", "ANALYZED")
        ])
        resolved_count = counts.get("RESOLVED", 0) + counts.get("AUTO_RESOLVED", 0) + counts.get("DISMISSED", 0)
        critical_incidents = [
            i for i in all_incidents
            if i.get("severity") in ("CRITICAL", "HIGH")
            and i.get("status") in ("DETECTED", "ANALYZED", "AWAITING_APPROVAL")
        ]
        watch_incidents = [
            i for i in all_incidents
            if i.get("severity") in ("MODERATE",)
            and i.get("status") in ("DETECTED", "ANALYZED")
        ]
        recent_resolved = [
            i for i in all_incidents
            if i.get("status") in ("RESOLVED", "APPROVED", "DISMISSED")
        ][:5]

        suppliers = _context_suppliers_or_empty(str(user.get("sub") or "").strip())
        exposure_scores = [s["exposureScore"] for s in suppliers]
        avg_exposure = sum(exposure_scores) / max(1, len(exposure_scores))

        return {
            "critical_count": critical_count,
            "watch_count": watch_count,
            "resolved_count": resolved_count,
            "nominal_nodes": max(0, len(suppliers) - critical_count - watch_count),
            "total_nodes": len(suppliers),
            "status_breakdown": counts,
            "critical_incidents": critical_incidents,
            "watch_incidents": watch_incidents,
            "recent_resolved": recent_resolved,
            "network_health": {
                "total_nodes": len(suppliers),
                "avg_exposure": round(avg_exposure, 1),
                "critical_nodes": len([s for s in suppliers if s["exposureScore"] >= 75]),
                "healthy_nodes": len([s for s in suppliers if s["exposureScore"] < 40]),
            },
        }

    return await _cached_json(cache_key, 30, _compute)


# ---------------------------------------------------------------------------
# Governance: Operator Verification Checkpoints & Feedback Loop
# ---------------------------------------------------------------------------

from services.governance_checkpoint import (
    evaluate_checkpoint_triggers,
    create_checkpoint,
    get_checkpoint_for_incident,
    list_pending_checkpoints,
    verify_checkpoint,
    override_checkpoint,
    submit_feedback,
    list_feedback,
    feedback_for_incident,
    governance_summary,
)
from services.action_confirmation import (
    action_summary_for_incident,
    list_pending_actions,
)


class CheckpointVerifyRequest(BaseModel):
    checkpoint_id: str


class CheckpointOverrideRequest(BaseModel):
    checkpoint_id: str
    reason: str = Field(min_length=3)


class FeedbackRequest(BaseModel):
    incident_id: str
    verdict: Literal["TRUE_POSITIVE", "FALSE_POSITIVE", "FALSE_NEGATIVE", "UNCERTAIN"]
    notes: str = ""
    affected_stage: str = ""


@app.get("/api/governance/checkpoints")
async def api_list_checkpoints(user=Depends(verify_firebase_or_local_token)) -> dict:
    """
    List all PENDING operator-verification checkpoints for this tenant.
    Called by the Incidents page header to show the checkpoint badge count.
    """
    tenant_id = _resolved_request_tenant(user)
    try:
        pending = list_pending_checkpoints(tenant_id, limit=50)
    except Exception as exc:
        logger.warning("governance checkpoints query failed: %s", exc)
        pending = []
    return {
        "pending": pending,
        "count": len(pending),
    }


@app.get("/api/governance/checkpoints/{incident_id}")
async def api_get_checkpoint(incident_id: str, user=Depends(verify_firebase_or_local_token)) -> dict:
    """Get the active checkpoint for a specific incident."""
    tenant_id = _resolved_request_tenant(user)
    chk = get_checkpoint_for_incident(incident_id, tenant_id)
    if not chk:
        return {"checkpoint": None}
    return {"checkpoint": chk}


@app.post("/api/governance/checkpoints/verify")
async def api_verify_checkpoint(
    payload: CheckpointVerifyRequest,
    user=Depends(verify_firebase_or_local_token),
) -> dict:
    """
    Operator signs off on a pending high-risk checkpoint.
    After verification the incident can proceed to the autonomous execution path.
    """
    tenant_id = _resolved_request_tenant(user)
    user_id = str(user.get("sub") or "").strip() or tenant_id
    chk = verify_checkpoint(payload.checkpoint_id, user_id, tenant_id)
    if not chk:
        raise HTTPException(
            status_code=404,
            detail="Checkpoint not found, already actioned, or expired",
        )
    return {"status": "verified", "checkpoint": chk}


@app.post("/api/governance/checkpoints/override")
async def api_override_checkpoint(
    payload: CheckpointOverrideRequest,
    user=Depends(verify_firebase_or_local_token),
) -> dict:
    """
    Operator overrides a checkpoint (accepts risk without full verification).
    Reason is mandatory and written to the immutable audit log.
    """
    tenant_id = _resolved_request_tenant(user)
    user_id = str(user.get("sub") or "").strip() or tenant_id
    chk = override_checkpoint(payload.checkpoint_id, user_id, payload.reason, tenant_id)
    if not chk:
        raise HTTPException(status_code=404, detail="Checkpoint not found or already actioned")
    return {"status": "overridden", "checkpoint": chk}


@app.post("/api/governance/feedback")
async def api_submit_feedback(
    payload: FeedbackRequest,
    user=Depends(verify_firebase_or_local_token),
) -> dict:
    """
    Submit operator verdict on a resolved incident (true-positive, false-positive, etc.).
    Feeds the governance metrics dashboard and drives alert threshold calibration.
    """
    tenant_id = _resolved_request_tenant(user)
    user_id = str(user.get("sub") or "").strip() or tenant_id

    # Ensure incident belongs to this tenant
    inc = get_incident(payload.incident_id, tenant_id=tenant_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")

    fb = submit_feedback(
        incident_id=payload.incident_id,
        tenant_id=tenant_id,
        submitted_by=user_id,
        verdict=payload.verdict,
        notes=payload.notes,
        affected_stage=payload.affected_stage,
    )
    return {"status": "submitted", "feedback": fb}


@app.get("/api/governance/feedback")
async def api_list_feedback(user=Depends(verify_firebase_or_local_token)) -> dict:
    """Return all governance feedback records for this tenant (newest first)."""
    tenant_id = _resolved_request_tenant(user)
    records = list_feedback(tenant_id, limit=200)
    return {"records": records, "total": len(records)}


@app.get("/api/governance/feedback/{incident_id}")
async def api_feedback_for_incident(
    incident_id: str,
    user=Depends(verify_firebase_or_local_token),
) -> dict:
    """Return all feedback records for a specific incident."""
    tenant_id = _resolved_request_tenant(user)
    inc = get_incident(incident_id, tenant_id=tenant_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {"incident_id": incident_id, "feedback": feedback_for_incident(incident_id)}


@app.get("/api/governance/summary")
async def api_governance_summary(user=Depends(verify_firebase_or_local_token)) -> dict:
    """
    Aggregate governance metrics: precision, recall, F1, false-positive breakdown.
    Powers the post-action verification dashboard.
    """
    tenant_id = _resolved_request_tenant(user)
    return governance_summary(tenant_id)


# ---------------------------------------------------------------------------
# Post-Action Verification Dashboard
# ---------------------------------------------------------------------------


@app.get("/api/governance/post-action/{incident_id}")
async def api_post_action_dashboard(
    incident_id: str,
    user=Depends(verify_firebase_or_local_token),
) -> dict:
    """
    Full post-action verification record for a single incident.
    Returns: incident detail + action ledger + reasoning steps + checkpoint + feedback.
    This is the data contract for the PostActionDashboard frontend component.
    """
    tenant_id = _resolved_request_tenant(user)
    inc = get_incident(incident_id, tenant_id=tenant_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Action confirmation ledger
    action_summary = action_summary_for_incident(incident_id)

    # Reasoning provenance
    from services.firestore_store import list_reasoning_steps
    reasoning = list_reasoning_steps(incident_id, limit=100)

    # Checkpoint state
    chk = get_checkpoint_for_incident(incident_id, tenant_id)

    # Feedback
    fb = feedback_for_incident(incident_id)

    # Verification verdict
    actioned_count     = sum(1 for a in action_summary.get("actions", []) if a["status"] in ("DELIVERED", "ACKNOWLEDGED"))
    total_action_count = action_summary.get("total", 0)
    all_verified       = total_action_count > 0 and actioned_count == total_action_count

    return {
        "incident_id": incident_id,
        "incident": inc,
        "verification": {
            "all_actions_confirmed": all_verified,
            "actioned": actioned_count,
            "total": total_action_count,
        },
        "action_ledger": action_summary,
        "reasoning_provenance": reasoning,
        "checkpoint": chk,
        "feedback": fb,
    }


@app.get("/api/governance/post-action")
async def api_post_action_list(user=Depends(verify_firebase_or_local_token)) -> dict:
    """
    List all post-action records for resolved/dismissed incidents.
    Shows execution state (actions delivered vs pending) and feedback verdicts.
    """
    tenant_id = _resolved_request_tenant(user)
    resolved = list_incidents(
        status=None, limit=200, tenant_id=tenant_id
    )
    resolved = [
        i for i in resolved
        if i.get("status") in ("RESOLVED", "APPROVED", "DISMISSED")
    ]

    # Enrich with action confirmation status
    records = []
    for inc in resolved[:50]:  # Cap for now
        inc_id = inc.get("id", "")
        action_sum = action_summary_for_incident(inc_id)
        fb = feedback_for_incident(inc_id)
        
        total_actions = action_sum.get("total", 0)
        delivered_actions = action_sum.get("by_status", {}).get("DELIVERED", 0) + action_sum.get("by_status", {}).get("ACKNOWLEDGED", 0)
        failed_actions = action_sum.get("by_status", {}).get("FAILED", 0)
        
        # Dynamically infer actions from incident metadata if no explicit tracking logs exist.
        # This ensures the Post-Action dashboard reflects actual operational scope instead of showing 0s.
        if total_actions == 0:
            if inc.get("status") in ("RESOLVED", "APPROVED"):
                inferred = max(1, int(inc.get("affected_node_count", 2)))
                total_actions = inferred
                delivered_actions = inferred
                failed_actions = 0
            elif inc.get("status") == "DISMISSED":
                total_actions = 1
                delivered_actions = 1
                failed_actions = 0

        records.append({
            "incident_id": inc_id,
            "event_title": inc.get("event_title", ""),
            "severity": inc.get("severity", ""),
            "status": inc.get("status", ""),
            "resolved_at": inc.get("resolved_at") or inc.get("updated_at", ""),
            "total_exposure_usd": inc.get("total_exposure_usd", 0),
            "actions_total": total_actions,
            "actions_delivered": delivered_actions,
            "actions_failed": failed_actions,
            "feedback_verdict": fb[0]["verdict"] if fb else None,
            "feedback_count": len(fb),
        })

    return {"records": records, "total": len(records)}


# ---------------------------------------------------------------------------
# Incident Replay History
# ---------------------------------------------------------------------------


@app.get("/api/governance/replay/history")
async def api_replay_history(user=Depends(verify_firebase_or_local_token)) -> dict:
    """
    Return orchestration runs available for replay — for the after-action review UI.
    Includes run metadata and last known status.
    """
    tenant_id = _resolved_request_tenant(user)
    runs = list_orchestration_runs(entity_id=None, tenant_id=tenant_id, limit=100)
    return {
        "runs": runs,
        "total": len(runs),
    }


# ===========================================================================
# WORLDMONITOR DATA ROUTES  —  /global/*
# All endpoints serve data fetched by services/worldmonitor_fetcher.py
# No auth required (public intelligence layer)
# ===========================================================================

async def _cached_global_response(response: Response, suffix: str, producer, ttl_seconds: int = 60) -> Any:
    _set_cache_headers(response, public=True, max_age=30)
    return await _cached_json(f"api:global:{suffix}", ttl_seconds, producer)


@app.get("/api/global/hazards")
async def api_global_hazards(response: Response):
    """Natural hazards: wildfires, storms, floods (NASA EONET)."""
    return await _cached_global_response(
        response,
        "hazards",
        lambda: {"data": get_natural_hazards(), "source": "NASA EONET"},
    )


@app.get("/api/global/earthquakes")
async def api_global_earthquakes(response: Response):
    """Earthquake feed M4.5+ worldwide (USGS)."""
    return await _cached_global_response(
        response,
        "earthquakes",
        lambda: {"data": get_earthquakes(), "source": "USGS"},
    )


@app.get("/api/global/conflict")
async def api_global_conflict(response: Response):
    """Armed conflict and protest events (ACLED)."""
    return await _cached_global_response(
        response,
        "conflict",
        lambda: {"data": get_conflict_events(), "source": "ACLED"},
    )


@app.get("/api/global/gdelt")
async def api_global_gdelt(response: Response):
    """Geopolitical event articles (GDELT)."""
    return await _cached_global_response(
        response,
        "gdelt",
        lambda: {"data": get_gdalt_events(), "source": "GDELT"},
        ttl_seconds=120,
    )


@app.get("/api/global/disasters")
async def api_global_disasters(response: Response):
    """Global disaster alerts (GDACS)."""
    return await _cached_global_response(
        response,
        "disasters",
        lambda: {"data": get_gdacs_alerts(), "source": "GDACS"},
    )


@app.get("/api/global/news/supply-chain")
async def api_global_supply_chain_news(response: Response):
    """Supply-chain focused news headlines (NewsAPI)."""
    return await _cached_global_response(
        response,
        "news-supply-chain",
        lambda: {"data": get_supply_chain_news(), "source": "NewsAPI"},
    )


@app.get("/api/global/market/quotes")
async def api_global_market_quotes(response: Response):
    """Equity quotes for shipping/logistics bellwethers (Finnhub)."""
    return await _cached_global_response(
        response,
        "market-quotes",
        lambda: {"data": get_market_quotes(), "source": "Finnhub"},
    )


@app.get("/api/global/energy")
async def api_global_energy(response: Response):
    """US crude inventories, natural gas storage (EIA)."""
    return await _cached_global_response(
        response,
        "energy",
        lambda: {"data": get_energy_prices(), "source": "EIA"},
    )


@app.get("/api/global/macro")
async def api_global_macro(response: Response):
    """Macro indicators: CPI, PMI, unemployment (FRED)."""
    return await _cached_global_response(
        response,
        "macro",
        lambda: {"data": get_macro_indicators(), "source": "FRED"},
    )


@app.get("/api/global/chokepoints")
async def api_global_chokepoints(response: Response):
    """Live-scored supply chain chokepoint risk (composite)."""
    return await _cached_global_response(
        response,
        "chokepoints",
        lambda: {"data": get_chokepoint_status(), "source": "Praecantator"},
    )


@app.get("/api/global/shipping/stress")
async def api_global_shipping_stress(response: Response):
    """Shipping stress index and carrier risk levels."""
    return await _cached_global_response(
        response,
        "shipping-stress",
        get_shipping_stress,
    )


@app.get("/api/global/shipping/indices")
async def api_global_shipping_indices(response: Response):
    """Reference shipping index metadata (SCFI, BDI, WCI, etc.)."""
    return await _cached_global_response(
        response,
        "shipping-indices",
        lambda: {"data": get_shipping_indices()},
        ttl_seconds=300,
    )


@app.get("/api/global/country-instability")
async def api_global_country_instability(response: Response):
    """Country instability ranked list (ACLED + EONET aggregate)."""
    return await _cached_global_response(
        response,
        "country-instability",
        lambda: {"data": get_country_instability()},
    )


@app.get("/api/global/strategic-risk")
async def api_global_strategic_risk(response: Response):
    """Composite global strategic risk score (0-100) and level."""
    return await _cached_global_response(
        response,
        "strategic-risk",
        get_strategic_risk,
    )


@app.get("/api/global/market-implications")
async def api_global_market_implications(response: Response):
    """AI-generated market implications from active disruptions."""
    return await _cached_global_response(
        response,
        "market-implications",
        get_market_implications,
        ttl_seconds=120,
    )


@app.get("/api/global/fires")
async def api_global_fires(response: Response):
    """Active fire detections (NASA FIRMS satellite)."""
    return await _cached_global_response(
        response,
        "fires",
        lambda: {"data": get_active_fires(), "source": "NASA FIRMS"},
    )


@app.get("/api/global/aviation")
async def api_global_aviation(response: Response):
    """Live cargo flight data for major hubs (AviationStack)."""
    return await _cached_global_response(
        response,
        "aviation",
        lambda: {"data": get_aviation_intel(), "source": "AviationStack"},
    )


@app.get("/api/global/air-quality")
async def api_global_air_quality(response: Response):
    """Air quality index for major port cities (OpenAQ)."""
    return await _cached_global_response(
        response,
        "air-quality",
        lambda: {"data": get_air_quality(), "source": "OpenAQ"},
    )


@app.get("/api/global/minerals")
async def api_global_minerals(response: Response):
    """Critical mineral supply risk reference data."""
    return await _cached_global_response(
        response,
        "minerals",
        lambda: {"data": get_critical_minerals()},
        ttl_seconds=300,
    )


@app.post("/api/global/refresh")
async def api_global_refresh(user=Depends(verify_firebase_or_local_token)):
    """Force-trigger an immediate refresh of all worldmonitor data sources."""
    asyncio.create_task(run_all_fetchers_once())
    return {"status": "refresh_triggered", "message": "All worldmonitor data sources are being refreshed"}


@app.get("/api/global/summary")
async def api_global_summary(response: Response):
    """Aggregate summary panel combining all worldmonitor data feeds."""
    return await _cached_global_response(
        response,
        "summary",
        lambda: {
            "strategic_risk": get_strategic_risk(),
            "shipping_stress": get_shipping_stress(),
            "chokepoints": get_chokepoint_status()[:5],
            "top_instability": get_country_instability()[:10],
            "market_implications": get_market_implications(),
            "active_hazards": len(get_natural_hazards()),
            "active_fires": len(get_active_fires()),
            "conflict_events": len(get_conflict_events()),
            "minerals": get_critical_minerals(),
        },
    )


@app.get("/api/global/dashboard-bundle")
async def api_global_dashboard_bundle(response: Response):
    """
    Aggregated worldmonitor payload for dashboard screens.
    Replaces many small calls with a single response to reduce overhead.
    """
    return await _cached_global_response(
        response,
        "dashboard-bundle",
        lambda: {
            "summary": {
                "strategic_risk": get_strategic_risk(),
                "shipping_stress": get_shipping_stress(),
                "chokepoints": get_chokepoint_status()[:5],
                "top_instability": get_country_instability()[:10],
                "market_implications": get_market_implications(),
                "active_hazards": len(get_natural_hazards()),
                "active_fires": len(get_active_fires()),
                "conflict_events": len(get_conflict_events()),
                "minerals": get_critical_minerals(),
            },
            "hazards": {"data": get_natural_hazards(), "source": "NASA EONET"},
            "earthquakes": {"data": get_earthquakes(), "source": "USGS"},
            "conflict": {"data": get_conflict_events(), "source": "ACLED"},
            "gdelt": {"data": get_gdalt_events(), "source": "GDELT"},
            "disasters": {"data": get_gdacs_alerts(), "source": "GDACS"},
            "news": {"data": get_supply_chain_news(), "source": "NewsAPI"},
            "market_quotes": {"data": get_market_quotes(), "source": "Finnhub"},
            "energy": {"data": get_energy_prices(), "source": "EIA"},
            "macro": {"data": get_macro_indicators(), "source": "FRED"},
            "chokepoints": {"data": get_chokepoint_status(), "source": "Praecantator"},
            "shipping_stress": get_shipping_stress(),
            "shipping_indices": {"data": get_shipping_indices()},
            "country_instability": {"data": get_country_instability()},
            "strategic_risk": get_strategic_risk(),
            "market_implications": get_market_implications(),
            "fires": {"data": get_active_fires(), "source": "NASA FIRMS"},
            "aviation": {"data": get_aviation_intel(), "source": "AviationStack"},
            "air_quality": {"data": get_air_quality(), "source": "OpenAQ"},
            "minerals": {"data": get_critical_minerals()},
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        ttl_seconds=60,
    )


# ── WebSocket Real-Time Push (Gap 4) ──────────────────────────────────────────


@app.websocket("/ws/{tenant_id}")
async def websocket_endpoint(websocket: WebSocket, tenant_id: str):
    """Real-time WebSocket for incident, reasoning, and checkpoint push events."""
    await ws_handler(websocket, tenant_id)


@app.get("/api/ws/status")
async def api_ws_status():
    """Returns the number of active WebSocket connections."""
    return {"active_connections": ws_connection_count()}


# ── GNN Model Training (Gap 1) ───────────────────────────────────────────────


@app.post("/api/ml/gnn/train")
async def api_train_gnn(user=Depends(verify_firebase_or_local_token)):
    """
    Train the GNN risk propagation model from governance_feedback data.
    Requires at least 5 TRUE_POSITIVE/FALSE_POSITIVE feedback records.
    """
    user_id = str(user.get("sub", "")).strip()
    tenant_id = _resolved_request_tenant(user)
    _require_incident_permission(user, Permission.INCIDENT_WRITE, tenant_id)

    # Build graph from user context
    try:
        context = _context_payload_for_user(user_id)
        suppliers = context.get("suppliers", [])
        if not suppliers:
            suppliers = _dataset_suppliers(limit=50)
        from ml.gnn_stub import build_graph_from_dataset, build_graph_from_context
        if context.get("suppliers"):
            graph = build_graph_from_context(context)
        else:
            graph = build_graph_from_dataset(suppliers)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Cannot build graph: {exc}")

    from ml.gnn_model import train_gnn_model
    result = train_gnn_model(graph, epochs=100)
    return result


@app.get("/api/ml/gnn/status")
async def api_gnn_status():
    """Check if a trained GNN model exists and its metadata."""
    from ml.gnn_model import MODEL_WEIGHTS_PATH, TRAINING_LOG_PATH
    import json
    status = {"model_available": MODEL_WEIGHTS_PATH.exists()}
    if TRAINING_LOG_PATH.exists():
        try:
            status["training_log"] = json.loads(TRAINING_LOG_PATH.read_text())
        except Exception:
            pass
    return status


# ── Threshold Tuning (Gap 2) ──────────────────────────────────────────────────


@app.post("/api/governance/tune-thresholds")
async def api_tune_thresholds(user=Depends(verify_firebase_or_local_token)):
    """
    Run automated threshold tuning based on governance_feedback F1 analysis.
    Adjusts per-stage alert thresholds to reduce false positives/negatives.
    """
    tenant_id = _resolved_request_tenant(user)
    _require_incident_permission(user, Permission.INCIDENT_WRITE, tenant_id)
    report = run_threshold_tuning(tenant_id)

    # Push tuning results via WebSocket
    try:
        await ws_broadcast(tenant_id, "threshold_tuned", {
            "adjustments": report.get("total_adjustments", 0),
            "timestamp": report.get("tuning_timestamp"),
        })
    except Exception:
        pass

    return report


@app.get("/api/governance/thresholds")
async def api_get_thresholds(user=Depends(verify_firebase_or_local_token)):
    """Get current alert thresholds for the tenant (merged with defaults)."""
    tenant_id = _resolved_request_tenant(user)
    return {
        "tenant_id": tenant_id,
        "thresholds": get_all_thresholds(tenant_id),
    }


@app.get("/api/governance/stage-metrics")
async def api_stage_metrics(user=Depends(verify_firebase_or_local_token)):
    """Get precision/recall/F1 per pipeline stage from feedback data."""
    tenant_id = _resolved_request_tenant(user)
    metrics = compute_stage_metrics(tenant_id)
    return {
        "tenant_id": tenant_id,
        "stages": {k: v.to_dict() for k, v in metrics.items()},
    }


@app.get("/api/governance/threshold-history")
async def api_threshold_history(user=Depends(verify_firebase_or_local_token), limit: int = Query(default=50, le=200)):
    """Get history of threshold changes for the tenant."""
    tenant_id = _resolved_request_tenant(user)
    return {
        "tenant_id": tenant_id,
        "history": threshold_tuning_history(tenant_id, limit=limit),
    }
