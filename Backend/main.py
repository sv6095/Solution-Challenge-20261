from __future__ import annotations

import io
import json
import secrets
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from starlette.responses import Response

from currency.frankfurter import convert_cost, get_exchange_rate
from currency.risk_index import compute_currency_risk_index
from currency.worldbank import get_inflation_rate
from agents.assessment_agent import run_assessment
from agents.rfq_agent import draft_rfq
from agents.routing_agent import run_routing
from pdf.certificate import generate_audit_certificate, generate_workflow_audit_report_pdf
from scheduler.signal_poll import start_signal_scheduler
from ml.xgboost_model import MODEL_PATH, train_and_save_model
from services.llm_analysis import generate_workflow_analysis
from services.firestore import read_context, read_workflow_event, write_context, write_workflow_event
from services.data_registry import disruption_snapshot, registry
from services.firebase_auth import verify_firebase_or_local_token
from services.local_store import (
    add_audit,
    create_rfq_event,
    create_rfq_event_linked,
    create_user,
    get_audit,
    get_context,
    get_user_by_email,
    get_workflow_report,
    get_workflow_event,
    init_local_store,
    insert_signal,
    list_audit,
    list_rfq_events,
    list_rfq_messages,
    add_rfq_message,
    update_rfq_status,
    list_signals,
    list_workflow_reports,
    upsert_workflow_report,
    upsert_context,
    upsert_workflow_event,
)
from services.mailer import send_rfq_email
from services.security import hash_password, mint_access_token, mint_refresh_token, verify_password

