from __future__ import annotations

import asyncio
import os
import hashlib
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from agents.citation_tracker import enrich_signal_item, mark_corroborations
from agents.signal_agent import fetch_gdelt, fetch_gnews, fetch_nasa_eonet, fetch_newsapi
from agents.extended_signal_agent import (
    fetch_gdacs,
    fetch_usgs_earthquakes,
    fetch_nasa_firms,
    fetch_reliefweb,
    fetch_acled,
    fetch_gps_interference,
    fetch_ofac_sanctions,
    fetch_portwatch_disruptions,
    fetch_portwatch_transit_alerts,
    fetch_social_sentiment,
    fetch_wto_trade_signals,
)
from services.firestore_store import add_audit, purge_archived_signals, replace_active_signals
from services.secret_manager import get_secret

_scheduler: BackgroundScheduler | None = None


def _derive_country_instability_signals(items: list[dict]) -> list[dict]:
    grouped: dict[str, dict[str, object]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        source_category = str(item.get("source_category") or "").strip().lower()
        if source_category not in {"geopolitical", "regulatory", "maritime", "trade"}:
            continue
        location = str(item.get("location") or "").strip()
        if not location or location.lower() == "global":
            continue
        country = location.split(",")[-1].strip()
        if not country:
            continue
        bucket = grouped.setdefault(country, {"severity_total": 0.0, "count": 0, "sources": set()})
        bucket["severity_total"] = float(bucket["severity_total"]) + float(item.get("severity") or 0.0)
        bucket["count"] = int(bucket["count"]) + 1
        cast_sources = bucket["sources"]
        if isinstance(cast_sources, set):
            cast_sources.add(str(item.get("source") or "unknown"))

    derived: list[dict] = []
    for country, bucket in grouped.items():
        count = int(bucket["count"])
        if count == 0:
            continue
        sources = bucket["sources"] if isinstance(bucket["sources"], set) else set()
        avg_severity = float(bucket["severity_total"]) / count
        source_bonus = min(25.0, len(sources) * 6.5)
        cii_score = max(20.0, min(100.0, (avg_severity * 8.0) + source_bonus + (count * 2.0)))
        if cii_score < 45.0:
            continue
        derived.append(
            {
                "id": f"cii_{country.lower().replace(' ', '_')}",
                "event_type": "country_instability_index",
                "title": f"Country instability index elevated: {country}",
                "description": (
                    f"Composite instability score {cii_score:.0f}/100 derived from {count} active "
                    f"signals across {len(sources)} source streams."
                ),
                "location": country,
                "severity": min(10.0, max(4.5, cii_score / 10.0)),
                "lat": 0.0,
                "lng": 0.0,
                "source": "cii_model",
                "source_category": "geopolitical",
                "url": "",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "cii_score": round(cii_score, 1),
                "source_count": len(sources),
            }
        )

    derived.sort(key=lambda item: float(item.get("cii_score") or 0.0), reverse=True)
    return derived[:12]


async def _poll_sources() -> None:
    news_api_key = get_secret("NEWSAPI_API_KEY")
    gnews_api_key = get_secret("GNEWS_API_KEY")

    batches: list[dict] = []
    for fn in (
        fetch_nasa_eonet,
        fetch_gdelt,
        lambda: fetch_newsapi(news_api_key),
        lambda: fetch_gnews(gnews_api_key),
        # ── Extended free sources ─────────────────────────────────
        fetch_gdacs,
        fetch_usgs_earthquakes,
        fetch_nasa_firms,
        fetch_reliefweb,
        fetch_acled,
        fetch_portwatch_transit_alerts,
        fetch_portwatch_disruptions,
        fetch_gps_interference,
        fetch_wto_trade_signals,
        fetch_ofac_sanctions,
        fetch_social_sentiment,
    ):
        try:
            items = await fn()
            batches.extend(items)
        except Exception as exc:
            add_audit("signal_poll_error", str(exc))

    # Deduplicate by signal ID
    dedup: dict[str, dict] = {}
    for item in batches:
        sid = str(item.get("id") or "").strip()
        if not sid:
            basis = f"{item.get('source','')}|{item.get('title','')}|{item.get('location','')}|{item.get('created_at','')}"
            sid = f"sig_{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:16]}"
            item["id"] = sid
        # Prefer most-recent version if we see the same id twice
        existing = dedup.get(sid)
        if existing is None:
            dedup[sid] = item
        # else keep existing (stable dedup)

    for item in _derive_country_instability_signals(list(dedup.values())):
        dedup[str(item["id"])] = item

    enriched = mark_corroborations([enrich_signal_item(dict(x)) for x in dedup.values()])
    replace_active_signals(enriched)
    purged = purge_archived_signals(days=7)
    add_audit("signal_poll_complete", f"active={len(dedup)} purged={purged}")

    # ── v4 Autonomous Incident Generation ────────────────────────────
    # After signals land, push the top events through the GNN-based
    # incident engine so incidents appear without any user click.
    try:
        from services.incident_engine import incident_engine
        from services.firestore_store import upsert_incident, list_incidents

        # Build risk-event dicts from the enriched signals
        events: list[dict] = []
        for sig in enriched:
            sev = float(sig.get("severity", 0) or 0)
            if sev < 4:  # Only process medium+ severity
                continue
            events.append({
                "id": str(sig.get("id") or ""),
                "title": str(sig.get("title") or sig.get("event_type") or "Signal"),
                "severity": "CRITICAL" if sev >= 8 else ("HIGH" if sev >= 6 else "MEDIUM"),
                "description": str(sig.get("description") or sig.get("location") or ""),
                "lat": float(sig.get("lat", 0) or 0),
                "lng": float(sig.get("lng", 0) or 0),
                "region": str(sig.get("location") or "Unknown"),
                "mode": str(sig.get("mode") or "land"),
                "timestamp": str(sig.get("created_at") or ""),
            })

        # Avoid re-creating incidents for events already processed
        existing_ids = {str(inc.get("event_id") or inc.get("id") or "") for inc in list_incidents(limit=500)}

        # Build a lightweight supplier list from the data registry
        from services.data_registry import registry
        suppliers = []
        for idx, port in enumerate(registry.ports[:50]):
            exposure = round(25 + ((abs(port.lat) + abs(port.lng)) % 70), 1)
            suppliers.append({
                "id": f"sup_{idx + 1}",
                "name": f"{port.city} Node",
                "country": port.country,
                "location": f"{port.city}, {port.country}",
                "tier": f"Tier {(idx % 3) + 1}",
                "exposureScore": exposure,
                "lat": port.lat,
                "lng": port.lng,
            })

        created = 0
        for evt in events[:15]:  # cap at 15 per cycle
            if evt["id"] in existing_ids:
                continue
            inc = incident_engine.process_event(evt, suppliers)
            if inc:
                upsert_incident(inc.id, inc.to_dict(), inc.status, inc.severity)
                add_audit("incident_auto_created", f"{inc.id}:{inc.severity}")
                created += 1

        if created > 0:
            add_audit("incident_auto_batch", f"created={created}")
    except Exception as exc:
        add_audit("incident_auto_error", str(exc)[:200])


def _job_wrapper() -> None:
    asyncio.run(_poll_sources())


def start_signal_scheduler() -> None:
    global _scheduler
    if os.getenv("ENABLE_SIGNAL_SCHEDULER", "true").lower() != "true":
        return
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(_job_wrapper, "interval", minutes=15, id="signal_poll_15m", replace_existing=True)
    _scheduler.start()
    add_audit("signal_scheduler_started", "15m")


async def force_poll() -> dict:
    """Trigger an immediate poll outside the scheduler cycle. Called from /api/signals/refresh."""
    await _poll_sources()
    return {"status": "ok", "message": "Signal refresh complete"}
