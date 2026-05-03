"""
ERP Integration Mock — Live Inventory & Throughput Synchronization

Real-world SCRM cannot rely on static `safety_stock_days` captured during onboarding.
This service acts as the integration layer with SAP/Oracle/Dynamics. Before the IncidentEngine 
runs its forward pass, it optionally queries this service to inject real-time operational state.
"""
import random
from typing import Dict, Any

def fetch_live_node_state(duns_number: str, internal_id: str) -> Dict[str, Any]:
    """
    Simulates fetching real-time ERP telemetry. 
    In production, this would call SAP OData or Oracle NetSuite REST APIs.
    """
    # For demo purposes, we randomly decay safety stock to simulate burn rate
    # and adjust daily throughput to signify recent production ramps.
    
    # We use a deterministic seed so the demo is stable across the same incident run
    random.seed(hash(duns_number or internal_id) % 10000)
    
    return {
        "live_safety_stock_days": max(1, int(random.gauss(5, 3))),
        "live_daily_throughput_usd": max(0.0, random.gauss(12000.0, 5000.0)),
        "margin_percentage": random.uniform(0.15, 0.40), # Live gross margin on these components
        "last_sync_time": "Just now (SAP ECC6)"
    }
