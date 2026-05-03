from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "Dataset"

PORTS_PATH = DATASET_DIR / "ports.json"
DISRUPTION_PATH = DATASET_DIR / "Global_Supply_Chain_Disruption.csv"
PREDICTIVE_PATH = DATASET_DIR / "Predective_Forecasting.csv"
AIRPORTS_PATH = DATASET_DIR / "airports.json"
HEALTH_SNAPSHOT_PATH = ROOT / "data_registry_health.json"


@dataclass(frozen=True)
class PortPoint:
    city: str
    country: str
    lat: float
    lng: float


class DataRegistry:
    def __init__(self) -> None:
        self.ports: list[PortPoint] = []
        self.airports: list[dict[str, Any]] = []
        self.sea_lane_multiplier: dict[str, float] = {}
        self.mode_cost_baseline: dict[str, float] = {}
        self.assessment_cost_by_event: dict[str, float] = {}
        self._load_ports()
        self._load_airports()
        self._load_disruption_stats()
        self._load_predictive_stats()

    def _load_ports(self) -> None:
        if not PORTS_PATH.exists():
            return
        payload = json.loads(PORTS_PATH.read_text(encoding="utf-8"))
        rows: list[PortPoint] = []
        for row in payload:
            try:
                rows.append(
                    PortPoint(
                        city=str(row.get("CITY", "")).strip(),
                        country=str(row.get("COUNTRY", "")).strip(),
                        lat=float(row["LATITUDE"]),
                        lng=float(row["LONGITUDE"]),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        self.ports = rows

    def _load_disruption_stats(self) -> None:
        if not DISRUPTION_PATH.exists():
            return

        lane_ratios: dict[str, list[float]] = {}
        mode_costs: dict[str, list[float]] = {}

        with DISRUPTION_PATH.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                route_type = (row.get("Route_Type") or "").strip()
                mode = (row.get("Transportation_Mode") or "").strip().lower()
                try:
                    base_days = float(row.get("Base_Lead_Time_Days") or 0)
                    actual_days = float(row.get("Actual_Lead_Time_Days") or 0)
                    shipping_cost = float(row.get("Shipping_Cost_USD") or 0)
                except ValueError:
                    continue

                if route_type and base_days > 0 and actual_days > 0:
                    lane_ratios.setdefault(route_type, []).append(actual_days / base_days)
                if mode and shipping_cost > 0:
                    mode_costs.setdefault(mode, []).append(shipping_cost)

        self.sea_lane_multiplier = {k: round(median(v), 3) for k, v in lane_ratios.items() if v}
        self.mode_cost_baseline = {k: round(median(v), 2) for k, v in mode_costs.items() if v}

    def _load_airports(self) -> None:
        if not AIRPORTS_PATH.exists():
            self.airports = []
            return
        try:
            payload = json.loads(AIRPORTS_PATH.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                self.airports = payload
            elif isinstance(payload, dict):
                self.airports = list(payload.values())
            else:
                self.airports = []
        except Exception:
            self.airports = []

    def _load_predictive_stats(self) -> None:
        if not PREDICTIVE_PATH.exists():
            return
        by_event: dict[str, list[float]] = {}
        with PREDICTIVE_PATH.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                event_type = (row.get("event_type") or "").strip()
                try:
                    cost = float(row.get("cost_impact_usd") or 0)
                except ValueError:
                    continue
                if event_type and cost > 0:
                    by_event.setdefault(event_type, []).append(cost)
        self.assessment_cost_by_event = {k: round(median(v), 2) for k, v in by_event.items() if v}

    def find_port_by_city_country(self, city: str | None, country: str | None) -> PortPoint | None:
        if not city or not country:
            return None
        city_norm = city.strip().lower()
        country_norm = country.strip().lower()
        for port in self.ports:
            if port.city.lower() == city_norm and port.country.lower() == country_norm:
                return port
        for port in self.ports:
            if port.city.lower() == city_norm:
                return port
        return None


registry = DataRegistry()


def disruption_snapshot() -> dict[str, Any]:
    return {
        "ports_loaded": len(registry.ports),
        "airports_loaded": len(registry.airports),
        "lane_multipliers_loaded": len(registry.sea_lane_multiplier),
        "mode_baselines_loaded": len(registry.mode_cost_baseline),
        "assessment_events_loaded": len(registry.assessment_cost_by_event),
    }


def data_registry_health_report() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    files = {
        "ports": PORTS_PATH,
        "airports": AIRPORTS_PATH,
        "disruption": DISRUPTION_PATH,
        "predictive": PREDICTIVE_PATH,
    }
    freshness: dict[str, Any] = {}
    completeness = {
        "ports_loaded": len(registry.ports),
        "airports_loaded": len(registry.airports),
        "lane_multipliers_loaded": len(registry.sea_lane_multiplier),
        "mode_baselines_loaded": len(registry.mode_cost_baseline),
        "assessment_events_loaded": len(registry.assessment_cost_by_event),
    }
    for name, path in files.items():
        if not path.exists():
            freshness[name] = {"exists": False, "age_hours": None}
            continue
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        age_hours = round((now - mtime).total_seconds() / 3600.0, 2)
        freshness[name] = {"exists": True, "age_hours": age_hours, "updated_at": mtime.isoformat()}

    current_signature = {
        "ports_loaded": completeness["ports_loaded"],
        "airports_loaded": completeness["airports_loaded"],
        "lane_keys": sorted(list(registry.sea_lane_multiplier.keys()))[:20],
        "event_types": sorted(list(registry.assessment_cost_by_event.keys()))[:20],
    }
    previous_signature: dict[str, Any] = {}
    drift = {"status": "unknown", "changed_fields": []}
    if HEALTH_SNAPSHOT_PATH.exists():
        try:
            previous_signature = json.loads(HEALTH_SNAPSHOT_PATH.read_text(encoding="utf-8"))
            if isinstance(previous_signature, dict):
                for key, value in current_signature.items():
                    if previous_signature.get(key) != value:
                        drift["changed_fields"].append(key)
                drift["status"] = "drift_detected" if drift["changed_fields"] else "stable"
        except Exception:
            drift["status"] = "unavailable"
    else:
        drift["status"] = "baseline_missing"

    try:
        HEALTH_SNAPSHOT_PATH.write_text(json.dumps(current_signature, indent=2), encoding="utf-8")
    except Exception:
        pass

    completeness_ok = all(v > 0 for v in completeness.values())
    freshness_ok = all(
        (not info.get("exists")) or (info.get("age_hours") is not None and float(info["age_hours"]) <= 24 * 30)
        for info in freshness.values()
    )

    return {
        "freshness": freshness,
        "completeness": completeness,
        "drift": drift,
        "healthy": bool(completeness_ok and freshness_ok),
    }
