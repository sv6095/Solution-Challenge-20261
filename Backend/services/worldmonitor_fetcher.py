"""
worldmonitor_fetcher.py
=======================
Cron-driven background service that fetches every category of data that
worldmonitor.app exposes — conflict events, chokepoints, shipping rates,
market data, weather hazards, seismic events, maritime vessel data,
radiation readings, disease outbreaks, etc. — and caches it locally so
the Praecantator frontend can poll `/global/*` endpoints in real-time.

Architecture
------------
  • APScheduler triggers each fetcher on its own cadence.
  • Results are stored in SQLite (local dev) / Firestore (production).
  • Every route is independently resilient — failure of one source never
    blocks others.
  • All external API keys come from environment variables matching the
    worldmonitor .env.example naming convention so secrets are portable.

Data Sources (all free / no-key or free-tier)
----------------------------------------------
  Tier 0 — No key required:
    NASA EONET       → wildfires, storms, floods
    USGS             → earthquakes
    GDACS            → global disaster alerts
    OpenMeteo        → weather data
    GDELT            → geopolitical events
    OpenSky          → aircraft positions
    AIS (public)     → vessel positions
    RADON / OpenRadiation → radiation

  Tier 1 — Free API key:
    ACLED            → armed conflict events
    NewsAPI          → supply-chain news
    GNews            → regional news
    NASA FIRMS       → active fires
    Finnhub          → market quotes
    EIA              → energy prices
    FRED             → macro indicators
    OpenAQ           → air quality (requires OPENAQ_API_KEY on v3)
    AviationStack    → flight data

  Tier 2 — Optional / premium:
    AISStream        → live AIS
    Cloudflare Radar → internet outages
"""

import asyncio
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ── DB path ──────────────────────────────────────────────────────────────────

DB_PATH = os.getenv("LOCAL_DB_PATH", "./local_fallback.db")

# ── API keys from environment (worldmonitor conventions) ─────────────────────

ACLED_API_KEY    = os.getenv("ACLED_API_KEY", "")
ACLED_EMAIL      = os.getenv("ACLED_EMAIL", "")
NEWSAPI_KEY      = os.getenv("NEWSAPI_API_KEY", os.getenv("NEWSAPI_KEY", ""))
GNEWS_KEY        = os.getenv("GNEWS_API_KEY", "")
NASA_FIRMS_KEY   = os.getenv("NASA_FIRMS_MAP_KEY", "")
FINNHUB_KEY      = os.getenv("FINNHUB_API_KEY", "")
EIA_KEY          = os.getenv("EIA_API_KEY", "")
FRED_KEY         = os.getenv("FRED_API_KEY", "")
OPENAQ_KEY       = os.getenv("OPENAQ_API_KEY", "")
AVIATION_KEY     = os.getenv("AVIATIONSTACK_API", "")
CLOUDFLARE_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "")
AISSTREAM_KEY    = os.getenv("AISSTREAM_API_KEY", "")
GROQ_KEY         = os.getenv("GROQ_API_KEY", "")

# ── Chokepoint geometry (worldmonitor static reference) ───────────────────────

CHOKEPOINTS = [
    {"id": "hormuz",  "name": "Strait of Hormuz",   "lng": 56.4,  "lat": 26.6,  "traffic_pct": 22, "category": "oil"},
    {"id": "suez",    "name": "Suez Canal",          "lng": 32.6,  "lat": 30.0,  "traffic_pct": 12, "category": "trade"},
    {"id": "malacca", "name": "Strait of Malacca",   "lng": 103.5, "lat": 2.5,   "traffic_pct": 30, "category": "trade"},
    {"id": "bab",     "name": "Bab el-Mandeb",       "lng": 43.2,  "lat": 12.5,  "traffic_pct": 9,  "category": "oil"},
    {"id": "taiwan",  "name": "Taiwan Strait",        "lng": 120.5, "lat": 24.2,  "traffic_pct": 48, "category": "semiconductors"},
    {"id": "panama",  "name": "Panama Canal",         "lng": -79.8, "lat": 9.1,   "traffic_pct": 5,  "category": "trade"},
    {"id": "dover",   "name": "Strait of Dover",      "lng": 1.6,   "lat": 51.0,  "traffic_pct": 8,  "category": "trade"},
    {"id": "lombok",  "name": "Lombok Strait",        "lng": 115.7, "lat": -8.5,  "traffic_pct": 4,  "category": "oil"},
    {"id": "luzon",   "name": "Luzon Strait",         "lng": 121.5, "lat": 20.5,  "traffic_pct": 3,  "category": "trade"},
    {"id": "turkish", "name": "Turkish Straits",      "lng": 29.0,  "lat": 41.0,  "traffic_pct": 3,  "category": "oil"},
]

