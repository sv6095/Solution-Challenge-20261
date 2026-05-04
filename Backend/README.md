# Praecantator Backend

FastAPI service powering the Praecantator SCRM platform. Orchestrates a 7-step autonomous pipeline, trained GNN risk propagation, a multi-agent LangGraph workflow, and a real-time global intelligence cache.

---

## Directory Map

```
Backend/
├── main.py                        # All API routes
├── agents/
│   ├── autonomous_pipeline.py     # 7-step master orchestration
│   ├── signal_agent.py            # Event ingest & proximity scoring
│   ├── graph_agent.py             # Supply chain graph construction
│   ├── assessment_agent.py        # Severity, stockout, exposure
│   ├── routing_agent.py           # Multi-modal route comparison
│   ├── decision_agent.py          # Pre-gate recommendation
│   ├── rfq_agent.py               # Backup supplier & RFQ draft
│   ├── action_agent.py            # Post-approval execution
│   ├── audit_agent.py             # Immutable step logging
│   └── reasoning_logger.py        # Per-agent narrative (Groq)
├── ml/
│   ├── gnn_model.py               # GraphSAGE + GAT — inference & training
│   ├── gnn_stub.py                # Heuristic fallback
│   └── gnn_weights.pt             # Trained weights (gitignored)
├── services/
│   ├── worldmonitor_fetcher.py    # 17-source cron intelligence layer
│   ├── governance_checkpoint.py   # HITL trigger + operator feedback
│   ├── llm_provider.py            # Gemini / Groq unified interface
│   ├── authorization.py           # RBAC — Principal / Permission
│   ├── data_quality_guard.py      # Signal completeness gates
│   ├── idempotency.py             # Duplicate incident prevention
│   └── local_store.py             # SQLite schema & CRUD
├── workflows/
│   └── langgraph_workflow.py      # Stateful LangGraph agent graph
└── requirements.txt
```

---

## Autonomous Pipeline

`agents/autonomous_pipeline.py` — `run_pipeline()`

| Step | Description |
|---|---|
| 1. Signal pull | Live events from WorldMonitor SQLite cache |
| 2. GNN propagation | GraphSAGE + GAT assigns risk scores to supplier nodes |
| 3. Value-at-Risk | `exposure = contract × score × duration_factor` |
| 4. Cluster / dedup | Haversine-based incident merging |
| 5. Assessment | Severity classification + stockout days |
| 6. Route analysis | Air / sea / land options scored |
| 7. Governance gate | Threshold check → PENDING or auto-proceed |

---

## GNN Model

`ml/gnn_model.py` — `SupplyChainGNN`

**Architecture:** `SAGEConv(9→32) → GATConv(32→16, heads=2) → Linear(32→1) + Sigmoid`

**9 input features per node:**
proximity, event severity, supplier tier, criticality, single-source flag, contract value (log), safety stock inverse, substitutability inverse, location precision.

**Training:** Operator verdicts (`TRUE_POSITIVE / FALSE_POSITIVE`) from `governance_feedback` table are used as labels. Trigger with `POST /ml/train` (requires ≥ 5 records). Falls back to `gnn_stub.py` heuristic when no weights exist.

---

## LangGraph Workflow

`workflows/langgraph_workflow.py`

```
signal → assessment → routing
                         │
                  governance_gate
                    /           \
              human_gate    auto_proceed
                    \           /
                    rfq_agent
                         │
                   action_agent → audit_agent → END
```

Persistent checkpoints (SQLite-backed) allow the workflow to pause at `human_gate`, survive restarts, and resume on operator approval via `POST /workflow/{id}/approve`.

---

## WorldMonitor Intelligence Layer

`services/worldmonitor_fetcher.py` — 17 async fetchers on APScheduler cron:

| Source | Data | Cadence |
|---|---|---|
| NASA EONET | Natural hazards | 30 min |
| USGS | Earthquakes M4.5+ | 15 min |
| GDACS | Global disaster alerts | 30 min |
| NASA FIRMS | Fire detections | 2 h |
| ACLED | Armed conflict | 2 h |
| GDELT | Geopolitical events | 1 h |
| NewsAPI | Supply chain news | 30 min |
| Finnhub | Market quotes | 15 min |
| EIA | Energy prices | 1 h |
| FRED | Macro indicators | 4 h |
| OpenAQ | Port city air quality | 2 h |
| AviationStack | Cargo hub flights | 1 h |
| Chokepoint scorer | 10 strategic chokepoints | 15 min |
| Country instability | ACLED + EONET aggregation | 30 min |
| Shipping stress | Chokepoint + carrier risk | 15 min |
| Market implications | LLM or heuristic summary | 1 h |
| Strategic risk | Composite 0–100 score | 15 min |

---

## Governance Checkpoint

`services/governance_checkpoint.py`

Escalates to PENDING human review when **any** condition is true:

| Condition | Default threshold |
|---|---|
| Severity | CRITICAL or HIGH |
| Financial exposure | ≥ $500,000 |
| Sole-source supplier | Any affected node |
| FP history | Operator flagged similar incident |

---

## API Reference (key groups)

| Group | Endpoints |
|---|---|
| Auth | `POST /auth/register`, `/auth/login`, `/auth/refresh` |
| Command | `GET /command/briefing` |
| Incidents | `GET /incidents/summary`, `POST /incidents/generate` |
| Workflow | `POST /workflow/start`, `GET /workflow/state/{id}`, `POST /workflow/{id}/approve` |
| Signals | `GET /signals/categorized`, `POST /signals/refresh` |
| Intelligence | `POST /intelligence/monte-carlo`, `GET /intelligence/gaps` |
| Global | `GET /global/hazards`, `/global/chokepoints`, `/global/strategic-risk`, … |
| RFQ | `GET /rfq`, `POST /rfq`, `PATCH /rfq/{id}` |
| Audit | `GET /audit`, `GET /audit/compliance` |
| ML | `POST /ml/train` |
| Reasoning | `GET /workflow/reasoning/{id}/render` |

---

## Setup

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Required `.env` keys

```env
GOOGLE_API_KEY=...
GROQ_API_KEY=...
FIREBASE_PROJECT_ID=...
FIREBASE_PRIVATE_KEY=...
FIREBASE_CLIENT_EMAIL=...
UPSTASH_REDIS_URL=...
UPSTASH_REDIS_TOKEN=...
# Optional data source keys
ACLED_API_KEY=...
NEWSAPI_API_KEY=...
NASA_FIRMS_MAP_KEY=...
FINNHUB_API_KEY=...
EIA_API_KEY=...
FRED_API_KEY=...
LOCAL_DB_PATH=./local_fallback.db
```
