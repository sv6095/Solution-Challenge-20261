# Backend - CLAUDE.md

This backend contains the active Python implementation for Praecantator.

## What lives here

- FastAPI app entry in `main.py`
- Workflow agents in `agents/`
- Conversational risk-agent orchestration in `managers/chatbot_manager.py`
- LangGraph-style workflow scaffolding in `workflows/`
- MCP tool exposure in `mcp_server.py`
- Provider switching in `services/`
- Routing, currency, ML, PDF, and scheduler support modules

## Agent system

The backend now contains two layers of agents:

1. Core workflow agents already used by the workflow endpoints:
   - `signal_agent`
   - `assessment_agent`
   - `routing_agent`
   - `rfq_agent`
   - `reasoning_logger`
   - `citation_tracker`
   - `risk_calculator`

2. Specialized conversational analysis agents:
   - `scheduler_agent`
   - `political_risk_agent`
   - `tariff_risk_agent`
   - `logistics_risk_agent`
   - `reporting_agent`
   - `assistant_agent`

Supporting orchestration modules:

- `agents/agent_definitions.py`
- `agents/agent_strategies.py`
- `managers/chatbot_manager.py`
- `workflows/state.py`
- `workflows/checkpoint.py`
- `workflows/langgraph_workflow.py`
- `ml/rl_agent.py`
- `ml/train_rl.py`
- `services/open_meteo.py`
- `services/fcm.py`

## Rules

- Build here, not in the reference directory.
- Do not import Azure SDKs, `pyodbc`, or Semantic Kernel.
- Keep provider switching in `services/`, not in each agent.
- Keep reasoning logs for meaningful decisions and fallbacks.
- Preserve local fallback behavior.

## API surface

Important endpoints include:

- workflow assessment/routing/RFQ endpoints
- workflow reasoning/report endpoints
- `POST /api/agents/chat` for multi-agent conversational orchestration
- `POST /api/workflow/start` for graph-driven workflow execution
- `POST /api/workflow/{workflow_id}/approve` for human-in-the-loop resume

## Data contract expectations

- Prefer shared, structured dict outputs between agents.
- Scheduler output is the base context for political, tariff, and logistics analysis.
- Reporting agent consolidates all available specialized outputs into one executive report.
