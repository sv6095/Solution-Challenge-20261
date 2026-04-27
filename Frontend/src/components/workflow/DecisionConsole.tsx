import { useMemo, useState } from "react";

import { api } from "@/lib/api";

type RouteRow = Record<string, unknown>;

type Props = {
  workflowId: string;
  signal: Record<string, unknown> | null;
  affectedSuppliers: Record<string, unknown>[];
  recommendedMode: "sea" | "air" | "land" | "";
  selectedMode: "sea" | "air" | "land" | "";
  stageDecision: "reroute" | "backup_supplier";
  routeComparison: RouteRow[];
  onApproved?: (payload: { action: "reroute" | "backup_supplier" | "both"; mode?: "sea" | "air" | "land" | null }) => void;
};

export function DecisionConsole({
  workflowId,
  signal,
  affectedSuppliers,
  recommendedMode,
  selectedMode,
  stageDecision,
  routeComparison,
  onApproved,
}: Props) {
  const [starting, setStarting] = useState(false);
  const [approving, setApproving] = useState<"" | "reroute" | "backup_supplier" | "both">("");
  const [decisionState, setDecisionState] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");

  const effectiveMode = selectedMode || recommendedMode || null;
  const routeSummary = useMemo(() => {
    return routeComparison
      .map((row) => `${String(row.mode || "mode")}: ${String(row.cost_usd || row.cost || "n/a")}`)
      .slice(0, 3)
      .join(" | ");
  }, [routeComparison]);

  async function startGraphWorkflow() {
    setStarting(true);
    setError("");
    try {
  const userId = getUserId();
      const res = await api.workflow.start({
        workflow_id: workflowId,
        user_id: userId,
        selected_signal: signal ?? {},
        affected_suppliers: affectedSuppliers,
      });
      setDecisionState(res.state);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start workflow.");
    } finally {
      setStarting(false);
    }
  }

  async function approve(action: "reroute" | "backup_supplier" | "both") {
    setApproving(action);
    setError("");
    try {
      const res = await api.workflow.approve(workflowId, { action, mode: effectiveMode });
      setDecisionState(res.state);
      onApproved?.({ action, mode: effectiveMode });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to approve decision.");
    } finally {
      setApproving("");
    }
  }

  const waitingHuman = String((decisionState?.status as string) || "").toLowerCase() === "waiting_human" || Boolean(decisionState?.waiting_human);
  const gateConfidence = Number((decisionState?.human_gate_packet as { confidence?: number } | undefined)?.confidence ?? 0);
  const gateMode = String((decisionState?.human_gate_packet as { recommended_mode?: string } | undefined)?.recommended_mode ?? effectiveMode ?? "pending");

  return (
    <div className="rounded-2xl border border-border bg-[radial-gradient(circle_at_top_left,rgba(0,212,255,0.12),transparent_35%),linear-gradient(180deg,rgba(12,19,28,0.95),rgba(8,12,18,0.98))] p-6 space-y-5 shadow-[0_20px_60px_rgba(0,0,0,0.35)]">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.3em] text-sentinel/80">LangGraph Command Deck</p>
          <h3 className="font-headline font-bold text-xl mt-2">Decision Console</h3>
          <p className="text-body-md text-secondary mt-2 max-w-2xl">
            Start the workflow runtime, inspect the human-gate packet, and commit to reroute, backup supplier, or dual-action execution.
          </p>
        </div>
        <button
          type="button"
          onClick={startGraphWorkflow}
          disabled={starting}
          className="rounded-lg bg-sentinel px-4 py-2 text-background font-medium disabled:opacity-40"
        >
          {starting ? "Starting..." : "Start Graph Workflow"}
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-sm">
        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
          <div className="text-label-sm text-secondary uppercase tracking-widest">Preferred action</div>
          <div className="font-semibold mt-2">{stageDecision === "reroute" ? "Reroute corridor" : "Backup supplier"}</div>
        </div>
        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
          <div className="text-label-sm text-secondary uppercase tracking-widest">Selected mode</div>
          <div className="font-semibold mt-2">{effectiveMode || "Pending"}</div>
        </div>
        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
          <div className="text-label-sm text-secondary uppercase tracking-widest">Human gate mode</div>
          <div className="font-semibold mt-2">{gateMode}</div>
        </div>
        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
          <div className="text-label-sm text-secondary uppercase tracking-widest">Gate confidence</div>
          <div className="font-semibold mt-2">{gateConfidence > 0 ? `${(gateConfidence * 100).toFixed(1)}%` : "Pending"}</div>
        </div>
      </div>

      <div className="rounded-xl border border-amber-500/30 bg-amber-500/[0.06] p-4">
        <div className="text-label-sm uppercase tracking-widest text-amber-300">Execution summary</div>
        <div className="mt-2 text-sm text-secondary">
          {routeSummary || "Compute routes first, then start the graph to generate a decision packet."}
        </div>
      </div>

      {decisionState ? (
        <div className="grid grid-cols-1 lg:grid-cols-[1.2fr_0.8fr] gap-4">
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-sm">
            <div className="text-label-sm text-secondary uppercase tracking-widest mb-2">Graph state</div>
            <div className="font-medium">Status: {String(decisionState.status ?? decisionState.current_stage ?? "unknown")}</div>
            {decisionState.human_gate_packet ? (
              <pre className="mt-3 overflow-x-auto rounded-lg bg-black/20 p-3 text-xs text-secondary whitespace-pre-wrap">
                {JSON.stringify(decisionState.human_gate_packet, null, 2)}
              </pre>
            ) : null}
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-sm">
            <div className="text-label-sm text-secondary uppercase tracking-widest mb-2">Decision brief</div>
            {decisionState.decision_brief ? (
              <pre className="overflow-x-auto rounded-lg bg-black/20 p-3 text-xs text-secondary whitespace-pre-wrap">
                {JSON.stringify(decisionState.decision_brief, null, 2)}
              </pre>
            ) : (
              <div className="text-secondary">The supervisor brief appears after route analysis completes.</div>
            )}
          </div>
        </div>
      ) : null}

      {waitingHuman || decisionState ? (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <button
            type="button"
            onClick={() => approve("reroute")}
            disabled={!!approving || !effectiveMode}
            className="rounded-xl border border-cyan-400/30 bg-cyan-400/[0.06] px-4 py-3 hover:bg-cyan-400/[0.12] disabled:opacity-40"
          >
            {approving === "reroute" ? "Approving..." : "Approve Reroute"}
          </button>
          <button
            type="button"
            onClick={() => approve("backup_supplier")}
            disabled={!!approving}
            className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 hover:bg-white/[0.08] disabled:opacity-40"
          >
            {approving === "backup_supplier" ? "Approving..." : "Approve Backup Supplier"}
          </button>
          <button
            type="button"
            onClick={() => approve("both")}
            disabled={!!approving || !effectiveMode}
            className="rounded-xl border border-emerald-400/30 bg-emerald-400/[0.06] px-4 py-3 hover:bg-emerald-400/[0.12] disabled:opacity-40"
          >
            {approving === "both" ? "Approving..." : "Approve Both"}
          </button>
        </div>
      ) : null}

      {error ? <div className="text-sm text-red-500">{error}</div> : null}
    </div>
  );
}
import { getUserId } from "@/lib/api";