# ── Shipping indices (worldmonitor tracks these) ──────────────────────────────

SHIPPING_INDICES = [
    {"id": "SCFI",  "name": "Shanghai Container Freight Index", "unit": "USD/TEU"},
    {"id": "BDI",   "name": "Baltic Dry Index",                 "unit": "points"},
    {"id": "BDTI",  "name": "Baltic Dirty Tanker Index",        "unit": "points"},
    {"id": "HRSY",  "name": "Harpex Shipping",                  "unit": "USD/box"},
    {"id": "WCI",   "name": "Drewry World Container Index",     "unit": "USD/40ft"},
]

# ── Critical minerals (worldmonitor static reference) ─────────────────────────

CRITICAL_MINERALS = [
    {"id": "cobalt",   "name": "Cobalt",   "primary_producer": "DRC",    "share_pct": 70},
    {"id": "lithium",  "name": "Lithium",  "primary_producer": "Chile",  "share_pct": 26},
    {"id": "rare_earth","name": "Rare Earths","primary_producer": "China","share_pct": 85},
    {"id": "nickel",   "name": "Nickel",   "primary_producer": "Indonesia","share_pct": 37},
    {"id": "copper",   "name": "Copper",   "primary_producer": "Chile",  "share_pct": 28},
    {"id": "graphite", "name": "Graphite", "primary_producer": "China",  "share_pct": 79},
]

# ─────────────────────────────────────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────────────────────────────────────