app = FastAPI(title="SupplyShield API", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
init_local_store()
start_signal_scheduler()


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


class WorkflowStateUpdate(BaseModel):
    stage: Literal["detect", "assess", "decide", "act", "audit"]
    confidence: float = Field(ge=0.0, le=1.0)


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    company_name: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


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


class WorkflowAssessRequest(BaseModel):
    workflow_id: str
    event_type: str
    severity: float = Field(ge=0, le=10)
    suppliers: list[dict] = []


class WorkflowAnalyzeRequest(BaseModel):
    event: dict = {}
    suppliers: list[dict] = []
    assessment: dict | None = None


class WorkflowReportStageUpsert(BaseModel):
    workflow_id: str
    stage: Literal["detect", "assess", "decide", "act", "audit"]
    payload: dict = {}


class RFQDraftRequest(BaseModel):
    user_id: str = "local-user"
    recipient: str
    event_context: str
    quantities: str


class RFQSendRequest(BaseModel):
    user_id: str = "local-user"
    recipient: str
    subject: str
    body: str


class TrainModelResponse(BaseModel):
    model_path: str
    rows: int


def _resolve_point(c: Coordinates) -> tuple[float, float]:
    if c.lat is not None and c.lng is not None:
        return c.lat, c.lng
    port = registry.find_port_by_city_country(c.city, c.country)
    if port:
        return port.lat, port.lng
    raise HTTPException(status_code=422, detail="Provide lat/lng or resolvable city+country in Dataset/ports.json")


def _scrub_context(payload: OnboardingRequest) -> dict[str, Any]:
    data = payload.model_dump()
    data["gmail_oauth_token_present"] = bool(data.pop("gmail_oauth_token", None))
    if data.get("slack_webhook"):
        data["slack_webhook"] = "***redacted***"
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    return data


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
        events.append(
            {
                "id": str(sig.get("id") or sig.get("signal_id") or f"evt_{idx+1}"),
                "title": str(sig.get("title") or sig.get("event_type") or "Disruption signal"),
                "severity": severity_label,
                "description": str(sig.get("description") or sig.get("location") or "Signal-derived event"),
                "timestamp": str(sig.get("created_at") or datetime.now(timezone.utc).isoformat()),
                "analyst": str(sig.get("source") or "signal-pipeline"),
                "lat": float(sig.get("lat", 0) or 0),
                "lng": float(sig.get("lng", 0) or 0),
                "region": str(sig.get("region") or sig.get("location") or "Unknown"),
                "url": _normalized_url(str(sig.get("url") or "")),
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


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dataset": disruption_snapshot(),
        "fallbacks": {"state_store": "sqlite"},
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
    user = create_user(str(uuid4()), payload.email, hash_password(payload.password), payload.company_name)
    add_audit("auth_register", user["user_id"])
    return {"user_id": user["user_id"], "email": user["email"], "company_name": user["company_name"]}


@app.post("/auth/login")
async def auth_login(payload: LoginRequest) -> dict:
    user = get_user_by_email(payload.email)
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {
        "user_id": user["user_id"],
        "access_token": mint_access_token(user["user_id"], user["email"]),
        "refresh_token": mint_refresh_token(user["user_id"]),
    }


# ---------------------------------------------------------------------------
# Frontend compatibility endpoints under /api/auth/*
# ---------------------------------------------------------------------------


@app.post("/api/auth/register")
async def api_auth_register(payload: RegisterRequest) -> dict:
    return await auth_register(payload)


@app.post("/api/auth/login")
async def api_auth_login(payload: LoginRequest) -> dict:
    return await auth_login(payload)


@app.post("/auth/google")
async def auth_google(payload: GoogleAuthRequest) -> dict:
    email = payload.email or f"google_user_{secrets.token_hex(4)}@example.com"
    user = get_user_by_email(email) or create_user(str(uuid4()), email, hash_password(payload.id_token), "Google User")
    return {"user_id": user["user_id"], "access_token": mint_access_token(user["user_id"], user["email"]), "provider": "google"}


@app.post("/onboarding/complete")
async def onboarding_complete(payload: OnboardingRequest, user=Depends(verify_firebase_or_local_token)) -> dict:
    if user.get("sub") != payload.user_id and user.get("source") != "bypass":
        raise HTTPException(status_code=403, detail="Cannot write another user's context")
    result = write_context(payload.user_id, _scrub_context(payload))
    add_audit("onboarding_complete", payload.user_id)
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
    result = run_assessment(payload.workflow_id, payload.event_type, payload.severity, payload.suppliers)
    write_workflow_event(payload.workflow_id, "assess", result["confidence_score"])
    add_audit("workflow_assess", payload.workflow_id)
    converted = await convert_cost(float(result["financial_exposure_usd"]), "USD")
    return {
        **result,
        "financial_exposure": converted,
        "assessed_by": user.get("sub", "local"),
    }


@app.post("/workflow/routes")
async def workflow_routes(payload: RouteRequest, user=Depends(verify_firebase_or_local_token)) -> dict:
    origin_lat, origin_lng = _resolve_point(payload.origin)
    dest_lat, dest_lng = _resolve_point(payload.destination)
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
    add_audit("workflow_routes", user.get("sub", "local"))
    return result


@app.post("/workflow/rfq/draft")
async def rfq_draft(payload: RFQDraftRequest, user=Depends(verify_firebase_or_local_token)) -> dict:
    drafted = draft_rfq(payload.recipient, payload.event_context, payload.quantities)
    drafted["estimated_cost"] = await convert_cost(5000.0, "USD")
    drafted["generated_by"] = user.get("sub", "local")
    return drafted


@app.post("/workflow/rfq/send")
async def rfq_send(payload: RFQSendRequest, user=Depends(verify_firebase_or_local_token)) -> dict:
    rfq_id = f"rfq_{uuid4().hex[:10]}"
    create_rfq_event(rfq_id, payload.user_id, payload.recipient, payload.subject, payload.body, "sent")
    mail_result = send_rfq_email(payload.recipient, payload.subject, payload.body)
    add_audit("rfq_sent", rfq_id)
    return {"status": "sent", "rfq_id": rfq_id, "mail": mail_result, "sent_by": user.get("sub", "local")}


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
    rows = _dataset_suppliers(limit=100)
    return [{"supplier_id": r["id"], "name": r["name"], "score": r["exposureScore"]} for r in rows]


@app.get("/exposure/{supplier_id}")
async def exposure_one(supplier_id: str, user=Depends(verify_firebase_or_local_token)) -> dict:
    rows = _dataset_suppliers(limit=300)
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
    stored = read_workflow_event(workflow_id)
    if stored:
        return stored
    return write_workflow_event(workflow_id, stage, 0.5)


@app.post("/workflow/state/{workflow_id}")
async def workflow_state_update(workflow_id: str, payload: WorkflowStateUpdate, user=Depends(verify_firebase_or_local_token)) -> dict:
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
async def api_dashboard_kpis() -> dict:
    suppliers = _dataset_suppliers(limit=200)
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
async def api_dashboard_suppliers(limit: int = 5) -> list[dict]:
    return _dataset_suppliers(limit=limit)


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
async def api_risks_suppliers(tier: str | None = None, minScore: float | None = None, maxScore: float | None = None) -> list[dict]:
    suppliers = await api_dashboard_suppliers(limit=5000)
    filtered = suppliers
    if tier:
        filtered = [s for s in filtered if s["tier"] == tier]
    if minScore is not None:
        filtered = [s for s in filtered if s["exposureScore"] >= float(minScore)]
    if maxScore is not None:
        filtered = [s for s in filtered if s["exposureScore"] <= float(maxScore)]
    return filtered


@app.get("/api/exposure/summary")
async def api_exposure_summary() -> dict:
    suppliers = _dataset_suppliers(limit=5000)
    avg = sum(s["exposureScore"] for s in suppliers) / max(1, len(suppliers))
    critical = len([s for s in suppliers if s["exposureScore"] >= 75])
    return {"avgScore": round(avg, 1), "criticalNodes": critical, "totalMonitored": len(suppliers)}


@app.get("/api/exposure/suppliers")
async def api_exposure_suppliers() -> list[dict]:
    return await api_dashboard_suppliers(limit=5000)


@app.post("/api/workflow/routes")
async def api_workflow_routes(payload: RouteRequest) -> dict:
    return await workflow_routes(payload, {"sub": "api-public"})


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
async def api_rfq_create(payload: dict) -> dict:
    rfq_id = f"rfq_{uuid4().hex[:8]}"
    recipient = str(payload.get("supplier") or payload.get("recipient") or "unknown@example.com")
    subject = str(payload.get("eventTrigger") or payload.get("subject") or "RFQ")
    body = str(payload.get("body") or "")
    status = str(payload.get("status") or "Draft").lower()
    create_rfq_event_linked(
        rfq_id,
        str(payload.get("user_id") or "api-public"),
        str(payload.get("workflowId") or payload.get("workflow_id") or "") or None,
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
async def api_workflow_analyze(payload: WorkflowAnalyzeRequest) -> dict:
    result = await generate_workflow_analysis(event=payload.event, suppliers=payload.suppliers, assessment=payload.assessment)
    return {"provider": result.provider, "analysis": result.text}


@app.post("/api/workflow/report")
async def api_workflow_report_upsert(payload: WorkflowReportStageUpsert) -> dict:
    existing = get_workflow_report(payload.workflow_id) or {"workflow_id": payload.workflow_id}
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


@app.get("/api/workflow/report/{workflow_id}")
async def api_workflow_report_get(workflow_id: str) -> dict:
    report = get_workflow_report(workflow_id)
    if not report:
        raise HTTPException(status_code=404, detail="Not Found")
    return report


@app.get("/api/workflow/report/{workflow_id}/pdf")
async def api_workflow_report_pdf(workflow_id: str) -> Response:
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
    content = generate_workflow_audit_report_pdf(report, requested_by="system")
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
    return [
        {
            "id": f"src_{idx+1}",
            "name": name,
            "active": True,
            "lastFetch": latest_by_source.get(name, ""),
            "recordCount": count,
            "latencyMs": None,
        }
        for idx, (name, count) in enumerate(sorted(by_source.items(), key=lambda kv: kv[1], reverse=True))
    ]


@app.get("/api/audit")
async def api_audit() -> list[dict]:
    rows = list_audit(limit=200)
    return [
        {
            "id": f"aud_{row['id']}",
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
async def api_settings_profile(request: Request) -> dict:
    user_id = str(request.headers.get("x-user-id") or "local-user")
    # Prefer Firestore if enabled, else SQLite.
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
    }


@app.patch("/api/settings/profile")
async def api_settings_profile_patch(payload: dict, request: Request) -> dict:
    user_id = str(request.headers.get("x-user-id") or payload.get("user_id") or "local-user")

    # Load existing context (Firestore preferred, then SQLite) and merge.
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

    # Persist (SQLite always, Firestore if enabled).
    write_context(user_id, ctx)
    add_audit("settings_profile_update", user_id)
    return await api_settings_profile(request)


@app.get("/api/settings/billing")
async def api_settings_billing() -> dict:
    workflows_used = len([r for r in list_audit(limit=1000) if str(r.get("action", "")).startswith("workflow_")])
    rfqs_sent = len([r for r in list_rfq_events(limit=1000) if str(r.get("status", "")).lower() == "sent"])
    suppliers_used = len(_dataset_suppliers(limit=1000))
    return {
        "plan": "Usage",
        "monthlyRate": 0,
        "workflowRunsUsed": workflows_used,
        "workflowRunsLimit": 1000,
        "rfqsSent": rfqs_sent,
        "suppliersUsed": suppliers_used,
        "suppliersLimit": max(200, suppliers_used),
    }


@app.post("/api/onboarding/complete")
async def api_onboarding_complete(payload: OnboardingRequest) -> dict:
    # Local/demo-friendly endpoint (frontend does not send auth headers yet).
    return await onboarding_complete(payload, {"sub": payload.user_id, "source": "bypass"})


@app.get("/api/contexts/{user_id}")
async def api_context_get(user_id: str) -> dict:
    # Prefer Firestore if enabled; fallback to SQLite.
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
async def api_onboarding_status(user_id: str) -> dict:
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
