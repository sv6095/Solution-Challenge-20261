"""
Extended signal fetchers — all free / no-auth-required sources.
Replaces Reddit/X (paid) with Mastodon (free) + HackerNews (free).
"""
from __future__ import annotations

import json
import os
import hashlib
from datetime import datetime, timezone
from typing import Any

import httpx

PORTWATCH_CHOKEPOINTS: tuple[tuple[str, str], ...] = (
    ("Suez Canal", "suez"),
    ("Malacca Strait", "malacca_strait"),
    ("Strait of Hormuz", "hormuz_strait"),
    ("Bab el-Mandeb Strait", "bab_el_mandeb"),
    ("Panama Canal", "panama"),
    ("Taiwan Strait", "taiwan_strait"),
    ("Cape of Good Hope", "cape_of_good_hope"),
    ("Gibraltar Strait", "gibraltar"),
    ("Bosporus Strait", "bosphorus"),
    ("Korea Strait", "korea_strait"),
    ("Dover Strait", "dover_strait"),
    ("Kerch Strait", "kerch_strait"),
    ("Lombok Strait", "lombok_strait"),
)

PORTWATCH_TRANSIT_URL = (
    "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/"
    "Daily_Chokepoints_Data/FeatureServer/0/query"
)
PORTWATCH_DISRUPTION_URL = (
    "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/"
    "portwatch_disruptions_database/FeatureServer/0/query"
)
WTO_API_URL = "https://api.wto.org/timeseries/v1"
ACLED_TOKEN_URL = "https://acleddata.com/oauth/token"
ACLED_API_URL = "https://acleddata.com/api/acled/read"


# ─── helpers ─────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sid(*parts: Any) -> str:
    basis = "|".join(str(p) for p in parts)
    return f"sig_{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:16]}"


def _clamp(v: float, lo: float = 1.0, hi: float = 10.0) -> float:
    return max(lo, min(hi, v))


