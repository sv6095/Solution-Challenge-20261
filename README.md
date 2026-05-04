# Praecantator — Supply Chain Risk Management Platform

> **Autonomous detection. GNN-powered propagation. Human-in-the-loop governance.**

Praecantator is an enterprise SCRM (Supply Chain Risk Management) platform that watches global signals 24/7, maps every disruption to your supplier network via a trained Graph Neural Network, and drives response actions through a governed, multi-agent workflow—escalating to human reviewers only when financial or strategic thresholds demand it.

---

## Problem Statement

Supply chain disruptions are identified too late, assessed too slowly, and mitigated with too little context. Traditional approaches are:

- **Siloed** — weather data, geopolitical feeds, and logistics signals live in separate tools
- **Manual** — analysts triage hundreds of daily alerts without automated prioritisation
- **Reactive** — decisions are made days after the event, when financial exposure has already accumulated
- **Opaque** — there is no auditable trail from raw signal to executed action

---

## What Praecantator Does

| Capability | How |
|---|---|
| **Global signal ingestion** | 17-source WorldMonitor cron layer (NASA EONET, USGS, GDACS, ACLED, GDELT, NewsAPI, Finnhub, EIA, FRED, OpenAQ, and more) |
| **Supplier graph modelling** | Customer's supply chain encoded as a typed graph (Tier 1/2/3 suppliers, logistics hubs, routes) |
| **GNN risk propagation** | GraphSAGE + GAT model propagates disruption risk across the graph using Haversine proximity + learned node features |
| **Autonomous pipeline** | 7-step pipeline runs without human touch: signal → GNN → assessment → routing → VaR → clustering → governance gate |
| **Human-in-the-loop gate** | Critical/High severity, >$500k exposure, or sole-source suppliers force mandatory operator sign-off |
| **LangGraph workflow engine** | Stateful, resumable multi-agent workflow with conditional routing between automated agents and the human gate |
| **Monte Carlo simulation** | 300-run stochastic simulation producing P10/P50/P90 arrival distribution and expected exposure avoided |
| **RFQ automation** | Backup supplier identification and RFQ drafting triggered post-approval |
| **Compliance audit trail** | Every agent step, operator decision, and workflow transition is logged and exportable |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    GLOBAL INTELLIGENCE                  │
│   NASA EONET · USGS · GDACS · ACLED · GDELT · NewsAPI  │
│   Finnhub · EIA · FRED · OpenAQ · AviationStack · AIS  │
└──────────────────────┬──────────────────────────────────┘
                       │  APScheduler cron (15–240 min cadence)
                       ▼
┌─────────────────────────────────────────────────────────┐
│              WorldMonitor Fetcher (SQLite / Firestore)  │
│   Chokepoint scoring · Country instability index        │
│   Shipping stress · Strategic risk composite            │
│   Market implications (LLM-generated or heuristic)     │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│           AUTONOMOUS PIPELINE  (autonomous_pipeline.py) │
│                                                         │
│  1. Signal pull      → live events within last N hours  │
│  2. GNN propagation  → GraphSAGE + GAT per supplier node│
│  3. VaR computation  → contract × score × duration      │
│  4. Cluster / dedup  → Haversine-based incident merging │
│  5. Assessment       → severity, stockout days          │
│  6. Routing analysis → air / sea / land options         │
│  7. Governance gate  → trigger thresholds → PENDING     │
└──────────────────────┬──────────────────────────────────┘
                       │
           ┌───────────┴───────────┐
           │                       │
           ▼                       ▼
  Auto-approved              HUMAN GATE
  (low risk)            (operator review UI)
           │                       │
           └───────────┬───────────┘
                       │ Approval / Rejection
                       ▼
