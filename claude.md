# SupplyShield - CLAUDE.md
# Version: 4.1

This file is the working guide for this repository.

## Repo Reality

There are three directories at the root:

```text
Praecantator/
|- Backend/      -> primary Python application
|- Frontend/     -> primary React application
|- Risk Wise/    -> reference-only material
```

Rules:

- Build only in `Backend/` and `Frontend/`.
- Read `Risk Wise/` for ideas, flow, schemas, and UI patterns only.
- Do not modify files inside `Risk Wise/`.
- Do not import code from `Risk Wise/` directly into the app.
- Do not add Azure SDKs, `pyodbc`, or Semantic Kernel to the active codebases.
- Do not mention internal reference provenance in app code or user-facing copy.

## Product Shape

SupplyShield is a supply-chain disruption workflow system with a staged flow:

1. `DETECT`
2. `ASSESS`
3. `DECIDE`
4. `ACT`
5. `AUDIT`

The live app already contains the core pieces for that flow:

- Backend agents under `Backend/agents/`
- Frontend workflow UI under `Frontend/src/`
- Real-time workflow state via Firestore when configured
- Local fallback storage and API responses when cloud services are unavailable

## Current Repo Map

### Backend

Important files and folders:

```text
Backend/
|- main.py
|- requirements.txt
|- agents/
|  |- assessment_agent.py
|  |- citation_tracker.py
|  |- orchestrator.py
|  |- reasoning_logger.py
|  |- rfq_agent.py
|  |- risk_calculator.py
|  |- routing_agent.py
|  |- signal_agent.py
|- currency/
|- Dataset/
|- ml/
|- pdf/
|- routing/
|- scheduler/
|- services/
```

### Frontend

Important files and folders:

```text
Frontend/
|- package.json
|- src/
|  |- components/
|  |  |- workflow/ReasoningPanel.tsx
|  |- hooks/
|  |  |- use-reasoning-steps.ts
|  |  |- use-workflow-event.ts
|  |- lib/
|  |  |- api.ts
|  |  |- firebase.ts
|  |  |- risk-heatmap.ts
|  |- pages/dashboard/
|  |- types/workflow.ts
```

## Non-Negotiable Engineering Rules

- Always check existing code before adding new files or abstractions.
- Extend existing types in `Frontend/src/types/` instead of duplicating them.
- Keep the provider/fallback pattern in service modules, not inside agent business logic.
- Keep real-time workflow state push-based where Firebase is configured.
- Keep local fallbacks working. Environment changes should switch providers without requiring large code edits.
- Never hardcode secrets.
- Do not rename or reorganize major folders without a strong repo-wide reason.

## Backend Source of Truth

The backend is a FastAPI app centered on `Backend/main.py`.

Key behaviors already present in the repo:

- `.env` is loaded first, then `.env.development` or `.env.local` for local work, and `.env.production` when `ENVIRONMENT=production`.
- `Backend/services/llm_provider.py` switches between `gemini` and `groq`.
- `Backend/services/db_provider.py` routes persistence through Firestore helpers or local SQLite-backed storage behavior.
- `Backend/services/cache_provider.py` switches between Upstash Redis and in-memory cache.
- `Backend/agents/reasoning_logger.py` writes reasoning steps through the persistence layer.
- `Backend/agents/orchestrator.py` contains the workflow stage map and human-gate rules.

Backend design rules:

- Agent modules should focus on business decisions, not provider branching.
- Provider selection belongs in `Backend/services/`.
- Every meaningful workflow decision should emit a reasoning step.
- New persistence logic should route through the existing storage facade instead of bypassing it.
- Prefer adding to current modules before inventing parallel replacements.

## Frontend Source of Truth

The frontend is a Vite + React + TypeScript app.

Current stack in use:

- React 18
- React Router
- TanStack Query
- Firebase client SDK
- Tailwind
- Radix UI components
- MapLibre and map-related visualization helpers

Frontend design rules:

- Shared workflow types belong in `Frontend/src/types/workflow.ts`.
- Real-time workflow updates should use the Firebase snapshot hooks already in the repo when config is available.
- REST calls remain appropriate for user-triggered actions and fallback data loading.
- Reuse existing dashboard structure and UI primitives before creating new component systems.

## Workflow Schema

These shapes already exist or are expected by the current app:

```ts
export interface WorkflowState {
  workflow_id: string
  stage: "DETECT" | "ASSESS" | "DECIDE" | "ACT" | "AUDIT"
  status: "running" | "waiting_approval" | "complete" | "error"
  created_at: string
  updated_at: string
}

export interface ReasoningStep {
  agent: string
  stage: string
  detail: string
  status: "success" | "error" | "fallback"
  timestamp: string
  timestamp_ms: number
  output?: Record<string, unknown>
}

export interface Signal {
  signal_id: string
  title: string
  event_type: string
  severity: number
  location: string
  lat: number
  lng: number
  source: string
  source_url: string
  source_type: "government" | "news" | "geopolitical" | "regional"
  verified: boolean
  corroborated_by: string[]
  corroboration_count: number
  detected_at: string
  relevance_score: number
}
```

If new workflow-facing data is introduced, update the shared type file first.

## Reasoning Panel Contract

The reasoning panel is part of the core product behavior.

Backend expectations:

- Log agent name
- Log stage name
- Log a plain-English detail message
- Log status as `success`, `error`, or `fallback`
- Include structured output only when it adds debugging or UI value

Frontend expectations:

- Display steps in chronological order
- Distinguish fallback runs clearly
- Keep the panel readable during live workflow execution

## Environment Model

Expected local-first provider defaults:

```bash
LLM_PROVIDER=groq
DB_PROVIDER=sqlite
CACHE_PROVIDER=memory
AUTH_PROVIDER=local
```

Expected production-oriented provider values:

```bash
LLM_PROVIDER=gemini
DB_PROVIDER=firestore
CACHE_PROVIDER=redis
AUTH_PROVIDER=firebase
```

Important note:

- Keep fallback support intact even when production integrations are enabled.

## Package and Dependency Guidance

Backend:

- Keep dependencies aligned with actual imports in `Backend/`.
- Avoid introducing cloud/vendor packages unless the feature is actively used.
- Do not add Azure-specific packages.

Frontend:

- Use the existing Vite/React toolchain.
- Do not introduce Next.js-specific patterns or packages for app behavior.
- Prefer existing UI packages already in `Frontend/package.json`.

## Safe Working Sequence

When implementing anything substantial:

1. Read the existing backend or frontend code first.
2. Check for an existing type, hook, service, or utility.
3. Inspect the reference directory only if needed for behavior or structure ideas.
4. Implement in `Backend/` or `Frontend/`.
5. Preserve provider fallbacks.
6. Update shared types if data shape changes.
7. Wire reasoning logs if the workflow behavior changed.
8. Verify the affected path with the lightest useful test or run.

## Hard Rules

- Do not edit `Risk Wise/`.
- Do not create duplicate workflow schemas in multiple frontend files.
- Do not branch provider logic throughout the agents.
- Do not remove local fallback behavior to make cloud mode work.
- Do not poll aggressively for state where the repo already uses live subscriptions.
