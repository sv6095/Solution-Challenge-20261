import { useEffect, useState } from "react";
import { doc, onSnapshot } from "firebase/firestore";

import { api } from "@/lib/api";
import { db, hasFirebaseConfig } from "@/lib/firebase";

export interface WorkflowEventState {
  stage?: string;
  confidence?: number;
  updated_at?: string;
}

export function useWorkflowEvent(workflowId: string) {
  const [data, setData] = useState<WorkflowEventState | null>(null);

  useEffect(() => {
    if (!workflowId) return undefined;

    if (hasFirebaseConfig && db) {
      const ref = doc(db, "workflow_events", workflowId);
      const unsubscribe = onSnapshot(ref, (snapshot) => {
        setData((snapshot.data() as WorkflowEventState | undefined) ?? null);
      });
      return unsubscribe;
    }

    let cancelled = false;
    const run = async () => {
      try {
        const res = await api.workflow.state(workflowId);
        if (!cancelled) {
          const state = (res.state ?? {}) as WorkflowEventState & { current_stage?: string; confidence?: number };
          setData({
            stage: state.current_stage ?? res.status,
            confidence: state.confidence,
            updated_at: (state as { updated_at?: string }).updated_at,
          });
        }
      } catch {
        if (!cancelled) setData(null);
      }
    };
    run();
    const timer = window.setInterval(run, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [workflowId]);

  return data;
}
