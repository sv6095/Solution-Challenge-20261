# Praecantator Backend Engine: Architecture & Technical Operations

The Praecantator Backend is the highly resilient, fully autonomous engine driving the supply chain risk intelligence platform. This document serves as an exhaustive breakdown of the architectural philosophies, multi-agent frameworks, enterprise constraint policies, and core Python modules governing the system's execution context.

Our objective with the backend is to facilitate "Zero-Touch" threat detection mapping precisely to actionable operational outcomes (e.g., dynamically rerouting logistics networks globally), securely shielded by rigorous enterprise grade access policies.

---

## 1. Architectural Foundations

### 1.1 Stateless Edge / Stateful Subsystems
The Praecantator backend is designed to operate seamlessly across high-availability multi-instance deployments. 
- **The FastAPI Edge:** The API layer is natively stateless. Identity verification, Request scoping, and Tenant extraction occur globally at the middleware dependency layer without touching the database via secure JWT propagation.
- **The State Storage (`services.local_store`):** All structured data logic is strictly relegated to our `local_store` module, providing SQLite persistence meant to effortlessly match production Firestore architectures. Context payloads are dynamically unrolled into discrete relational `graph_nodes` ensuring thread-safe transactional updates globally.
- **The Graph Representation (`models.supply_graph`):** Supply chain networks are strictly mathematical. Using underlying Graph Neural Network (GNN) principles in PyTorch (and encapsulated effectively in `CustomerSupplyGraph`), all vendor data is synthesized into isolated Spatial Quadrant nodes preventing Out of Memory (OOM) failures natively during live disaster evaluations.
- **Live ERP State Sync:** Instead of relying on static configurations from onboarding models, operational telemetry (like localized margin percent and live safety stock burn rate) dynamically injects into the execution boundary via `services/erp_sync.py` prior to invoking mathematical propagation logic.

### 1.2 The OODA Loop Pipeline
At the absolute core of the risk management platform lies the `autonomous_pipeline.py`. Relying on LangGraph for deterministic graph iterations, Praecantator translates intelligence intercepts into actionable items using the `[DETECT -> ASSESS -> DECIDE -> ACT -> AUDIT]` cognitive loop.

Instead of generating unstructured text, Large Language Models run in strict constrained schemas dictating parameters like "Re-Routed Ports", "Total USD Savings", and "Fallback Vendors."

---

## 2. Core Operational Modules

### 2.1 Multi-Agent Orchestration & Determinism
Located in `agents/autonomous_pipeline.py`, the autonomous pipeline drives business logic using specialized analytical agents.

*   **Political Risk / Signal Agent (`political_risk_agent.py`):** Operates on the frontlines actively crawling structured sources (GDELT, NASA, Mastodon) and mapping "Risk Polygons." Its explicit job is finding spatial overlaps between an external disruption and the secure bounds of a customer's specific hardware components.
*   **Assessment Agent:** Synthesizes the downstream delays. Instead of making generic warnings, this step predicts structural disruption impacts.
*   **Routing Agent (`routing_evaluator.py`):** Acts as the logistical brain. Leveraging supply network edges mapped within the master `CustomerSupplyGraph`, the agent calculates temporal and cost savings. Utilizing simulated multi-modal transportation, it outputs mathematically proven shipment options.
*   **RFQ & Audit Agent:** Transitions virtual mathematical outcomes into real-world business mechanics by drafting communication and definitively compiling the full trace of an executed run.

### 2.2 Enterprise Isolation & Tenancy Governance
The primary requirement for operating B2B Multi-Tenant platforms is preventing "data bleed." Praecantator employs pervasive isolation protocols.

*   **Authorization Substrate (`services.authorization.py`):** Introduces Role-Based Access Controls (RBAC). It evaluates internal policy schemas, confirming that users inherently contain permissions required to interact with API endpoints. If an onboarded user with `tenant_A` attempts to access logistics mapped natively for `tenant_B`, the endpoint evaluates the incoming bearer token logic, instantly dropping the request and returning `403 Forbidden`.
*   **Strict Context Boundary (`services.tenant_quota.py`):** Every API transaction is tightly bound through a contextual barrier explicitly ensuring load limits and payload separation.

