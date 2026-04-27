# Frontend - CLAUDE.md

This frontend contains the active React + Vite + TypeScript implementation for Praecantator.

## What lives here

- Dashboard pages under `src/pages/dashboard/`
- Shared workflow UI under `src/components/`
- Live workflow hooks under `src/hooks/`
- API and Firebase helpers under `src/lib/`
- Shared workflow types under `src/types/workflow.ts`

## Rules

- Extend existing shared types before creating duplicates.
- Prefer existing hooks and UI primitives before adding new abstractions.
- Keep workflow state push-based when Firebase is configured.
- Keep fallback behavior for non-Firebase local runs.

## Current workflow UI primitives

- `src/components/workflow/ReasoningPanel.tsx`
- `src/components/workflow/AgentCopilotPanel.tsx`
- `src/hooks/use-agent-chat.ts`
- `src/hooks/use-reasoning-steps.ts`
- `src/hooks/use-workflow-event.ts`

## Backend integration

The frontend should treat the backend as the source of truth for:

- workflow analysis
- route decisions
- RFQ actions
- reasoning history
- consolidated reports
- multi-agent conversational analysis through `/api/agents/chat`
- graph workflow start and approval through `/api/workflow/start` and `/api/workflow/{workflow_id}/approve`