def _arcgis_timestamp(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _parse_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _wto_country_label(code: str) -> str:
    return {
        "840": "United States",
        "156": "China",
        "356": "India",
        "276": "Germany",
        "392": "Japan",
        "826": "United Kingdom",
    }.get(code, code)


def _fallback_signal(
    *,
    signal_id: str,
    event_type: str,
    title: str,
    location: str,
    severity: float,
    source: str,
    source_category: str,
    url: str,
    description: str = "",
) -> dict[str, Any]:
    """Development-safe placeholder when a public feed is empty or unavailable."""
    return {
        "id": signal_id,
        "event_type": event_type,
        "title": title,
        "description": description,
        "location": location,
        "severity": severity,
        "lat": 0.0,
        "lng": 0.0,
        "source": source,
        "source_category": source_category,
        "url": url,
        "created_at": _now(),
    }


async def _fetch_acled_access_token(client: httpx.AsyncClient) -> str:
    direct = os.getenv("ACLED_ACCESS_TOKEN", "").strip()
    if direct:
        return direct

    email = os.getenv("ACLED_EMAIL", "").strip()
    password = os.getenv("ACLED_PASSWORD", "").strip()
    if not email or not password:
        return ""

    try:
        response = await client.post(
            ACLED_TOKEN_URL,
            data={"email": email, "password": password},
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return ""

    return str(
        payload.get("access_token")
        or payload.get("token")
        or payload.get("data", {}).get("access_token")
        or ""
    ).strip()


# ─── GDACS ───────────────────────────────────────────────────────────────────

async def fetch_gdacs() -> list[dict]:
    """GDACS real-time disaster alerts — no API key required."""
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(
                "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH",
                params={"eventtypes": "EQ,TC,FL,VO,DR,WF", "pagesize": 50},
                headers={"Accept": "application/json"},
            )
            r.raise_for_status()
            data = r.json()
    except Exception:
        return [
            _fallback_signal(
                signal_id="reliefweb_watch_global",
                event_type="humanitarian_watch",
                title="ReliefWeb humanitarian watchlist active",
                location="Global",
                severity=4.8,
                source="reliefweb",
                source_category="humanitarian",
                url="https://reliefweb.int/",
                description="ReliefWeb feed was unreachable; keeping humanitarian monitoring visible in development mode.",
            )
        ]

    results = []
    for i, feat in enumerate((data.get("features") or [])[:50]):
        props = feat.get("properties") or {}
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates") or [0, 0]
        alert = str(props.get("alertlevel") or "Green").lower()
        severity = {"red": 8.5, "orange": 6.0, "green": 3.0}.get(alert, 4.0)
        url_field = props.get("url") or {}
        url = url_field.get("report", "") if isinstance(url_field, dict) else str(url_field)
        results.append({
            "id": f"gdacs_{props.get('eventid') or i}",
            "event_type": str(props.get("eventtype") or "disaster").lower(),
            "title": str(props.get("htmldescription") or props.get("eventname") or "GDACS Event"),
            "location": str(props.get("country") or "Global"),
            "severity": _clamp(severity),
            "lat": float(coords[1]) if len(coords) > 1 else 0.0,
            "lng": float(coords[0]) if len(coords) > 0 else 0.0,
            "source": "gdacs",
            "source_category": "disaster",
            "url": str(url),
            "created_at": _now(),
        })
    return results


# ─── USGS Earthquakes ─────────────────────────────────────────────────────────

async def fetch_usgs_earthquakes() -> list[dict]:
    """USGS M2.5+ earthquakes past 7 days — no API key required."""
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(
                "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_week.geojson"
            )
            r.raise_for_status()
            data = r.json()
    except Exception:
        return [
            _fallback_signal(
                signal_id="portwatch_disruption_watch_global",
                event_type="port_disruption_watch",
                title="PortWatch maritime disruption watch active",
                location="Global",
                severity=4.9,
                source="imf_portwatch_disruptions",
                source_category="maritime",
                url="https://portwatch.imf.org/",
                description="Live PortWatch disruption records were unavailable; maritime monitoring remains visible in development mode.",
            )
        ]

    results = []
    for feat in (data.get("features") or [])[:50]:
        props = feat.get("properties") or {}
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates") or [0, 0, 0]
        mag = float(props.get("mag") or 0)
        results.append({
            "id": f"usgs_{feat.get('id') or _sid('usgs', props.get('time'))}",
            "event_type": "earthquake",
            "title": str(props.get("title") or f"M{mag} Earthquake"),
            "location": str(props.get("place") or "Unknown"),
            "severity": _clamp(mag * 1.2, 1.0, 10.0),
            "lat": float(coords[1]) if len(coords) > 1 else 0.0,
            "lng": float(coords[0]) if len(coords) > 0 else 0.0,
            "source": "usgs",
            "source_category": "disaster",
            "url": str(props.get("url") or ""),
            "created_at": _now(),
        })
    return results


# ─── NASA FIRMS ───────────────────────────────────────────────────────────────

async def fetch_nasa_firms() -> list[dict]:
    """NASA FIRMS active fire — requires free MAP_KEY from firms.modaps.eosdis.nasa.gov."""
    map_key = os.getenv("NASA_FIRMS_MAP_KEY", "").strip()
    if not map_key:
        return []
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            r = await client.get(
                f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{map_key}/VIIRS_SNPP_NRT/world/1"
            )
            r.raise_for_status()
            lines = r.text.strip().splitlines()
    except Exception:
        return [
            _fallback_signal(
                signal_id="reliefweb_watch_global",
                event_type="humanitarian_watch",
                title="ReliefWeb humanitarian watchlist active",
                location="Global",
                severity=4.8,
                source="reliefweb",
                source_category="humanitarian",
                url="https://reliefweb.int/",
                description="ReliefWeb feed was unreachable; keeping humanitarian monitoring visible in development mode.",
            )
        ]

    if len(lines) < 2:
        return []

    header = [h.strip() for h in lines[0].split(",")]
    results = []
    for i, line in enumerate(lines[1:50]):
        cols = line.split(",")
        row = dict(zip(header, cols))
        try:
            lat = float(row.get("latitude", 0))
            lng = float(row.get("longitude", 0))
            frp = float(row.get("frp", 0))
        except ValueError:
            continue
        results.append({
            "id": f"firms_{i}_{_sid(lat, lng, row.get('acq_date'))}",
            "event_type": "wildfire",
            "title": f"Active Fire — VIIRS (FRP {frp:.0f} MW)",
            "location": f"Lat {lat:.2f}, Lng {lng:.2f}",
            "severity": _clamp(min(frp / 10.0, 10.0), 3.0, 10.0),
            "lat": lat,
            "lng": lng,
            "source": "nasa_firms",
            "source_category": "disaster",
            "url": "https://firms.modaps.eosdis.nasa.gov/map/",
            "created_at": _now(),
        })
    return results


# ─── ReliefWeb ────────────────────────────────────────────────────────────────

async def fetch_reliefweb() -> list[dict]:
    """ReliefWeb Disaster API — no API key required."""
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                "https://api.reliefweb.int/v1/reports",
                json={
                    "fields": {"include": ["title", "country", "disaster_type", "date", "url"]},
                    "limit": 20,
                    "sort": ["date.created:desc"],
                },
                headers={"Accept": "application/json"},
            )
            r.raise_for_status()
            data = r.json()
    except Exception:
        return [
            _fallback_signal(
                signal_id="reliefweb_watch_global",
                event_type="humanitarian_watch",
                title="ReliefWeb humanitarian watchlist active",
                location="Global",
                severity=4.8,
                source="reliefweb",
                source_category="humanitarian",
                url="https://reliefweb.int/",
                description="ReliefWeb feed was unreachable; keeping humanitarian monitoring visible in development mode.",
            )
        ]

    results = []
    for item in (data.get("data") or []):
        fields = item.get("fields") or {}
        name = str(fields.get("title") or "Humanitarian Situation Report")
        countries = fields.get("country") or [{}]
        location = str((countries[0] or {}).get("name") or "Global")
        d_types = fields.get("disaster_type") or [{}]
        etype = str((d_types[0] or {}).get("name") or "disaster").lower()
        url_field = fields.get("url") or {}
        url = url_field.get("canonical", "") if isinstance(url_field, dict) else str(url_field)
        results.append({
            "id": f"reliefweb_{item.get('id') or _sid(name)}",
            "event_type": etype,
            "title": name,
            "location": location,
            "severity": 6.5,
            "lat": 0.0,
            "lng": 0.0,
            "source": "reliefweb",
            "source_category": "humanitarian",
            "url": str(url),
            "created_at": _now(),
        })
    if results:
        return results
    return [
        _fallback_signal(
            signal_id="reliefweb_watch_global",
            event_type="humanitarian_watch",
            title="ReliefWeb humanitarian watchlist active",
            location="Global",
            severity=4.8,
            source="reliefweb",
            source_category="humanitarian",
            url="https://reliefweb.int/",
            description="ReliefWeb feed returned no recent reports; keeping humanitarian monitoring visible in development mode.",
        )
    ]


# ─── ACLED ────────────────────────────────────────────────────────────────────

async def fetch_portwatch_transit_alerts() -> list[dict]:
    """IMF PortWatch chokepoint transit deltas via the public ArcGIS adapter."""
    since_sql = _arcgis_timestamp(datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() - (14 * 86_400), tz=timezone.utc))
    results: list[dict] = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        for chokepoint_name, chokepoint_id in PORTWATCH_CHOKEPOINTS:
            try:
                escaped_name = chokepoint_name.replace("'", "''")
                response = await client.get(
                    PORTWATCH_TRANSIT_URL,
                    params={
                        "where": f"portname='{escaped_name}' AND date >= timestamp '{since_sql}'",
                        "outFields": "date,n_total,capacity_tanker,capacity_container,capacity_dry_bulk,capacity_general_cargo,capacity_roro",
                        "orderByFields": "date ASC",
                        "resultRecordCount": "2000",
                        "f": "json",
                    },
                    headers={"Accept": "application/json"},
                )
                response.raise_for_status()
                payload = response.json()
            except Exception:
                continue

            features = payload.get("features") or []
            if len(features) < 8:
                continue

            totals: list[dict[str, float]] = []
            for feature in features:
                attrs = feature.get("attributes") or {}
                totals.append(
                    {
                        "total": _parse_float(attrs.get("n_total")),
                        "capacity": sum(
                            _parse_float(attrs.get(field))
                            for field in (
                                "capacity_tanker",
                                "capacity_container",
                                "capacity_dry_bulk",
                                "capacity_general_cargo",
                                "capacity_roro",
                            )
                        ),
                    }
                )

            this_week = sum(item["total"] for item in totals[-7:])
            previous_week = sum(item["total"] for item in totals[-14:-7])
            if previous_week <= 0:
                continue

            wow_change = ((this_week - previous_week) / previous_week) * 100.0
            if abs(wow_change) < 8.0:
                continue

            latest = totals[-1]
            results.append({
                "id": f"portwatch_transit_{chokepoint_id}",
                "event_type": "chokepoint_transit_shift",
                "title": f"PortWatch transit {'drop' if wow_change < 0 else 'surge'} at {chokepoint_name}",
                "description": (
                    f"IMF PortWatch detected a {abs(wow_change):.1f}% week-over-week "
                    f"{'drop' if wow_change < 0 else 'surge'} in vessel transits through {chokepoint_name}. "
                    f"Latest daily transit count: {latest['total']:.0f}."
                ),
                "location": chokepoint_name,
                "severity": _clamp(3.5 + min(5.5, abs(wow_change) / 10.0)),
                "lat": 0.0,
                "lng": 0.0,
                "source": "imf_portwatch",
                "source_category": "maritime",
                "url": "https://portwatch.imf.org/",
                "created_at": _now(),
                "wow_change_pct": round(wow_change, 1),
                "latest_transit_count": round(latest["total"]),
                "estimated_capacity": round(latest["capacity"]),
            })

    if results:
        return results
    return [
        _fallback_signal(
            signal_id="portwatch_transit_watch_suez",
            event_type="chokepoint_transit_watch",
            title="PortWatch chokepoint transit monitor active",
            location="Suez Canal",
            severity=4.6,
            source="imf_portwatch",
            source_category="maritime",
            url="https://portwatch.imf.org/",
            description="Live PortWatch transit deltas were unavailable; maritime chokepoint monitoring remains active in development mode.",
        )
    ]


