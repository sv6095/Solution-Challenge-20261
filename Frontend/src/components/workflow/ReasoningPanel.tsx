import { useEffect, useState, useRef } from "react";
import { api } from "@/lib/api";
import type { ReasoningStep } from "@/types/workflow";

/* ── Agent colour palette (Light Theme Optimized) ─────────────────────────── */
const AGENT_COLORS: Record<string, { bg: string; text: string; ring: string }> = {
  signal_agent:         { bg: "#eff6ff", text: "#2563eb", ring: "#93c5fd" },
  assessment_agent:     { bg: "#fffbeb", text: "#d97706", ring: "#fcd34d" },
  routing_agent:        { bg: "#ecfdf5", text: "#059669", ring: "#6ee7b7" },
  rfq_agent:            { bg: "#f5f3ff", text: "#7c3aed", ring: "#c4b5fd" },
  audit_agent:          { bg: "#f0f9ff", text: "#0284c7", ring: "#7dd3fc" },
  orchestrator:         { bg: "#f8fafc", text: "#475569", ring: "#cbd5e1" },
  logistics_risk_agent: { bg: "#eef2ff", text: "#4f46e5", ring: "#a5b4fc" },
  political_risk_agent: { bg: "#fff1f2", text: "#e11d48", ring: "#fda4af" },
  tariff_risk_agent:    { bg: "#fff7ed", text: "#ea580c", ring: "#fdba74" },
  supervisor:           { bg: "#f8fafc", text: "#475569", ring: "#cbd5e1" },
  decision:             { bg: "#ecfdf5", text: "#059669", ring: "#6ee7b7" },
  graph:                { bg: "#eff6ff", text: "#2563eb", ring: "#93c5fd" },
  notification:         { bg: "#f0f9ff", text: "#0284c7", ring: "#7dd3fc" },
};

const DEFAULT_COLOR = { bg: "#f1f5f9", text: "#334155", ring: "#cbd5e1" };

