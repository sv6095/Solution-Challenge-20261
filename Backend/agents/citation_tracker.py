from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

SOURCE_TYPES: dict[str, tuple[str, bool]] = {
    "NASA EONET": ("government", True),
    "NewsAPI": ("news", False),
    "GDELT": ("geopolitical", False),
    "GNews": ("regional", False),
}

# Normalizes raw `source` strings from signal_agent payloads → display label
SOURCE_ALIASES: dict[str, str] = {
    "nasa_eonet": "NASA EONET",
    "gdelt": "GDELT",
    "newsapi": "NewsAPI",
    "gnews": "GNews",
}


@dataclass
class SignalCitation:
    source: str
    source_type: str
    verified: bool
    url: str
    title: str
    retrieved_at: str
    corroborated_by: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def display_source_label(raw: str | None) -> str:
    if not raw:
        return "unknown"
    key = raw.strip().lower()
    return SOURCE_ALIASES.get(key, raw.strip())


def build_citation(source_name: str, raw_item: dict[str, Any]) -> SignalCitation:
    label = display_source_label(source_name)
    stype, verified = SOURCE_TYPES.get(label, ("unknown", False))
    return SignalCitation(
        source=label,
        source_type=stype,
        verified=verified,
        url=str(raw_item.get("url") or raw_item.get("link") or ""),
        title=str(raw_item.get("title") or raw_item.get("event_type") or ""),
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        corroborated_by=[],
    )


def citation_to_dict(source_name: str, raw_item: dict[str, Any]) -> dict[str, Any]:
    return build_citation(source_name, raw_item).to_dict()


def events_overlap(a: dict[str, Any], b: dict[str, Any]) -> bool:
    ta = str(a.get("title") or "").lower().strip()
    tb = str(b.get("title") or "").lower().strip()
    if ta and tb:
        if ta in tb or tb in ta:
            return True
        if min(len(ta), len(tb)) >= 24 and ta[:24] == tb[:24]:
            return True
    la = str(a.get("location") or "").lower().strip()
    lb = str(b.get("location") or "").lower().strip()
    if la and lb and la == lb:
        return True
    try:
        alat, alng = float(a.get("lat")), float(a.get("lng"))
        blat, blng = float(b.get("lat")), float(b.get("lng"))
        if abs(alat - blat) < 2.5 and abs(alng - blng) < 2.5:
            return True
    except (TypeError, ValueError):
        pass
    return False


def mark_corroborations(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for s in signals:
        cit = s.get("citation")
        if not isinstance(cit, dict):
            continue
        corroborated = cit.setdefault("corroborated_by", [])
        if not isinstance(corroborated, list):
            cit["corroborated_by"] = []
            corroborated = cit["corroborated_by"]
        for other in signals:
            if s is other:
                continue
            if not events_overlap(s, other):
                continue
            ocit = other.get("citation") if isinstance(other.get("citation"), dict) else {}
            src = str(ocit.get("source") or display_source_label(str(other.get("source") or "")))
            if src and src not in corroborated:
                corroborated.append(src)
        cit["corroboration_count"] = len(corroborated)
    return signals


def enrich_signal_item(item: dict[str, Any]) -> dict[str, Any]:
    raw_src = str(item.get("source") or "")
    item["citation"] = citation_to_dict(raw_src, item)
    return item
