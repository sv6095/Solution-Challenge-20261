from __future__ import annotations

from datetime import datetime, timezone

import httpx


async def fetch_nasa_eonet() -> list[dict]:
    async with httpx.AsyncClient(timeout=12.0) as client:
        r = await client.get(
            "https://eonet.gsfc.nasa.gov/api/v3/events",
            params={
                "status": "open",
                "limit": 20,
                "days": 7,
                "category": "severeStorms,wildfires,volcanoes,floods,landslides,drought,earthquakes",
            },
        )
        r.raise_for_status()
        data = r.json()
    events = []
    for e in data.get("events", []):
        coord = (e.get("geometry") or [{}])[-1].get("coordinates", [0, 0])
        source_url = ""
        sources = e.get("sources") or []
        if sources and isinstance(sources, list):
            source_url = str((sources[0] or {}).get("url") or "")
        events.append(
            {
                "id": f"eonet_{e.get('id')}",
                "event_type": (e.get("categories") or [{"id": "unknown"}])[0].get("id", "unknown"),
                "location": e.get("title", "unknown"),
                "severity": 7.0,
                "lng": coord[0] if len(coord) > 1 else 0,
                "lat": coord[1] if len(coord) > 1 else 0,
                "source": "nasa_eonet",
                "title": e.get("title", "unknown"),
                "url": source_url,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    return events


async def fetch_gdelt() -> list[dict]:
    async with httpx.AsyncClient(timeout=12.0) as client:
        r = await client.get(
            "https://api.gdeltproject.org/api/v2/doc/doc",
            params={
                "query": "supply chain disruption port strike",
                "mode": "artlist",
                "maxrecords": 10,
                "format": "json",
                "timespan": 1440,
            },
        )
        r.raise_for_status()
        data = r.json()
    return [
        {
            "id": f"gdelt_{i}",
            "event_type": "geopolitical_news",
            "location": item.get("sourcecountry", "unknown"),
            "severity": 5.0,
            "source": "gdelt",
            "title": item.get("title", "news"),
            "url": item.get("url", ""),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        for i, item in enumerate(data.get("articles", []))
    ]


async def fetch_newsapi(api_key: str | None) -> list[dict]:
    if not api_key:
        return []
    async with httpx.AsyncClient(timeout=12.0) as client:
        r = await client.get(
            "https://newsapi.org/v2/everything",
            params={"q": "supply chain disruption", "pageSize": 10, "sortBy": "publishedAt", "apiKey": api_key},
        )
        r.raise_for_status()
        data = r.json()
    return [
        {
            "id": f"newsapi_{i}",
            "event_type": "news_signal",
            "location": "global",
            "severity": 4.0,
            "source": "newsapi",
            "title": item.get("title", "headline"),
            "url": item.get("url", ""),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        for i, item in enumerate(data.get("articles", []))
    ]


async def fetch_gnews(api_key: str | None) -> list[dict]:
    if not api_key:
        return []
    async with httpx.AsyncClient(timeout=12.0) as client:
        r = await client.get(
            "https://gnews.io/api/v4/search",
            params={"q": "logistics disruption", "lang": "en", "max": 10, "apikey": api_key},
        )
        r.raise_for_status()
        data = r.json()
    return [
        {
            "id": f"gnews_{i}",
            "event_type": "regional_news",
            "location": "global",
            "severity": 4.0,
            "source": "gnews",
            "title": item.get("title", "headline"),
            "url": item.get("url", ""),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        for i, item in enumerate(data.get("articles", []))
    ]