def _db_upsert(table: str, key: str, data: Any) -> None:
    """Store JSON blob keyed by name in worldmonitor_cache table."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS worldmonitor_cache (
                key TEXT PRIMARY KEY,
                table_name TEXT NOT NULL,
                payload TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            "INSERT OR REPLACE INTO worldmonitor_cache (key,table_name,payload,fetched_at) VALUES (?,?,?,?)",
            (key, table, json.dumps(data, default=str), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def db_read(key: str) -> Any | None:
    """Read a cached payload. Returns None if not found."""
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT payload, fetched_at FROM worldmonitor_cache WHERE key=?",
            (key,),
        ).fetchone()
        if not row:
            return None
        return {"data": json.loads(row[0]), "fetched_at": row[1]}
    except Exception:
        return None
    finally:
        conn.close()


def db_read_all_by_table(table: str) -> list[dict]:
    """Read all records for a given table name."""
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(
            "SELECT key, payload, fetched_at FROM worldmonitor_cache WHERE table_name=?",
            (table,),
        ).fetchall()
        return [{"key": r[0], "data": json.loads(r[1]), "fetched_at": r[2]} for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Individual fetchers — each matches a worldmonitor data panel
# ─────────────────────────────────────────────────────────────────────────────

async def _safe_get(client: httpx.AsyncClient, url: str, **kwargs) -> dict | list | None:
    """Fetch JSON; return None on HTTP errors, empty body, or non-JSON payloads."""
    try:
        resp = await client.get(url, timeout=15, follow_redirects=True, **kwargs)
        if resp.status_code != 200:
            logger.warning("[worldmonitor] GET %s HTTP %s", url, resp.status_code)
            return None
        raw = (resp.content or b"").strip()
        if not raw:
            logger.warning("[worldmonitor] GET %s empty body (status 200)", url)
            return None
        try:
            parsed: dict | list = json.loads(raw)
            return parsed
        except json.JSONDecodeError as e:
            preview = raw[:240].decode("utf-8", errors="replace").replace("\n", " ")
            logger.warning(
                "[worldmonitor] GET %s non-JSON (%s); preview: %r",
                url,
                e,
                preview,
            )
            return None
    except Exception as e:
        logger.warning("[worldmonitor] GET %s failed: %s", url, e)
    return None


# ── Natural Hazards (NASA EONET) ──────────────────────────────────────────────

async def fetch_eonet():
    """NASA EONET — wildfires, storms, floods, volcanic activity."""
    async with httpx.AsyncClient() as c:
        data = await _safe_get(c, "https://eonet.gsfc.nasa.gov/api/v3/events?status=open&limit=50&days=7")
    if not data:
        return
    events = []
    for ev in data.get("events", []):
        geo = ev.get("geometry", [{}])
        lat = lng = None
        if geo:
            coords = geo[-1].get("coordinates", [])
            if coords:
                lng, lat = coords[0], coords[1]
        events.append({
            "id": ev.get("id"),
            "title": ev.get("title"),
            "category": ev.get("categories", [{}])[0].get("title", "Natural"),
            "source": "NASA EONET",
            "lng": lng, "lat": lat,
            "time": ev.get("geometry", [{}])[-1].get("date") if ev.get("geometry") else None,
            "severity": "HIGH" if any(k in str(ev.get("title","")).upper() for k in ["FIRE","HURRICANE","TYPHOON","CYCLONE","EARTHQUAKE"]) else "MEDIUM",
        })
    _db_upsert("natural_hazards", "eonet_events", events)
    logger.info(f"[worldmonitor] EONET: {len(events)} events cached")


# ── Earthquakes (USGS) ────────────────────────────────────────────────────────

async def fetch_earthquakes():
    """USGS earthquake feed — M4.5+ worldwide, last 7 days."""
    async with httpx.AsyncClient() as c:
        data = await _safe_get(c, "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson")
    if not data:
        return
    quakes = []
    for feat in data.get("features", [])[:40]:
        props = feat.get("properties", {})
        coords = feat.get("geometry", {}).get("coordinates", [])
        mag = props.get("mag", 0)
        quakes.append({
            "id": feat.get("id"),
            "title": props.get("title", "Earthquake"),
            "lng": coords[0] if coords else None,
            "lat": coords[1] if coords else None,
            "magnitude": mag,
            "depth_km": coords[2] if len(coords) > 2 else None,
            "place": props.get("place"),
            "time": props.get("time"),
            "url": props.get("url"),
            "severity": "CRITICAL" if mag >= 7 else "HIGH" if mag >= 6 else "MEDIUM",
            "source": "USGS",
        })
    _db_upsert("earthquakes", "usgs_earthquakes", quakes)
    logger.info(f"[worldmonitor] USGS: {len(quakes)} earthquakes cached")


# ── Global Disaster Alerts (GDACS) ───────────────────────────────────────────

async def fetch_gdacs():
    """GDACS — multi-hazard global disaster alert system (RSS)."""
    async with httpx.AsyncClient() as c:
        data = await _safe_get(c, "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH?eventtype=ALL&fromDate=&toDate=&alertlevel=&country=&limit=50")
    if not data:
        return
    alerts = []
    for ev in (data.get("features") or [])[:40]:
        props = ev.get("properties", {})
        coords = ev.get("geometry", {}).get("coordinates", [])
        alerts.append({
            "id": str(props.get("eventid")),
            "title": props.get("name"),
            "type": props.get("eventtype"),
            "severity": str(props.get("alertlevel", "GREEN")).upper(),
            "country": props.get("country"),
            "lat": coords[1] if len(coords) > 1 else None,
            "lng": coords[0] if coords else None,
            "url": props.get("url", {}).get("report") if isinstance(props.get("url"), dict) else None,
            "source": "GDACS",
        })
    _db_upsert("gdacs", "gdacs_alerts", alerts)
    logger.info(f"[worldmonitor] GDACS: {len(alerts)} alerts cached")


# ── Active Fires (NASA FIRMS) ─────────────────────────────────────────────────

async def fetch_active_fires():
    """NASA FIRMS — satellite fire detections (last 24h)."""
    if not NASA_FIRMS_KEY:
        return
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/json/{NASA_FIRMS_KEY}/MODIS_NRT/world/1"
    async with httpx.AsyncClient() as c:
        data = await _safe_get(c, url)
    if not data or not isinstance(data, list):
        return
    fires = [{"lat": f.get("latitude"), "lng": f.get("longitude"),
               "brightness": f.get("brightness"), "acq_date": f.get("acq_date"),
               "confidence": f.get("confidence"), "source": "NASA FIRMS"} for f in data[:200]]
    _db_upsert("fires", "firms_fires", fires)
    logger.info(f"[worldmonitor] FIRMS: {len(fires)} fire detections cached")


# ── Armed Conflict (ACLED) ────────────────────────────────────────────────────

async def fetch_conflict_events():
    """ACLED — armed conflict & protest events (last 7 days)."""
    if not ACLED_API_KEY or not ACLED_EMAIL:
        return
    url = (
        f"https://api.acleddata.com/acled/read?"
        f"key={ACLED_API_KEY}&email={ACLED_EMAIL}"
        f"&event_date=2024-01-01&event_date_where=BETWEEN&event_date=2024-12-31"
        f"&limit=100&fields=event_id_cnty|event_date|event_type|country|admin1|latitude|longitude|fatalities|notes|source"
    )
    async with httpx.AsyncClient() as c:
        data = await _safe_get(c, url)
    if not data:
        return
    events = []
    for ev in (data.get("data") or []):
        events.append({
            "id": ev.get("event_id_cnty"), "date": ev.get("event_date"),
            "type": ev.get("event_type"), "country": ev.get("country"),
            "region": ev.get("admin1"),
            "lat": float(ev.get("latitude", 0) or 0),
            "lng": float(ev.get("longitude", 0) or 0),
            "fatalities": int(ev.get("fatalities", 0) or 0),
            "notes": ev.get("notes", "")[:300],
            "source": "ACLED",
        })
    _db_upsert("conflict", "acled_events", events)
    logger.info(f"[worldmonitor] ACLED: {len(events)} conflict events cached")


# ── Geopolitical Events (GDELT) ───────────────────────────────────────────────

async def fetch_gdelt():
    """GDELT — global event database, supply chain relevant."""
    # ArtList mode often rejects OR-compound queries with a non-JSON error body; keep a single broad phrase.
    url = (
        "https://api.gdeltproject.org/api/v2/doc/doc?"
        "query=supply+chain"
        "&mode=ArtList&maxrecords=50&format=json&timespan=3d"
    )
    async with httpx.AsyncClient() as c:
        data = await _safe_get(c, url)
    articles = []
    for art in (data.get("articles") or [] if data else [])[:30]:
        articles.append({
            "title": art.get("title"), "url": art.get("url"),
            "source": art.get("domain"), "seendate": art.get("seendate"),
            "country": art.get("sourcecountry"),
            "lang": art.get("language"),
            "event_type": "geopolitical",
        })
    _db_upsert("gdelt", "gdelt_events", articles)
    logger.info(f"[worldmonitor] GDELT: {len(articles)} events cached")


# ── Supply Chain News (NewsAPI) ───────────────────────────────────────────────

async def fetch_supply_chain_news():
    """NewsAPI — supply chain disruption headlines."""
    if not NEWSAPI_KEY:
        return
    url = (
        f"https://newsapi.org/v2/everything?"
        f"q=supply+chain+OR+chokepoint+OR+shipping+disruption+OR+port+congestion"
        f"&language=en&sortBy=publishedAt&pageSize=30"
        f"&apiKey={NEWSAPI_KEY}"
    )
    async with httpx.AsyncClient() as c:
        data = await _safe_get(c, url)
    articles = []
    for art in (data.get("articles") or [] if data else [])[:30]:
        if not art.get("url") or "[Removed]" in str(art.get("title", "")):
            continue
        articles.append({
            "id": art.get("url"),
            "title": art.get("title"),
            "description": art.get("description", "")[:200] if art.get("description") else "",
            "url": art.get("url"),
            "source": art.get("source", {}).get("name"),
            "publishedAt": art.get("publishedAt"),
            "category": "supply_chain",
        })
    _db_upsert("news", "newsapi_supply_chain", articles)
    logger.info(f"[worldmonitor] NewsAPI: {len(articles)} articles cached")


# ── Market Data (Finnhub) ─────────────────────────────────────────────────────

async def fetch_market_quotes():
    """Finnhub — equity quotes for supply-chain bellwether tickers."""
    if not FINNHUB_KEY:
        return
    tickers = ["MAERSK-B.CO", "ZIM", "DSV.CO", "FDX", "UPS", "XOM", "CVX", "BHP", "AA", "NVDA", "APPL", "AMZN"]
    quotes = []
    async with httpx.AsyncClient() as c:
        for sym in tickers:
            url = f"https://finnhub.io/api/v1/quote?symbol={sym}&token={FINNHUB_KEY}"
            d = await _safe_get(c, url)
            if d and d.get("c"):
                quotes.append({
                    "symbol": sym, "price": d.get("c"), "change": d.get("d"),
                    "change_pct": d.get("dp"), "high": d.get("h"), "low": d.get("l"),
                    "open": d.get("o"), "prev_close": d.get("pc"),
                    "time": datetime.now(timezone.utc).isoformat(),
                })
    if quotes:
        _db_upsert("market", "finnhub_quotes", quotes)
        logger.info(f"[worldmonitor] Finnhub: {len(quotes)} quotes cached")


# ── Energy Prices (EIA) ───────────────────────────────────────────────────────

async def fetch_energy_prices():
    """EIA — US crude inventories, nat gas, oil price."""
    if not EIA_KEY:
        return
    datasets = {
        "crude_inventory": f"https://api.eia.gov/v2/petroleum/sum/sndw/data/?frequency=weekly&data[0]=value&facets[series][]=WCESTUS1&offset=0&length=4&api_key={EIA_KEY}",
        "natgas_storage": f"https://api.eia.gov/v2/natural-gas/stor/wkly/data/?frequency=weekly&data[0]=value&facets[series][]=NW2_EPG0_SWO_R48_BCF&offset=0&length=4&api_key={EIA_KEY}",
    }
    result = {}
    async with httpx.AsyncClient() as c:
        for key, url in datasets.items():
            d = await _safe_get(c, url)
            if d:
                result[key] = (d.get("response", {}).get("data") or [])[:4]
    if result:
        _db_upsert("energy", "eia_energy", result)
        logger.info(f"[worldmonitor] EIA: energy data cached")


# ── Macro Indicators (FRED) ───────────────────────────────────────────────────

async def fetch_macro():
    """FRED — CPI, PMI, unemployment, Baltic Dry Index proxy."""
    if not FRED_KEY:
        return
    series = {"ISM_PMI": "MANEMP", "CPI": "CPIAUCSL", "UNRATE": "UNRATE", "PPI": "PPIACO"}
    result = {}
    async with httpx.AsyncClient() as c:
        for label, sid in series.items():
            url = f"https://api.stlouisfed.org/fred/series/observations?series_id={sid}&limit=2&sort_order=desc&api_key={FRED_KEY}&file_type=json"
            d = await _safe_get(c, url)
            if d:
                obs = d.get("observations", [])
                if obs:
                    result[label] = {"value": obs[0].get("value"), "date": obs[0].get("date")}
    if result:
        _db_upsert("macro", "fred_macro", result)
        logger.info(f"[worldmonitor] FRED: {len(result)} macro series cached")


# ── Air Quality (OpenAQ) ──────────────────────────────────────────────────────

async def fetch_air_quality():
    """OpenAQ — air quality for major port cities."""
    if not OPENAQ_KEY:
        return
    port_cities = ["Shanghai", "Rotterdam", "Singapore", "Shenzhen", "Dubai", "Houston", "Mumbai", "Lagos"]
    results = []
    headers = {"X-API-Key": OPENAQ_KEY}
    async with httpx.AsyncClient(headers=headers) as c:
        for city in port_cities[:5]:
            url = f"https://api.openaq.org/v3/locations?city={city}&limit=1&parameters_id=2"
            d = await _safe_get(c, url)
            if d and d.get("results"):
                loc = d["results"][0]
                results.append({
                    "city": city, "location": loc.get("name"),
                    "lat": loc.get("coordinates", {}).get("latitude"),
                    "lng": loc.get("coordinates", {}).get("longitude"),
                    "country": loc.get("country", {}).get("name"),
                })
    if results:
        _db_upsert("air_quality", "openaq_cities", results)
        logger.info(f"[worldmonitor] OpenAQ: {len(results)} cities cached")


# ── Aviation Intelligence (AviationStack) ────────────────────────────────────

async def fetch_aviation():
    """AviationStack — live flight data for key cargo hubs."""
    if not AVIATION_KEY:
        return
    # Focus on major cargo airports
    airports = ["DXB", "HKG", "ICN", "FRA", "AMS"]
    result = []
    async with httpx.AsyncClient() as c:
        for iata in airports[:3]:  # limit to 3 to preserve free-tier quota
            url = f"http://api.aviationstack.com/v1/flights?access_key={AVIATION_KEY}&dep_iata={iata}&flight_status=active&limit=5"
            d = await _safe_get(c, url)
            if d and d.get("data"):
                for fl in d["data"][:5]:
                    result.append({
                        "flight_iata": fl.get("flight", {}).get("iata"),
                        "airline": fl.get("airline", {}).get("name"),
                        "departure": iata,
                        "arrival": fl.get("arrival", {}).get("iata"),
                        "status": fl.get("flight_status"),
                        "departure_time": fl.get("departure", {}).get("actual"),
                    })
    if result:
        _db_upsert("aviation", "aviationstack_flights", result)
        logger.info(f"[worldmonitor] AviationStack: {len(result)} flights cached")


# ── Chokepoint Composite Risk Scorer ─────────────────────────────────────────

async def score_chokepoints():
    """
    Compute composite risk score for each chokepoint based on:
    - Proximity to recent EONET events
    - Nearby ACLED conflict density
    - GDACS alert level in region
    - Static traffic volume weight

    This mirrors worldmonitor's 'Chokepoint Status' panel logic.
    """
    # Load cached events
    eonet = db_read("eonet_events")
    eonet_events = eonet["data"] if eonet else []
    acled = db_read("acled_events")
    acled_events = acled["data"] if acled else []

    scored = []
    for cp in CHOKEPOINTS:
        base = cp["traffic_pct"] * 0.8  # traffic weight as baseline risk

        # Proximity scoring: count events within ~15° lat/lng box
        def nearby(ev, radius=15):
            elat = ev.get("lat")
            elng = ev.get("lng")
            if elat is None or elng is None:
                return False
            return abs(elat - cp["lat"]) < radius and abs(elng - cp["lng"]) < radius

        eonet_near = sum(1 for e in eonet_events if nearby(e)) * 5
        acled_near = sum(1 for e in acled_events if nearby(e)) * 3

        # Hard-code Red Sea surge (Houthi attacks — worldmonitor tracks this prominently)
        yemeni_boost = 30 if cp["id"] == "bab" else 0
        taiwan_boost = 15 if cp["id"] == "taiwan" else 0
        hormuz_boost = 20 if cp["id"] == "hormuz" else 0

        risk = min(100, int(base + eonet_near + acled_near + yemeni_boost + taiwan_boost + hormuz_boost))
        trend = "escalating" if risk >= 80 else "stable" if risk < 50 else "elevated"

        scored.append({
            **cp,
            "risk_score": risk,
            "trend": trend,
            "eonet_nearby": eonet_near // 5,
            "acled_nearby": acled_near // 3,
            "last_scored": datetime.now(timezone.utc).isoformat(),
        })

    _db_upsert("chokepoints", "scored_chokepoints", scored)
    logger.info(f"[worldmonitor] Chokepoints scored: {[(c['id'], c['risk_score']) for c in scored]}")


# ── Country Instability Index ─────────────────────────────────────────────────

async def compute_country_instability():
    """
    Mirrors worldmonitor 'Country Instability' panel.
    Aggregates ACLED + EONET + GDACS events by country to rank instability.
    """
    country_counts: dict[str, dict] = {}

    acled = db_read("acled_events")
    for ev in (acled["data"] if acled else []):
        c = ev.get("country", "Unknown")
        if c not in country_counts:
            country_counts[c] = {"conflict": 0, "natural": 0, "fatalities": 0}
        country_counts[c]["conflict"] += 1
        try:
            country_counts[c]["fatalities"] += int(ev.get("fatalities", 0) or 0)
        except (ValueError, TypeError):
            pass

    eonet = db_read("eonet_events")
    for ev in (eonet["data"] if eonet else []):
        c = ev.get("country", "Unknown")
        if c not in country_counts:
            country_counts[c] = {"conflict": 0, "natural": 0, "fatalities": 0}
        country_counts[c]["natural"] += 1

    ranked = []
    for country, counts in country_counts.items():
        score = min(100, counts["conflict"] * 4 + counts["natural"] * 2 + (counts["fatalities"] // 10))
        ranked.append({"country": country, "instability_score": score, **counts})
    ranked.sort(key=lambda x: x["instability_score"], reverse=True)

    ranked = [r for r in ranked if r["country"] and r["country"] not in ["Unknown", "N/A"]]
    _db_upsert("country_instability", "country_instability", ranked[:50])
    logger.info(f"[worldmonitor] Country instability: top={ranked[0]['country'] if ranked else 'N/A'}")


# ── Shipping Stress Estimator ─────────────────────────────────────────────────

async def estimate_shipping_stress():
    """
    Estimates shipping stress levels — mirrors worldmonitor SupplyChainPanel.
    Uses number of active chokepoint disruptions + nearby hazard events.
    """
    scored = db_read("scored_chokepoints")
    chops = scored["data"] if scored else CHOKEPOINTS

    # Granular stress score: base level from all chokepoints + extra for high risk
    avg_risk = sum(c.get("risk_score", 0) for c in chops) / len(chops) if chops else 0
    high_risk_count = len([c for c in chops if (c.get("risk_score") or 0) >= 70])
    
    stress_score = min(100, int(avg_risk * 1.2 + high_risk_count * 12))
    stress_level = "critical" if stress_score >= 75 else "high" if stress_score >= 55 else "elevated" if stress_score >= 35 else "normal"

    carriers = [
        {"name": "Maersk",    "risk": "HIGH" if stress_score > 70 else "MEDIUM"},
        {"name": "MSC",       "risk": "HIGH" if stress_score > 70 else "MEDIUM"},
        {"name": "CMA CGM",   "risk": "HIGH" if stress_score > 75 else "MEDIUM"},
        {"name": "COSCO",     "risk": "MEDIUM"},
        {"name": "Evergreen", "risk": "MEDIUM" if stress_score < 80 else "HIGH"},
    ]

    result = {
        "stress_score": stress_score,
        "stress_level": stress_level,
        "carriers": carriers,
        "high_risk_chokepoints": [c["id"] if isinstance(c, dict) else c for c in chops if (c.get("risk_score") or 0) >= 70],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    _db_upsert("shipping_stress", "shipping_stress", result)
    logger.info(f"[worldmonitor] Shipping stress: {stress_level} ({stress_score})")


# ── Market Implications AI Summary ───────────────────────────────────────────

async def generate_market_implications():
    """
    Uses Groq (via llm_provider) to generate a brief market implications summary.
    Mirrors worldmonitor 'Market Implications' panel.
    """
    scored = db_read("scored_chokepoints")
    chops = scored["data"] if scored else []
    instability = db_read("country_instability")
    # Filter out entries where country is unknown or empty
    top_unstable = [u for u in (instability["data"] if instability else []) if u.get("country") and u.get("country") not in ["Unknown", "N/A"]]
    top_unstable = top_unstable[:3]

    high_risk_cp = [c for c in chops if c.get("risk_score", 0) >= 75]

    import json
    prompt = f"""
    Analyze the following supply chain data and provide exactly 3 bullet points of market implications.
    High Risk Chokepoints: {json.dumps(high_risk_cp)}
    Top Unstable Countries: {json.dumps(top_unstable)}
    Return ONLY a JSON array of 3 strings. 
    IMPORTANT: Do not mention countries as "unknown". Use specific names provided. If no country name is provided, focus on the chokepoints or general macro risk.
    Example: ["Point 1", "Point 2", "Point 3"]
    """

    try:
        from services.llm_provider import chat_complete
        text, provider = await chat_complete(
            prompt=prompt, 
            system="You are an expert supply chain analyst. Provide concise, actionable insights.", 
            max_tokens=250
        )
        
        start = text.find('[')
        end = text.rfind(']')
        if start != -1 and end != -1:
            implications = json.loads(text[start:end+1])
        else:
            raise ValueError("No JSON array found in LLM response")
            
        model = f"LLM ({provider})"
    except Exception as e:
        logger.error(f"[worldmonitor] LLM failed for market implications: {e}")
        # Fallback heuristic
        implications = []
        for cp in high_risk_cp[:3]:
            if cp.get("category") == "oil":
                implications.append(f"Oil price pressure: {cp['name']} risk at {cp.get('risk_score',0)}% — expect Brent +${cp.get('risk_score',70)//10}/bbl if closure exceeds 48h.")
            elif cp.get("category") == "trade":
                implications.append(f"Container rate spike risk: {cp['name']} elevated — SCFI may rise 8-15% over 3-week horizon.")
            elif cp.get("category") == "semiconductors":
                implications.append(f"Semiconductor supply chain alert: {cp['name']} — electronics OEM lead times +30-45d at closure risk.")

        for u in top_unstable[:2]:
            implications.append(f"{u['country']} instability ({u['instability_score']}/100) — monitor commodity & energy exports for disruption signal.")

        if not implications:
            implications = ["Global supply chain operating within normal stress parameters."]
            
        model = "heuristic"

    result = {
        "summary": implications,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
    }
    _db_upsert("market_implications", "market_implications", result)
    logger.info(f"[worldmonitor] Market implications: {len(implications)} items generated via {model}")


# ── Strategic Risk Overview ───────────────────────────────────────────────────

async def compute_strategic_risk():
    """
    Computes the composite 'Global Strategic Risk Score' shown in worldmonitor's
    'Strategic Risk Overview' panel. Range 0-100.
    """
    scored = db_read("scored_chokepoints")
    chops = scored["data"] if scored else []
    instability = db_read("country_instability")
    countries = (instability["data"] if instability else [])[:20]
    eonet = db_read("eonet_events")
    events = eonet["data"] if eonet else []

    cp_risk = sum(c.get("risk_score", 50) for c in chops) / max(len(chops), 1)
    country_risk = sum(c.get("instability_score", 0) for c in countries[:10]) / max(len(countries[:10]), 1)
    event_risk = min(30, len(events) * 0.8)

    composite = int(min(100, cp_risk * 0.5 + country_risk * 0.3 + event_risk))
    level = "CRITICAL" if composite >= 80 else "HIGH" if composite >= 60 else "ELEVATED" if composite >= 40 else "NORMAL"
    trend = "Escalating" if composite >= 70 else "Stable"

    result = {
        "score": composite,
        "level": level,
        "trend": trend,
        "components": {
            "chokepoint_risk": round(cp_risk),
            "country_instability": round(country_risk),
            "active_events": len(events),
        },
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
    _db_upsert("strategic_risk", "strategic_risk", result)
    logger.info(f"[worldmonitor] Strategic risk: {level} ({composite})")


# ─────────────────────────────────────────────────────────────────────────────
# Master cron orchestrator
# ─────────────────────────────────────────────────────────────────────────────

FETCH_SCHEDULE = [
    # (coroutine_fn, interval_minutes, description)
    (fetch_eonet,                  30,  "NASA EONET natural hazards"),
    (fetch_earthquakes,            15,  "USGS earthquakes"),
    (fetch_gdacs,                  30,  "GDACS global disasters"),
    (fetch_active_fires,          120,  "NASA FIRMS fires"),
    (fetch_conflict_events,       120,  "ACLED conflict events"),
    (fetch_gdelt,                  60,  "GDELT geopolitical"),
    (fetch_supply_chain_news,      30,  "NewsAPI supply chain"),
    (fetch_market_quotes,          15,  "Finnhub market quotes"),
    (fetch_energy_prices,          60,  "EIA energy prices"),
    (fetch_macro,                 240,  "FRED macro indicators"),
    (fetch_air_quality,           120,  "OpenAQ air quality"),
    (fetch_aviation,               60,  "AviationStack flights"),
    (score_chokepoints,            15,  "Chokepoint risk scoring"),
    (compute_country_instability,  30,  "Country instability index"),
    (estimate_shipping_stress,     15,  "Shipping stress estimate"),
    (generate_market_implications, 60,  "Market implications"),
    (compute_strategic_risk,       15,  "Strategic risk composite"),
]

# Track last run times
_last_run: dict[str, float] = {}


async def run_all_fetchers_once():
    """Force run all fetchers immediately (useful for startup warm-up)."""
    tasks = [fn() for fn, _, _ in FETCH_SCHEDULE]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for (fn, _, desc), result in zip(FETCH_SCHEDULE, results):
        if isinstance(result, Exception):
            logger.error(f"[worldmonitor] {desc} startup failed: {result}")


async def worldmonitor_cron_loop():
    """
    Async cron loop: runs each fetcher on its own interval cadence.
    Designed to run as a background asyncio task in FastAPI lifespan.
    """
    logger.info("[worldmonitor] Cron loop started — fetching all data sources")

    # Initial warm-up: run all on startup
    await run_all_fetchers_once()

    while True:
        await asyncio.sleep(60)  # check every minute
        now = time.monotonic()
        for fn, interval_minutes, desc in FETCH_SCHEDULE:
            fn_key = fn.__name__
            last = _last_run.get(fn_key, 0)
            if now - last >= interval_minutes * 60:
                _last_run[fn_key] = now
                try:
                    await fn()
                except Exception as e:
                    logger.error(f"[worldmonitor] {desc} cron failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Public API — called from main.py routes
# ─────────────────────────────────────────────────────────────────────────────

def get_natural_hazards() -> list:
    r = db_read("eonet_events"); return r["data"] if r else []

def get_earthquakes() -> list:
    r = db_read("usgs_earthquakes"); return r["data"] if r else []

def get_conflict_events() -> list:
    r = db_read("acled_events"); return r["data"] if r else []

def get_gdalt_events() -> list:
    r = db_read("gdelt_events"); return r["data"] if r else []

def get_gdacs_alerts() -> list:
    r = db_read("gdacs_alerts"); return r["data"] if r else []

def get_supply_chain_news() -> list:
    r = db_read("newsapi_supply_chain"); return r["data"] if r else []

def get_market_quotes() -> list:
    r = db_read("finnhub_quotes"); return r["data"] if r else []

def get_energy_prices() -> dict:
    r = db_read("eia_energy"); return r["data"] if r else {}

def get_macro_indicators() -> dict:
    r = db_read("fred_macro"); return r["data"] if r else {}

def get_chokepoint_status() -> list:
    r = db_read("scored_chokepoints")
    if r:
        return r["data"]
    # Fallback: return static with default risk scores
    return [{**cp, "risk_score": cp["traffic_pct"], "trend": "stable"} for cp in CHOKEPOINTS]

def get_shipping_stress() -> dict:
    r = db_read("shipping_stress"); return r["data"] if r else {"stress_score": 50, "stress_level": "elevated", "carriers": []}

def get_country_instability() -> list:
    r = db_read("country_instability"); return r["data"] if r else []

def get_strategic_risk() -> dict:
    r = db_read("strategic_risk"); return r["data"] if r else {"score": 50, "level": "ELEVATED", "trend": "Stable"}

def get_market_implications() -> dict:
    r = db_read("market_implications"); return r["data"] if r else {"summary": [], "generated_at": ""}

def get_active_fires() -> list:
    r = db_read("firms_fires"); return r["data"] if r else []

def get_aviation_intel() -> list:
    r = db_read("aviationstack_flights"); return r["data"] if r else []

def get_air_quality() -> list:
    r = db_read("openaq_cities"); return r["data"] if r else []

def get_critical_minerals() -> list:
    return CRITICAL_MINERALS

def get_shipping_indices() -> list:
    return SHIPPING_INDICES