/* ── Stage label prettifier ───────────────────────────────────────────────── */
function prettyStage(stage: string): string {
  return stage.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/* ── Agent label ──────────────────────────────────────────────────────────── */
function agentLabel(agent: string): string {
  return agent
    .replace(/_agent$/i, "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/* ── Tiny JSON tree ───────────────────────────────────────────────────────── */
function JsonChip({ data }: { data: Record<string, unknown> }) {
  const [open, setOpen] = useState(false);
  const entries = Object.entries(data).filter(([, v]) => v !== null && v !== undefined);
  if (entries.length === 0) return null;
  return (
    <div className="mt-2.5">
      <button
        onClick={() => setOpen((o) => !o)}
        className="text-[10px] font-mono font-bold uppercase tracking-widest text-muted-foreground bg-transparent border border-border rounded px-2 py-0.5 cursor-pointer hover:bg-surface transition-colors"
      >
        {open ? "▲ hide" : "▼ output"} ({entries.length} field{entries.length !== 1 ? "s" : ""})
      </button>
      {open && (
        <div className="mt-1.5 bg-surface-low border border-border rounded-md p-2.5 font-mono text-[11px] text-muted-foreground leading-relaxed">
          {entries.map(([k, v]) => (
            <div key={k}>
              <span className="text-accent font-bold">{k}</span>
              <span className="text-muted-foreground/50">{" → "}</span>
              <span className="text-foreground">
                {typeof v === "object" ? JSON.stringify(v) : String(v)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Types ────────────────────────────────────────────────────────────────── */
type EnrichedStep = ReasoningStep & { narrative?: string };

type Props = {
  workflowId: string | null | undefined;
};

/* ── Component ───────────────────────────────────────────────────────────── */
export function ReasoningPanel({ workflowId }: Props) {
  const [open, setOpen] = useState(false);
  const [steps, setSteps] = useState<EnrichedStep[]>([]);
  const [loading, setLoading] = useState(false);
  const [rendering, setRendering] = useState(false);
  const fetched = useRef(false);

  /* Fetch rendered steps lazily when user opens the panel */
  useEffect(() => {
    if (!open || !workflowId?.trim() || fetched.current) return;
    fetched.current = true;

    (async () => {
      setLoading(true);
      try {
        /* Attempt Groq-rendered endpoint first */
        setRendering(true);
        const res = await api.workflow.reasoningRender(workflowId.trim());
        setSteps(res.steps ?? []);
      } catch {
        /* Graceful fallback to raw steps */
        try {
          const raw = await api.workflow.reasoning(workflowId.trim());
          setSteps(raw.steps ?? []);
        } catch {
          setSteps([]);
        }
      } finally {
        setLoading(false);
        setRendering(false);
      }
    })();
  }, [open, workflowId]);

  if (!workflowId?.trim()) return null;

  return (
    <div className="mt-5 rounded-xl border border-border bg-card overflow-hidden font-body">
      {/* ── Header toggle ── */}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-5 py-4 bg-transparent border-none cursor-pointer gap-3 hover:bg-surface-low transition-colors"
      >
        <span className="font-headline text-lg text-foreground tracking-wide drop-shadow-sm">
          Agent Reasoning
        </span>
        <div className="flex items-center gap-3">
          {steps.length > 0 && (
            <span className="text-[11px] font-mono font-bold text-muted-foreground uppercase tracking-widest">
              {steps.length} step{steps.length !== 1 ? "s" : ""}
            </span>
          )}
          <span className="text-xs text-muted-foreground font-bold">
            {open ? "▲" : "▼"}
          </span>
        </div>
      </button>

      {/* ── Step list ── */}
      {open && (
        <div className="border-t border-border max-h-[560px] overflow-y-auto custom-scrollbar">
          {/* Loading / rendering state */}
          {loading && (
            <div className="px-5 py-7 text-center text-muted-foreground text-[13px] font-mono">
              {rendering
                ? "Generating intelligence narrative…"
                : "Loading reasoning steps…"}
            </div>
          )}

          {!loading &&
            steps.map((step, i) => {
              const color = AGENT_COLORS[step.agent] ?? DEFAULT_COLOR;
              const narrative = step.narrative || step.detail || "";
              const output =
                step.output && typeof step.output === "object" && Object.keys(step.output).length > 0
                  ? (step.output as Record<string, unknown>)
                  : null;

              return (
                <div
                  key={`${step.timestamp_ms ?? i}-${i}`}
                  className="flex gap-4 px-5 py-4.5 border-b border-border hover:bg-surface-low transition-colors"
                >
                  {/* Left column: agent badge + time */}
                  <div className="flex flex-col items-center gap-1.5 min-w-[80px]">
                    <span
                      style={{
                        color: color.text,
                        backgroundColor: color.bg,
                        borderColor: `${color.ring}30`,
                        boxShadow: `0 0 8px ${color.ring}15`,
                      }}
                      className="text-[9px] font-mono font-extrabold uppercase tracking-widest border rounded px-1.5 py-0.5 whitespace-nowrap"
                    >
                      {agentLabel(step.agent)}
                    </span>
                    {step.timestamp && (
                      <span className="text-[9px] font-mono text-muted-foreground mt-1">
                        {new Date(step.timestamp).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                          second: "2-digit",
                        })}
                      </span>
                    )}
                  </div>

                  {/* Right column: stage heading + narrative */}
                  <div className="flex-1 min-w-0">
                    {/* Stage heading — gothic */}
                    <div 
                      className="font-headline text-sm mb-1.5 tracking-wide"
                      style={{ color: color.text }}
                    >
                      {prettyStage(step.stage)}
                    </div>

                    {/* Narrative body — Inter */}
                    <p className="font-body text-[13px] text-foreground leading-relaxed m-0">
                      {narrative}
                    </p>

                    {/* Structured output (collapsible) */}
                    {output && <JsonChip data={output} />}
                  </div>
                </div>
              );
            })}

          {!loading && steps.length === 0 && (
            <div className="px-5 py-8 text-center text-muted-foreground text-xs font-mono">
              No reasoning steps recorded for this workflow.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
