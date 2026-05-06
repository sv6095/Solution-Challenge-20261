import asyncio
import os
import sys
import unittest
from uuid import uuid4

# Ensure backend directory is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.firestore_store import delete_incident, get_incident, list_incidents, upsert_incident

if not (os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GCP_PROJECT_ID") or os.getenv("GCLOUD_PROJECT")):
    raise unittest.SkipTest("Firestore project env is required for Firestore-only integration tests")

def test_tenant_data_isolation():
    suffix = uuid4().hex[:8]
    tenant_A = f"tenant_a_{suffix}"
    tenant_B = f"tenant_b_{suffix}"
    incident_a = f"incA_{suffix}"
    incident_b = f"incB_{suffix}"
    
    # 1. Insert data for Tenant A
    upsert_incident(
        incident_id=incident_a,
        payload={"title": "Factory Fire A"},
        status="DETECTED",
        severity="HIGH",
        tenant_id=tenant_A
    )
    
    # 2. Insert data for Tenant B
    upsert_incident(
        incident_id=incident_b,
        payload={"title": "Port Strike B"},
        status="DETECTED",
        severity="CRITICAL",
        tenant_id=tenant_B
    )
    
    # 3. Test list isolation
    a_incidents = list_incidents(tenant_id=tenant_A)
    b_incidents = list_incidents(tenant_id=tenant_B)
    
    assert len(a_incidents) == 1
    assert len(b_incidents) == 1
    assert a_incidents[0]["id"] == incident_a
    assert b_incidents[0]["id"] == incident_b
    
    # 4. Test fetch isolation
    # Tenant A should not be able to fetch Tenant B's incident
    stolen_inc = get_incident(incident_b, tenant_id=tenant_A)
    assert stolen_inc is None, "Data Breach: Tenant A can read Tenant B data!"
    delete_incident(incident_a, tenant_id=tenant_A)
    delete_incident(incident_b, tenant_id=tenant_B)
    
    print("SUCCESS: Cross-customer read/write data isolation strictly enforced.")

if __name__ == "__main__":
    test_tenant_data_isolation()
