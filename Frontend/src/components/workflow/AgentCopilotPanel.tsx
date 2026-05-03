import { useState } from "react";

import { useAgentChat } from "@/hooks/use-agent-chat";
import { AgentSystemGrid } from "@/components/workflow/AgentSystemGrid";

type Props = {
  workflowId?: string | null;
  context?: Record<string, unknown>;
};

export function AgentCopilotPanel({ workflowId, context }: Props) {
  const [message, setMessage] = useState("");
  const { result, loading, error, runAgentChat } = useAgentChat();

  async function submitPrompt(raw?: string) {
    const trimmed = (raw ?? message).trim();
    if (!trimmed) return;
    await runAgentChat({
      message: trimmed,
      workflow_id: workflowId,
      context,
    });
    if (!raw) setMessage("");
  }

  return (
    <div className="rounded-2xl border border-border bg-[radial-gradient(circle_at_top_left,rgba(0,212,255,0.12),transparent_32%),linear-gradient(180deg,rgba(11,17,24,0.96),rgba(9,13,19,0.98))] p-5 mt-4 shadow-[0_18px_54px_rgba(0,0,0,0.28)]">
      <div className="flex items-center justify-between gap-3 mb-4">
        <div>
          <div className="text-label-sm text-secondary uppercase tracking-widest">Agent Copilot</div>
          <div className="text-body-md text-secondary">Run the full specialist team, inspect the supervisor brief, and query any agent directly.</div>
        </div>
      </div>

      <AgentSystemGrid result={result} loading={loading} onQuickRun={submitPrompt} />

      <div className="mt-4 flex gap-2">
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Example: Coordinate all agents and give me the best disruption response plan."
          className="min-h-[96px] flex-1 rounded-xl border border-border bg-background/60 px-3 py-2 text-sm"
        />
        <button
          type="button"
          onClick={() => submitPrompt()}
          disabled={loading || !message.trim()}
          className="rounded-xl bg-sentinel px-4 py-2 text-sm font-medium text-background disabled:opacity-50"
        >
          {loading ? "Running..." : "Run Mission"}
        </button>
      </div>

      {error ? <div className="mt-3 text-sm text-red-500">{error}</div> : null}

      {result ? (
        <div className="mt-4 space-y-3">
          <div className="text-label-sm text-secondary uppercase tracking-widest">
            Sequence: <span className="text-sentinel">{result.sequence.join(" -> ")}</span>
          </div>
          {result.supervisor ? (
            <div className="rounded-xl border border-border bg-background/60 p-3 text-xs">
              <div className="text-secondary uppercase tracking-widest mb-2">Supervisor Brief</div>
              <div className="mb-1">
                Path: <span className="text-sentinel">{String(result.supervisor.recommended_path ?? "unknown")}</span>
              </div>
              <div className="mb-1">
                Confidence: <span className="text-sentinel">{String(result.supervisor.global_confidence ?? "")}</span>
              </div>
              <div>{String(result.supervisor.decision_brief ?? "")}</div>
            </div>
          ) : null}
          <pre className="overflow-auto rounded-xl border border-border bg-background/60 p-3 text-xs whitespace-pre-wrap">
            {result.text}
          </pre>
        </div>
      ) : null}
    </div>
  );
}