┌─────────────────────────────────────────────────────────┐
│            LangGraph Workflow Engine                    │
│   signal_agent → assessment_agent → routing_agent       │
│   → human_gate → rfq_agent → action_agent → audit_agent│
│   Persistent checkpoints · Resumable state machine      │
└─────────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│                 FASTAPI BACKEND  (main.py)              │
│   /command  /incidents  /workflow  /signals  /global    │
│   /rfq  /audit  /intelligence  /exposure  /auth         │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│           REACT DASHBOARD  (Vite + shadcn/ui)           │
│   CommandCenter · NetworkView · Intelligence            │
│   IncidentSimulator · RouteViewer · Compliance          │
│   MapLibre GL · TanStack Query · Recharts               │
└─────────────────────────────────────────────────────────┘
```

---

## Repository Structure

```
Praecantator/
├── Backend/                   # FastAPI service
│   ├── main.py                # API gateway — all routes
│   ├── agents/
│   │   ├── autonomous_pipeline.py   # 7-step orchestration
│   │   ├── signal_agent.py          # Event ingestion & scoring
│   │   ├── assessment_agent.py      # Severity classification
│   │   ├── routing_agent.py         # Multi-modal route analysis
│   │   ├── rfq_agent.py             # Backup supplier & RFQ
│   │   ├── decision_agent.py        # Human-gate recommendation
│   │   ├── action_agent.py          # Execution post-approval
│   │   └── audit_agent.py           # Immutable audit log
│   ├── ml/
│   │   ├── gnn_model.py             # GraphSAGE + GAT inference & training
│   │   ├── gnn_stub.py              # Heuristic fallback (no weights)
│   │   └── gnn_weights.pt           # Trained model weights (gitignored)
│   ├── services/
│   │   ├── worldmonitor_fetcher.py  # 17-source global cron fetcher
│   │   ├── governance_checkpoint.py # HITL trigger & feedback loop
│   │   ├── llm_provider.py          # Gemini / Groq abstraction
│   │   ├── authorization.py         # Principal / Permission RBAC
│   │   ├── data_quality_guard.py    # Signal quality gates
│   │   ├── idempotency.py           # Duplicate incident guard
│   │   └── local_store.py           # SQLite persistence layer
│   ├── workflows/
│   │   └── langgraph_workflow.py    # Stateful agent graph
│   ├── requirements.txt
│   └── README.md
│
├── Frontend/                  # Vite + React + TypeScript
│   ├── src/
│   │   ├── App.tsx                  # Router (6 dashboard pages)
│   │   ├── lib/api.ts               # Typed API client
│   │   ├── pages/dashboard/
│   │   │   ├── CommandCenter.tsx    # KPI map + incident table
│   │   │   ├── NetworkView.tsx      # MapLibre supplier graph
│   │   │   ├── Intelligence.tsx     # Signal feed + Monte Carlo
│   │   │   ├── IncidentSimulator.tsx# Full incident lifecycle
│   │   │   ├── RouteViewer.tsx      # Multi-modal logistics routes
│   │   │   └── Compliance.tsx       # Audit trail & governance
│   │   ├── components/workflow/
│   │   │   ├── ReasoningPanel.tsx   # Per-agent step viewer
│   │   │   └── CheckpointBanner.tsx # Governance status banner
│   │   └── mapcn/
│   │       └── heatmap.tsx          # MapLibre risk heatmap
│   ├── package.json
│   └── README.md
│
└── README.md
```

---

## Tech Stack

### Backend
| Layer | Technology |
|---|---|
| API framework | FastAPI (Python 3.11+) |
| Workflow engine | LangGraph |
| GNN | PyTorch Geometric — GraphSAGE + GAT |
| LLM providers | Google Gemini, Groq |
| Auth | Firebase (JWT) + custom RBAC |
| Database | SQLite (dev) / Google Cloud Firestore (prod) |
| Cache / queue | Upstash Redis |
| Scheduler | APScheduler (async cron) |
| HTTP client | httpx (async) |

### Frontend
| Layer | Technology |
|---|---|
| Framework | Vite + React 18 + TypeScript |
| UI components | shadcn/ui + Radix UI |
| Mapping | MapLibre GL JS |
| Data fetching | TanStack Query v5 |
| Charts | Recharts |
| Styling | Tailwind CSS v3 |

---

## Quick Start

### Backend
```bash
cd Backend
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # fill in API keys
uvicorn main:app --reload
```

### Frontend
```bash
cd Frontend
npm install
cp .env.example .env.local    # set VITE_API_URL=http://127.0.0.1:8000/api
npm run dev
```

---

## Key Concepts

### Governance Thresholds
Incidents are automatically escalated to the human gate when **any** of the following are true:
- Severity is `CRITICAL` or `HIGH`
- Total financial exposure ≥ $500,000
- A sole-source supplier is affected
- Operator has previously flagged similar incidents as false positives

### GNN Training Loop
The `SupplyChainGNN` model self-improves from operator feedback. Every `TRUE_POSITIVE` / `FALSE_POSITIVE` verdict stored in the governance feedback table is used as a training sample. Call `POST /ml/train` to retrain after accumulating ≥ 5 feedback records.

### Monte Carlo Simulation
The Intelligence page allows analysts to select any live signal and run a 300-iteration stochastic simulation that produces:
- P10 / P50 / P90 delivery delay distribution
- Expected exposure avoided by recommended action
- Worst-case loss estimate
- Data quality score and automation-readiness flag

---

## Environment Variables

| Variable | Description |
|---|---|
| `GOOGLE_API_KEY` | Gemini LLM |
| `GROQ_API_KEY` | Groq LLM (fallback) |
| `FIREBASE_*` | Firebase project credentials |
| `UPSTASH_REDIS_URL` | Upstash Redis endpoint |
| `NASA_FIRMS_MAP_KEY` | NASA active fire detections |
| `ACLED_API_KEY` | Armed conflict events |
| `NEWSAPI_API_KEY` | Supply chain news headlines |
| `FINNHUB_API_KEY` | Market quotes |
| `EIA_API_KEY` | US energy prices |
| `FRED_API_KEY` | Macro indicators |
| `LOCAL_DB_PATH` | SQLite path (default `./local_fallback.db`) |

---

## Governance & Compliance

All workflow transitions, agent decisions, and operator overrides are stored in the immutable audit log and are accessible via:
- `GET /audit` — structured event log
- `GET /audit/compliance` — aggregate KPIs
- `GET /audit/{id}/pdf` — per-incident PDF report

The `CheckpointBanner` component in the frontend surfaces the current governance status (PENDING / VERIFIED / BYPASSED) inline with every incident view.
