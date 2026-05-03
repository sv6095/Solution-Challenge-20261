import { useCallback, useMemo, useState } from "react";

import { api } from "@/lib/api";

export type SpineStage = "DETECT" | "ASSESS" | "DECIDE" | "ACT" | "AUDIT";

const STAGE_ORDER: SpineStage[] = ["DETECT", "ASSESS", "DECIDE", "ACT", "AUDIT"];

export interface WorkflowSpineSignal {
  id?: string;
  title?: string;
  description?: string;
  severity?: string;
  lat?: number;
  lng?: number;
  region?: string;
  timestamp?: string;
  [key: string]: unknown;
}

function getOrCreateWorkflowId() {
  const existing = sessionStorage.getItem("active_workflow_id");
  if (existing) return existing;
  const fresh = `wf_${Date.now()}_${Math.random().toString(16).slice(2)}`;
  sessionStorage.setItem("active_workflow_id", fresh);
  return fresh;
}

export function useWorkflowSpine() {
  const [workflowId, setWorkflowId] = useState<string>(() => getOrCreateWorkflowId());
  const [stage, setStage] = useState<SpineStage>(() => {
    const stored = (sessionStorage.getItem("workflow_spine_stage") || "").toUpperCase();
    return (STAGE_ORDER.includes(stored as SpineStage) ? stored : "DETECT") as SpineStage;
  });

  const selectedSignal = useMemo<WorkflowSpineSignal | null>(() => {
    const raw = sessionStorage.getItem("preloaded_workflow_event");
    if (!raw) return null;
    try {
      const parsed = JSON.parse(raw) as WorkflowSpineSignal;
      return parsed;
    } catch {
      return null;
    }
  }, [workflowId, stage]);

  const setSpineStage = useCallback((next: SpineStage) => {
    sessionStorage.setItem("workflow_spine_stage", next);
    setStage(next);
  }, []);

  const ensureWorkflow = useCallback(() => {
    const id = getOrCreateWorkflowId();
    if (id !== workflowId) setWorkflowId(id);
    return id;
  }, [workflowId]);

  const startFromSignal = useCallback(async (signal: WorkflowSpineSignal) => {
    const wf = `wf_${Date.now()}_${Math.random().toString(16).slice(2)}`;
    sessionStorage.setItem("active_workflow_id", wf);
    sessionStorage.setItem("preloaded_workflow_event", JSON.stringify(signal));
    sessionStorage.setItem("workflow_spine_stage", "DETECT");
    setWorkflowId(wf);
    setStage("DETECT");

    await api.workflow.start({
      workflow_id: wf,
    user_id: getUserId(),
      selected_signal: signal as Record<string, unknown>,
      affected_suppliers: [],
    });

    return wf;
  }, []);

  return {
    workflowId,
    stage,
    selectedSignal,
    ensureWorkflow,
    setSpineStage,
    startFromSignal,
  };
}
import { getUserId } from "@/lib/api";
