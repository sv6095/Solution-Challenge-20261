from __future__ import annotations

import io
import json
import secrets
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query
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
from pdf.certificate import generate_audit_certificate
from scheduler.signal_poll import start_signal_scheduler
from ml.xgboost_model import MODEL_PATH, train_and_save_model
from services.firestore import read_workflow_event, write_context, write_workflow_event
from services.data_registry import disruption_snapshot, registry
from services.firebase_auth import verify_firebase_or_local_token
from services.local_store import (
    add_audit,
    create_rfq_event,
    create_user,
    get_user_by_email,
    get_workflow_event,
    init_local_store,
    insert_signal,
    list_audit,
    list_rfq_events,
    list_signals,
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
    create_rfq_event(rfq_id, str(payload.get("user_id") or "api-public"), recipient, subject, body, status)
    return {
        "id": rfq_id,
        "supplier": recipient,
        "eventTrigger": subject,
        "dateSent": datetime.now(timezone.utc).date().isoformat(),
        "status": status.title(),
    }


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


@app.get("/api/settings/profile")
async def api_settings_profile() -> dict:
    return {"name": "", "email": "", "company": "", "role": "Admin"}


@app.patch("/api/settings/profile")
async def api_settings_profile_patch(payload: dict) -> dict:
    current = await api_settings_profile()
    current.update(payload)
    return current


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
