import { useEffect, useState } from "react";
import { doc, onSnapshot } from "firebase/firestore";

import { db, hasFirebaseConfig } from "@/lib/firebase";

export interface WorkflowEventState {
  stage?: string;
  confidence?: number;
  updated_at?: string;
}

export function useWorkflowEvent(workflowId: string) {
  const [data, setData] = useState<WorkflowEventState | null>(null);

  useEffect(() => {
    if (!workflowId || !hasFirebaseConfig || !db) return undefined;
    const ref = doc(db, "workflow_events", workflowId);
    const unsubscribe = onSnapshot(ref, (snapshot) => {
      setData((snapshot.data() as WorkflowEventState | undefined) ?? null);
    });
    return unsubscribe;
  }, [workflowId]);

  return data;
}