### 2.3 Reliability: Idempotency & Fault Tolerance
Since Praecantator relies strictly on automated LLM execution crossing multiple network hurdles, maintaining deterministic reliability is quintessential.

*   **Idempotency Guards (`services.idempotency.py`):** Interacts flawlessly with the `action_confirmation.py` implementation. Should a pipeline break midway during the `ACT` execution stage due to SMTP failures or API quotas, the idempotency cache traps the duplicate request. It forces any execution trace to explicitly be evaluated against the operational payload structure before moving on.
*   **Compensation and State Recovery:** The `stage_policy.py` file details what must be completed before agents pass information to adjacent nodes. If a failure is found, the system is forced into a terminal fallback state, awaiting a manual replay initialization (`replay_autonomous_run()`).

### 2.4 Governance & Safety Protocols
To maintain operator trust, the system integrates heavy procedural checkpoints for human validation.

*   **Checkpoints (`services.governance_checkpoint.py`):** If a disruption algorithm detects a multi-million dollar threat that intends to invoke radical logistical alterations, the pipeline halts immediately after the `DECIDE` stage. An internal checkpoint generates a required operational review layer. An action is permanently disabled from executing globally until an authoritative human explicitly grants permission.
*   **Reasoning Logger (`agents.reasoning_logger.py`):** No decision is permitted as a "black box." Every AI node inherently executes `log_reasoning_step()`, recording internal metadata processing details chronologically. This is fully streamed onto the front-end to act as a granular audit trail.

---

## 3. Data Integrity & Verification

### 3.1 Network Canonicalization & Validation
To guarantee mapping consistency, generic external names are forcefully rejected unless validated by `services.master_data_validator.py`.
Users must provide legitimate geospatial constraints. If spatial bounding constraints fail, a deterministic fuzzy string-matching fallback actively searches global signal text matrices against exact entity mapping names protecting against zero-match failure latency.
Staging validation boundaries explicitly check for DUNS / LEI duplications mitigating cascading data conflicts *prior* to finalizing JSON state payloads.

### 3.2 Action Ledgering
Any modification to endpoints must leave physical traces. The `action_confirmation.py` handles tracking event sequences such as transitioning logic from `DRAFT`, validating logic passing as `SENT`, waiting for third-party inputs acknowledging the event as `DELIVERED`, and finishing as `ACKNOWLEDGED`. The separation of internal calculation states from external truth guarantees no single point of arbitrary modification.

---

## 4. Scaling Considerations & Phase Evolution

The architecture is currently functioning optimally within the limits of its current implementation goals. To advance the backend capabilities, developers should consider referencing:

1.  **Phase 0 (Containment):** The foundation established in strict policy execution and bypassing elimination protocols.
2.  **Phase 1 (Correctness):** Unifying dynamic spatial processing mapping explicitly bound toward `CustomerSupplyGraph`.
3.  **Phase 2 (Reliability):** Eliminating hanging transactions, wrapping states within deterministic idempotency closures.
4.  **Phase 3 (Scalability):** Future updates dictating specific Redis node queuing allocations and advanced Celery workers matching massive input spikes.
5.  **Phase 4 & 5 (Operational Trust):** Current state of the art establishing fully compliant evidence ledgers for Service Level Agreements regarding isolation validation and governance audits.

---

## 5. System Execution Examples

When a catastrophic typhoon forces port closures along the coast of the Pacific, the `Signal Agent` detects the perimeter bounds. 

1. Within strict data partitions, `tenant_id: x-apple-corp` assesses overlapping geometry of their global node graphs, flagging 12 major vendors under critical impact delays.
2. The `Workflow Pipeline` securely assesses fallback algorithms against global indices. 
3. LLMs generate exact metrics identifying a multi-modal shift via land transportation that would optimize savings by `$145,000` while shifting temporal parameters forward by an exact factor of 4 days.
4. An `Audit Trail` flags the multi-million dollar adjustment resulting in a firm governance barrier.
5. Operator logs into the React interface, verifying the reasoning trails before natively dismissing the safety protocols, executing the actual routing algorithms directly to target destination software safely.

Praecantator’s Python ecosystem allows for uninterrupted execution scaling limitlessly depending on assigned hardware while ensuring perfect fidelity logic without compromise.