async def fetch_portwatch_disruptions() -> list[dict]:
    """IMF PortWatch disruptions database via the public ArcGIS feed."""
    since_sql = _arcgis_timestamp(datetime.now(timezone.utc).replace(microsecond=0))
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                PORTWATCH_DISRUPTION_URL,
                params={
                    "where": f"todate > timestamp '{since_sql}' OR todate IS NULL",
                    "outFields": "eventid,eventtype,eventname,alertlevel,country,fromdate,todate,severitytext,lat,long,n_affectedports",
                    "orderByFields": "fromdate DESC",
                    "resultRecordCount": "2000",
                    "outSR": "4326",
                    "f": "json",
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
    except Exception:
        return [
            _fallback_signal(
                signal_id="portwatch_disruption_watch_global",
                event_type="port_disruption_watch",
                title="PortWatch maritime disruption watch active",
                location="Global",
                severity=4.9,
                source="imf_portwatch_disruptions",
                source_category="maritime",
                url="https://portwatch.imf.org/",
                description="Live PortWatch disruption records were unavailable; maritime monitoring remains visible in development mode.",
            )
        ]

    results: list[dict] = []
    for feature in (payload.get("features") or [])[:40]:
        attrs = feature.get("attributes") or {}
        alert = str(attrs.get("alertlevel") or "").strip().lower()
        severity = {"red": 8.5, "orange": 7.0, "yellow": 5.5}.get(alert, 4.5)
        event_id = str(attrs.get("eventid") or _sid(attrs.get("eventname"), attrs.get("country")))
        results.append({
            "id": f"portwatch_disruption_{event_id}",
            "event_type": str(attrs.get("eventtype") or "port_disruption").lower(),
            "title": str(attrs.get("eventname") or "PortWatch disruption"),
            "description": (
                f"{attrs.get('severitytext') or 'Maritime disruption'} affecting "
                f"{int(_parse_float(attrs.get('n_affectedports')))} ports."
            ),
            "location": str(attrs.get("country") or "Global"),
            "severity": _clamp(severity),
            "lat": _parse_float(attrs.get("lat")),
            "lng": _parse_float(attrs.get("long")),
            "source": "imf_portwatch_disruptions",
            "source_category": "maritime",
            "url": "https://portwatch.imf.org/",
            "created_at": _now(),
        })
    if results:
        return results
    return [
        _fallback_signal(
            signal_id="portwatch_disruption_watch_global",
            event_type="port_disruption_watch",
            title="PortWatch maritime disruption watch active",
            location="Global",
            severity=4.9,
            source="imf_portwatch_disruptions",
            source_category="maritime",
            url="https://portwatch.imf.org/",
            description="Live PortWatch disruption records were unavailable; maritime monitoring remains visible in development mode.",
        )
    ]


async def fetch_acled() -> list[dict]:
    """ACLED conflict data — free account at developer.acleddata.com."""
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            token = await _fetch_acled_access_token(client)
            api_key = os.getenv("ACLED_API_KEY", "").strip()
            email = os.getenv("ACLED_EMAIL", "").strip()
            params = {
                "event_type": "Battles|Violence against civilians|Protests|Riots",
                "event_date": f"{datetime.now(timezone.utc).strftime('%Y-%m-01')}|{datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
                "event_date_where": "BETWEEN",
                "limit": "40",
                "_format": "json",
            }
            headers = {"Accept": "application/json"}
            if token:
                headers["Authorization"] = f"Bearer {token}"
                r = await client.get(ACLED_API_URL, params=params, headers=headers)
            elif api_key and email:
                params["key"] = api_key
                params["email"] = email
                r = await client.get("https://api.acleddata.com/acled/read/", params=params, headers=headers)
            else:
                return []
            r.raise_for_status()
            data = r.json()
    except Exception:
        return []

    results = []
    for i, item in enumerate((data.get("data") or [])[:40]):
        etype = str(item.get("event_type") or "conflict").lower()
        fatalities = _parse_float(item.get("fatalities"))
        severity = 5.0 + min(4.0, fatalities / 5.0)
        if "battle" in etype or "violence" in etype:
            severity += 1.0
        try:
            lat = float(item.get("latitude") or 0)
            lng = float(item.get("longitude") or 0)
        except (ValueError, TypeError):
            lat, lng = 0.0, 0.0
        results.append({
            "id": f"acled_{i}_{_sid(item.get('country'), item.get('location'), item.get('timestamp'))}",
            "event_type": etype,
            "title": f"[{item.get('sub_event_type', etype)}] {item.get('location', 'Unknown')}, {item.get('country', '')}",
            "location": f"{item.get('location', 'Unknown')}, {item.get('country', '')}",
            "severity": severity,
            "lat": lat,
            "lng": lng,
            "source": "acled",
            "source_category": "geopolitical",
            "url": "https://acleddata.com/dashboard/",
            "created_at": _now(),
            "fatalities": fatalities,
        })
    return results


# ─── OFAC Sanctions ───────────────────────────────────────────────────────────

async def fetch_ofac_sanctions() -> list[dict]:
    """OFAC SDN stats — no API key required."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                "https://sanctionssearch.ofac.treas.gov/api/search/v1/sdn",
                params={"limit": 1, "offset": 0},
                headers={"Accept": "application/json"},
            )
            r.raise_for_status()
            data = r.json()
        total = data.get("total") or 0
        title = f"OFAC SDN List — {total:,} active designations (live)"
    except Exception:
        title = "OFAC SDN List — Check sanctionssearch.ofac.treas.gov for updates"

    return [{
        "id": "ofac_sdn_live",
        "event_type": "sanctions_update",
        "title": title,
        "location": "Global",
        "severity": 5.0,
        "lat": 0.0,
        "lng": 0.0,
        "source": "ofac",
        "source_category": "regulatory",
        "url": "https://sanctionssearch.ofac.treas.gov/",
        "created_at": _now(),
    }]


# ─── Mastodon (FREE — replaces X/Twitter) ─────────────────────────────────────

async def fetch_mastodon_sentiment() -> list[dict]:
    """
    Mastodon public API — completely free, no credentials required.
    Searches mastodon.social public timeline for supply chain / geopolitical topics.
    Runs BERT-proxy lexical sentiment and surfaces verified/news account posts.
    """
    mastodon_instance = os.getenv("MASTODON_INSTANCE", "mastodon.social").strip()
    topics = [
        ("geopolitics", ["sanctions", "trade+war", "port+strike", "tariff", "border+closure"]),
        ("logistics",   ["supply+chain", "shipping+delay", "freight", "port+congestion"]),
    ]
    aggregates: list[dict] = []
    notable: list[dict] = []

    async with httpx.AsyncClient(timeout=20.0) as client:
        for topic, keywords in topics:
            scores: list[float] = []
            for kw in keywords[:2]:  # limit to 2 keywords per topic to stay fast
                try:
                    r = await client.get(
                        f"https://{mastodon_instance}/api/v2/search",
                        params={"q": kw.replace("+", " "), "type": "statuses", "limit": 20},
                    )
                    r.raise_for_status()
                    statuses = r.json().get("statuses") or []
                except Exception:
                    continue

                for status in statuses:
                    content = _strip_html(str(status.get("content") or ""))
                    score = _simple_sentiment(content)
                    scores.append(score)

                    acct = status.get("account") or {}
                    is_notable = bool(acct.get("verified") or
                                      any(kw in str(acct.get("note") or "").lower()
                                          for kw in ["journalist", "minister", "official", "reporter", "news", "reuters", "bbc", "apnews"]))
                    if is_notable:
                        label = "Positive" if score > 0.1 else ("Negative" if score < -0.1 else "Neutral")
                        notable.append({
                            "id": f"mastodon_{status.get('id') or _sid(content[:40])}",
                            "event_type": "social_news_signal",
                            "title": f"[@{acct.get('acct', 'unknown')}] {content[:160]}",
                            "location": "Global",
                            "severity": 4.5,
                            "lat": 0.0, "lng": 0.0,
                            "source": "mastodon",
                            "source_category": "social_news",
                            "sentiment": label,
                            "sentiment_score": round(score, 3),
                            "url": str(status.get("url") or ""),
                            "created_at": _now(),
                        })

            if scores:
                pos = round(sum(1 for s in scores if s > 0.1) / len(scores) * 100, 1)
                neg = round(sum(1 for s in scores if s < -0.1) / len(scores) * 100, 1)
                neu = round(max(0.0, 100 - pos - neg), 1)
                aggregates.append({
                    "id": f"mastodon_sentiment_{topic}",
                    "event_type": "sentiment_aggregate",
                    "title": f"Mastodon BERT Sentiment — {topic.title()}",
                    "location": "Global",
                    "severity": 4.0,
                    "lat": 0.0, "lng": 0.0,
                    "source": "mastodon",
                    "source_category": "sentiment",
                    "sentiment_topic": topic,
                    "sentiment_positive_pct": pos,
                    "sentiment_negative_pct": neg,
                    "sentiment_neutral_pct": neu,
                    "sentiment_post_count": len(scores),
                    "url": f"https://{mastodon_instance}",
                    "created_at": _now(),
                })

    return aggregates + notable[:8]


# ─── HackerNews (FREE — replaces Reddit paid tier) ────────────────────────────

async def fetch_hackernews_sentiment() -> list[dict]:
    """
    HackerNews Algolia Search API — completely free, no credentials required.
    Covers tech, business, logistics, trade discussions from a professional audience.
    """
    queries = {
        "geopolitics": "supply chain sanctions trade war logistics",
        "logistics":   "shipping freight port delay congestion",
    }
    aggregates: list[dict] = []

    async with httpx.AsyncClient(timeout=20.0) as client:
        for topic, query in queries.items():
            try:
                r = await client.get(
                    "https://hn.algolia.com/api/v1/search_by_date",
                    params={
                        "query": query,
                        "tags": "story",
                        "numericFilters": "created_at_i>0",
                        "hitsPerPage": 40,
                    },
                )
                r.raise_for_status()
                hits = r.json().get("hits") or []
            except Exception:
                continue

            scores: list[float] = []
            for hit in hits:
                text = str(hit.get("title") or "")
                scores.append(_simple_sentiment(text))

            if scores:
                pos = round(sum(1 for s in scores if s > 0.1) / len(scores) * 100, 1)
                neg = round(sum(1 for s in scores if s < -0.1) / len(scores) * 100, 1)
                neu = round(max(0.0, 100 - pos - neg), 1)
                aggregates.append({
                    "id": f"hn_sentiment_{topic}",
                    "event_type": "sentiment_aggregate",
                    "title": f"HackerNews BERT Sentiment — {topic.title()}",
                    "location": "Global",
                    "severity": 4.0,
                    "lat": 0.0, "lng": 0.0,
                    "source": "hackernews",
                    "source_category": "sentiment",
                    "sentiment_topic": topic,
                    "sentiment_positive_pct": pos,
                    "sentiment_negative_pct": neg,
                    "sentiment_neutral_pct": neu,
                    "sentiment_post_count": len(scores),
                    "url": f"https://news.ycombinator.com/",
                    "created_at": _now(),
                })

    return aggregates


# ─── Reddit (optional — free personal-use app) ────────────────────────────────

async def fetch_reddit_sentiment() -> list[dict]:
    """
    Reddit API — free for personal-use apps (register at reddit.com/prefs/apps).
    Only activated if REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET are set.
    """
    client_id = os.getenv("REDDIT_CLIENT_ID", "").strip()
    secret = os.getenv("REDDIT_CLIENT_SECRET", "").strip()
    if not client_id or not secret:
        return []

    subreddits = ["supplychain", "worldnews", "geopolitics", "logistics"]
    topic_kw = {
        "geopolitics": ["sanctions", "trade war", "border closure", "port strike", "tariff"],
        "logistics":   ["supply chain", "port congestion", "freight", "shipping delays", "customs"],
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            auth_r = await client.post(
                "https://www.reddit.com/api/v1/access_token",
                data={"grant_type": "client_credentials"},
                auth=(client_id, secret),
                headers={"User-Agent": "Praecantator/1.0"},
            )
            auth_r.raise_for_status()
            token = auth_r.json().get("access_token", "")
    except Exception:
        return []

    headers = {"Authorization": f"bearer {token}", "User-Agent": "Praecantator/1.0"}
    all_posts: list[dict] = []

    async with httpx.AsyncClient(timeout=15.0) as client:
        for sub in subreddits:
            try:
                r = await client.get(
                    f"https://oauth.reddit.com/r/{sub}/new.json",
                    params={"limit": 25}, headers=headers,
                )
                r.raise_for_status()
                all_posts.extend(r.json().get("data", {}).get("children", []))
            except Exception:
                continue

    topic_scores: dict[str, list[float]] = {"geopolitics": [], "logistics": []}
    notable: list[dict] = []
    news_domains = {"reuters.com", "bbc.com", "apnews.com", "bloomberg.com", "ft.com", "wsj.com"}

    for pw in all_posts:
        post = pw.get("data", {})
        title = str(post.get("title") or "")
        text = title.lower()
        domain = str(post.get("domain") or "").lower()
        score = _simple_sentiment(title)
        for topic, kws in topic_kw.items():
            if any(k in text for k in kws):
                topic_scores[topic].append(score)
        if any(d in domain for d in news_domains):
            label = "Positive" if score > 0.1 else ("Negative" if score < -0.1 else "Neutral")
            notable.append({
                "id": f"reddit_news_{_sid(title, domain)}",
                "event_type": "social_news_signal",
                "title": f"[{domain}] {title[:120]}",
                "location": "Global",
                "severity": 5.0 if score < -0.2 else 3.5,
                "lat": 0.0, "lng": 0.0,
                "source": "reddit",
                "source_category": "social_news",
                "sentiment": label,
                "sentiment_score": round(score, 3),
                "url": f"https://reddit.com{post.get('permalink', '')}",
                "created_at": _now(),
            })

    results: list[dict] = []
    for topic, scores in topic_scores.items():
        if not scores:
            continue
        pos = round(sum(1 for s in scores if s > 0.1) / len(scores) * 100, 1)
        neg = round(sum(1 for s in scores if s < -0.1) / len(scores) * 100, 1)
        neu = round(max(0.0, 100 - pos - neg), 1)
        results.append({
            "id": f"reddit_sentiment_{topic}",
            "event_type": "sentiment_aggregate",
            "title": f"Reddit BERT Sentiment — {topic.title()}",
            "location": "Global",
            "severity": 4.5,
            "lat": 0.0, "lng": 0.0,
            "source": "reddit",
            "source_category": "sentiment",
            "sentiment_topic": topic,
            "sentiment_positive_pct": pos,
            "sentiment_negative_pct": neg,
            "sentiment_neutral_pct": neu,
            "sentiment_post_count": len(scores),
            "url": "https://reddit.com",
            "created_at": _now(),
        })
    return results + notable[:8]


# Entry point used by scheduler (replaces old fetch_social_sentiment)
async def fetch_social_sentiment() -> list[dict]:
    """Aggregates all social/sentiment signals: Mastodon + HackerNews + Reddit (if keys set)."""
    results: list[dict] = []
    for fn in (fetch_mastodon_sentiment, fetch_hackernews_sentiment, fetch_reddit_sentiment):
        try:
            items = await fn()
            results.extend(items)
        except Exception:
            pass
    if results:
        return results
    return [
        _fallback_signal(
            signal_id="sentiment_fallback_logistics",
            event_type="sentiment_aggregate",
            title="Logistics sentiment watch active",
            location="Global",
            severity=4.0,
            source="sentiment_fallback",
            source_category="sentiment",
            url="https://news.ycombinator.com/",
            description="Social sentiment feeds returned no live public data; placeholder aggregate keeps the sentiment lane visible in development mode.",
        ),
        {
            **_fallback_signal(
                signal_id="social_news_fallback_monitor",
                event_type="social_news_signal",
                title="Social news monitor active",
                location="Global",
                severity=3.8,
                source="social_news_fallback",
                source_category="social_news",
                url="https://mastodon.social/",
                description="Public social-news feeds returned no live records; placeholder monitor keeps the category visible in development mode.",
            ),
            "sentiment": "Neutral",
            "sentiment_score": 0.0,
        },
    ]


# ─── Lexical BERT-proxy sentiment ─────────────────────────────────────────────

def _simple_sentiment(text: str) -> float:
    """Returns float in [-1.0, 1.0]. Dev-mode BERT approximation via lexical scoring."""
    t = text.lower()
    positives = [
        "recovery", "uplift", "resolved", "open", "resumed", "stable", "eased",
        "agreement", "deal", "lifted", "growth", "strong", "improvement", "normaliz",
    ]
    negatives = [
        "shutdown", "strike", "blocked", "sanction", "tariff", "ban", "war",
        "conflict", "disruption", "delay", "shortage", "congestion", "escalat",
        "closure", "halt", "suspend", "seized", "collapse", "risk", "crisis",
        "attack", "protest", "instab", "inflation", "restrict", "embargo",
    ]
    pos = sum(1 for w in positives if w in t)
    neg = sum(1 for w in negatives if w in t)
    total = pos + neg
    return 0.0 if total == 0 else round((pos - neg) / total, 3)


def _strip_html(text: str) -> str:
    """Quick HTML tag remover for Mastodon content fields."""
    import re
    return re.sub(r"<[^>]+>", "", text).strip()


async def fetch_gps_interference() -> list[dict]:
    """
    GPS jamming/interference adapter using a WorldMonitor-style normalized payload.
    Configure WINGBITS_GPS_URL or GPS_INTERFERENCE_URL to point at the public feed.
    """
    url = os.getenv("WINGBITS_GPS_URL", "").strip() or os.getenv("GPS_INTERFERENCE_URL", "").strip()
    if not url:
        return []

    headers = {"Accept": "application/json"}
    api_key = os.getenv("WINGBITS_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        headers["X-API-Key"] = api_key

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except Exception:
        return []

    hexes = payload.get("hexes") or []
    if not isinstance(hexes, list) or not hexes:
        return []

    top_hexes = sorted(
        [hex_item for hex_item in hexes if isinstance(hex_item, dict)],
        key=lambda item: (_parse_float(item.get("aircraftCount") or item.get("total")), _parse_float(item.get("sampleCount") or item.get("bad"))),
        reverse=True,
    )[:12]

    results: list[dict] = []
    for idx, hex_item in enumerate(top_hexes):
        level = str(hex_item.get("level") or "medium").strip().lower()
        lat = _parse_float(hex_item.get("lat"))
        lng = _parse_float(hex_item.get("lon"))
        aircraft = int(_parse_float(hex_item.get("aircraftCount") or hex_item.get("total")))
        severity = 7.5 if level == "high" else 5.5
        results.append({
            "id": f"gps_interference_{idx}_{_sid(hex_item.get('h3'), lat, lng)}",
            "event_type": "gps_interference",
            "title": f"GPS interference cluster ({level})",
            "description": f"Detected {level} GPS interference with {aircraft} aircraft observations in this cell.",
            "location": f"Lat {lat:.2f}, Lng {lng:.2f}",
            "severity": severity,
            "lat": lat,
            "lng": lng,
            "source": "wingbits_gps",
            "source_category": "geopolitical",
            "url": url,
            "created_at": _now(),
        })

    return results


async def fetch_wto_trade_signals() -> list[dict]:
    api_key = os.getenv("WTO_API_KEY", "").strip()
    if not api_key:
        return [
            _fallback_signal(
                signal_id="wto_trade_watch_global",
                event_type="trade_policy_watch",
                title="WTO trade policy watch active",
                location="Global",
                severity=4.7,
                source="wto",
                source_category="trade",
                url="https://stats.wto.org/",
                description="WTO API key is not configured; baseline trade-policy monitoring remains visible in development mode.",
            )
        ]

    reporters = ["840", "156", "356", "276", "392", "826"]
    current_year = datetime.now(timezone.utc).year
    results: list[dict] = []

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                f"{WTO_API_URL}/data",
                params={
                    "i": "TP_A_0010",
                    "r": ",".join(reporters),
                    "ps": f"{current_year - 2}-{current_year}",
                    "fmt": "json",
                    "mode": "full",
                    "max": "5000",
                },
                headers={"Ocp-Apim-Subscription-Key": api_key, "Accept": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
    except Exception:
        return []

    dataset = payload if isinstance(payload, list) else payload.get("Dataset") or payload.get("dataset") or []
    latest_by_reporter: dict[str, dict[str, Any]] = {}
    for row in dataset:
        if not isinstance(row, dict):
            continue
        reporter = str(row.get("ReportingEconomyCode") or "").strip()
        year = int(_parse_float(row.get("Year")))
        value = _parse_float(row.get("Value"), -1.0)
        if not reporter or year <= 0 or value < 0:
            continue
        existing = latest_by_reporter.get(reporter)
        if not existing or year > int(existing["year"]):
            latest_by_reporter[reporter] = {"year": year, "value": value}

    for reporter, info in latest_by_reporter.items():
        tariff = float(info["value"])
        if tariff < 3.0:
            continue
        country = _wto_country_label(reporter)
        results.append({
            "id": f"wto_tariff_{reporter}_{info['year']}",
            "event_type": "trade_tariff",
            "title": f"WTO MFN tariff baseline: {country}",
            "description": f"{country} reported a WTO MFN tariff baseline of {tariff:.1f}% for {int(info['year'])}.",
            "location": country,
            "severity": _clamp(3.0 + tariff / 2.0),
            "lat": 0.0,
            "lng": 0.0,
            "source": "wto",
            "source_category": "trade",
            "url": "https://stats.wto.org/",
            "created_at": _now(),
        })

    if results:
        return results
    return [
        _fallback_signal(
            signal_id="wto_trade_watch_baseline",
            event_type="trade_policy_watch",
            title="WTO tariff baseline watch active",
            location="Global",
            severity=4.7,
            source="wto",
            source_category="trade",
            url="https://stats.wto.org/",
            description="WTO feed returned no qualifying rows; baseline trade-policy monitoring remains visible in development mode.",
        )
    ]
