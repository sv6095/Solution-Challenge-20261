import asyncio
import os
from pathlib import Path
import sys

# Ensure backend directory is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.local_store import upsert_incident, get_incident, list_incidents

def test_tenant_data_isolation():
    tenant_A = "tenant_a_123"
    tenant_B = "tenant_b_456"
    
    # 1. Insert data for Tenant A
    upsert_incident(
        incident_id="incA_001",
        payload={"title": "Factory Fire A"},
        status="DETECTED",
        severity="HIGH",
        tenant_id=tenant_A
    )
    
    # 2. Insert data for Tenant B
    upsert_incident(
        incident_id="incB_001",
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
    assert a_incidents[0]["id"] == "incA_001"
    assert b_incidents[0]["id"] == "incB_001"
    
    # 4. Test fetch isolation
    # Tenant A should not be able to fetch Tenant B's incident
    stolen_inc = get_incident("incB_001", tenant_id=tenant_A)
    assert stolen_inc is None, "Data Breach: Tenant A can read Tenant B data!"
    
    print("SUCCESS: Cross-customer read/write data isolation strictly enforced.")

if __name__ == "__main__":
    test_tenant_data_isolation()
