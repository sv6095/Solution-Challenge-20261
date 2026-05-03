import { useEffect, useState } from "react";
import { collection, onSnapshot, orderBy, query } from "firebase/firestore";

import { api } from "@/lib/api";
import { db, hasFirebaseConfig } from "@/lib/firebase";
import type { ReasoningStep } from "@/types/workflow";

export function useReasoningSteps(workflowId: string | null | undefined) {
  const [steps, setSteps] = useState<ReasoningStep[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!workflowId?.trim()) {
      setSteps([]);
      setLoading(false);
      return undefined;
    }
    const id = workflowId.trim();

    if (hasFirebaseConfig && db) {
      const q = query(collection(db, "workflow_events", id, "reasoning"), orderBy("timestamp_ms", "asc"));
      const unsub = onSnapshot(q, (snap) => {
        setSteps(snap.docs.map((d) => d.data() as ReasoningStep));
        setLoading(false);
      });
      return unsub;
    }

    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const res = await api.workflow.reasoning(id);
        if (!cancelled) setSteps(res.steps ?? []);
      } catch {
        if (!cancelled) setSteps([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [workflowId]);

  return { steps, loading };
}
