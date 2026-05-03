import { useState } from "react";

import { api } from "@/lib/api";
import type { AgentChatResult } from "@/types/workflow";

export function useAgentChat() {
  const [result, setResult] = useState<AgentChatResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>("");

  async function runAgentChat(payload: {
    message: string;
    workflow_id?: string | null;
    session_id?: string | null;
    context?: Record<string, unknown>;
  }) {
    setLoading(true);
    setError("");
    try {
      const res = await api.agents.chat(payload);
      setResult(res as AgentChatResult);
      return res as AgentChatResult;
    } catch (err) {
      const message = err instanceof Error ? err.message : "Agent chat failed.";
      setError(message);
      throw err;
    } finally {
      setLoading(false);
    }
  }

  return { result, loading, error, runAgentChat };
}
