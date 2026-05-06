/**
 * GovernanceFeedbackWidget
 * ========================
 * Renders inline on a resolved/dismissed incident so operators can submit
 * a verdict (TRUE_POSITIVE | FALSE_POSITIVE | FALSE_NEGATIVE | UNCERTAIN).
 * Results feed the governance metrics dashboard.
 *
 * Usage:
 *   <GovernanceFeedbackWidget incidentId={detail.id} status={detail.status} />
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ThumbsUp, ThumbsDown, HelpCircle, AlertCircle, CheckCircle2, Loader2 } from "lucide-react";
import { motion, AnimatePresence } from "motion/react";

const BASE = (import.meta.env.VITE_API_URL ?? "/api").replace(/\/+$/, "");

import { getAccessToken, getUserId } from "@/lib/api";

function authHeaders(): HeadersInit {
  const token  = getAccessToken();
  const userId = getUserId();
  return {
    "Content-Type": "application/json",
    "X-User-Id": userId,
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

type Verdict = "TRUE_POSITIVE" | "FALSE_POSITIVE" | "FALSE_NEGATIVE" | "UNCERTAIN";

const VERDICTS: {
  key: Verdict;
  label: string;
  short: string;
  color: string;
  bg: string;
  icon: React.ElementType;
}[] = [
  {
    key: "TRUE_POSITIVE",
    label: "True Positive",
    short: "TP",
    color: "text-emerald-400",
    bg: "bg-emerald-500/10 border-emerald-500/30 hover:bg-emerald-500/20",
    icon: ThumbsUp,
  },
  {
    key: "FALSE_POSITIVE",
    label: "False Positive",
    short: "FP",
    color: "text-sentinel",
    bg: "bg-sentinel/10 border-sentinel/30 hover:bg-sentinel/20",
    icon: ThumbsDown,
  },
  {
    key: "FALSE_NEGATIVE",
    label: "False Negative",
    short: "FN",
    color: "text-orange-400",
    bg: "bg-orange-500/10 border-orange-500/30 hover:bg-orange-500/20",
    icon: AlertCircle,
  },
  {
    key: "UNCERTAIN",
    label: "Uncertain",
    short: "?",
    color: "text-gray-400",
    bg: "bg-surface-high border-border hover:bg-surface-highest",
    icon: HelpCircle,
  },
];

const AFFECTED_STAGES = [
  { value: "", label: "All stages" },
  { value: "signal_detection", label: "Signal Detection" },
  { value: "gnn_propagation", label: "Praecantator Propagation" },
  { value: "financial_assessment", label: "Financial Assessment" },
  { value: "route_generation", label: "Route Generation" },
  { value: "rfq_generation", label: "RFQ Generation" },
];

interface Props {
  incidentId: string;
  status: string;
}

export function GovernanceFeedbackWidget({ incidentId, status }: Props) {
  const qc = useQueryClient();
  const [expanded, setExpanded]   = useState(false);
  const [selected, setSelected]   = useState<Verdict | null>(null);
  const [notes, setNotes]         = useState("");
  const [stage, setStage]         = useState("");
  const [submitted, setSubmitted] = useState(false);

  // Check if feedback already exists
  const { data: existingFb } = useQuery({
    queryKey: ["governance-feedback-inc", incidentId],
    queryFn: async () => {
      const r = await fetch(`${BASE}/governance/feedback/${incidentId}`, { headers: authHeaders() });
      if (!r.ok) return null;
      return r.json();
    },
    enabled: !!incidentId,
  });

  const mutation = useMutation({
    mutationFn: async (vars: { verdict: Verdict; notes: string; stage: string }) => {
      const r = await fetch(`${BASE}/governance/feedback`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({
          incident_id: incidentId,
          verdict: vars.verdict,
          notes: vars.notes,
          affected_stage: vars.stage,
        }),
      });
      if (!r.ok) throw new Error(await r.text());
      return r.json();
    },
    onSuccess: () => {
      setSubmitted(true);
      setExpanded(false);
      qc.invalidateQueries({ queryKey: ["governance-feedback-inc", incidentId] });
      qc.invalidateQueries({ queryKey: ["governance-summary"] });
    },
  });

  // Only show for resolved/dismissed incidents
  if (!["RESOLVED", "APPROVED", "DISMISSED"].includes(status)) return null;

  const hasFeedback = existingFb?.feedback && existingFb.feedback.length > 0;
  const existingVerdict = hasFeedback ? existingFb.feedback[0].verdict : null;
  const existingVerdictDef = VERDICTS.find((v) => v.key === existingVerdict);

  return (
    <div className="border border-border/50 rounded mt-1">
      {/* Header: toggle row */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-surface-high/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          {hasFeedback || submitted ? (
            <CheckCircle2 size={12} className="text-emerald-400" />
          ) : (
            <HelpCircle size={12} className="text-gray-500" />
          )}
          <span className="text-[10px] font-mono font-bold uppercase tracking-widest text-gray-400">
            Operator Feedback
          </span>
          {(hasFeedback || submitted) && existingVerdictDef && (
            <span className={`text-[10px] font-mono font-bold ml-2 px-2 py-0.5 rounded border uppercase ${existingVerdictDef.bg} ${existingVerdictDef.color}`}>
              {existingVerdictDef.short} · {existingVerdictDef.label}
            </span>
          )}
          {!hasFeedback && !submitted && (
            <span className="text-[10px] font-mono text-gray-500 ml-1">· pending review</span>
          )}
        </div>
        <span className="text-[10px] font-mono text-gray-500">{expanded ? "▲" : "▼"}</span>
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="overflow-hidden border-t border-border/40"
          >
            <div className="p-4 space-y-3 bg-surface-low">
              {(hasFeedback || submitted) ? (
                <div className="text-center py-2">
                  <CheckCircle2 size={20} className="text-emerald-400 mx-auto mb-1.5" />
                  <p className="text-xs font-mono font-semibold text-emerald-400">
                    Feedback submitted
                  </p>
                  {existingFb?.feedback?.[0]?.notes && (
                    <p className="text-xs text-gray-400 mt-1 italic">
                      "{existingFb.feedback[0].notes}"
                    </p>
                  )}
                </div>
              ) : (
                <>
                  {/* Verdict buttons */}
                  <p className="text-[10px] font-mono text-gray-400 uppercase tracking-widest">
                    Was this incident correctly identified?
                  </p>
                  <div className="grid grid-cols-2 gap-2">
                    {VERDICTS.map((v) => {
                      const Icon = v.icon;
                      const isSel = selected === v.key;
                      return (
                        <button
                          key={v.key}
                          onClick={() => setSelected(v.key)}
                          className={`flex items-center gap-2 px-3 py-2 border rounded text-xs font-mono font-bold uppercase tracking-wider transition-all ${v.bg} ${v.color}
                            ${isSel ? "ring-1 ring-current" : ""}`}
                        >
                          <Icon size={12} />
                          {v.label}
                        </button>
                      );
                    })}
                  </div>

                  {/* Affected stage (only for FP/FN) */}
                  {selected && selected !== "TRUE_POSITIVE" && (
                    <div>
                      <label className="text-[10px] font-mono text-gray-400 uppercase tracking-widest block mb-1">
                        Which stage caused this?
                      </label>
                      <select
                        value={stage}
                        onChange={(e) => setStage(e.target.value)}
                        className="w-full text-xs font-mono bg-surface border border-border/50 text-gray-200 px-3 py-1.5 rounded focus:outline-none focus:border-sentinel/50"
                      >
                        {AFFECTED_STAGES.map((s) => (
                          <option key={s.value} value={s.value}>{s.label}</option>
                        ))}
                      </select>
                    </div>
                  )}

                  {/* Notes */}
                  {selected && (
                    <div>
                      <label className="text-[10px] font-mono text-gray-400 uppercase tracking-widest block mb-1">
                        Notes (optional)
                      </label>
                      <textarea
                        value={notes}
                        onChange={(e) => setNotes(e.target.value)}
                        placeholder="What should have happened differently?"
                        rows={2}
                        className="w-full text-xs font-mono bg-surface border border-border/50 text-gray-200 px-3 py-2 rounded resize-none focus:outline-none focus:border-sentinel/50 placeholder:text-gray-600"
                      />
                    </div>
                  )}

                  {/* Submit */}
                  {selected && (
                    <button
                      onClick={() =>
                        mutation.mutate({ verdict: selected, notes, stage })
                      }
                      disabled={mutation.isPending}
                      className="flex items-center gap-2 px-4 py-2 text-xs font-mono font-bold uppercase tracking-widest bg-sentinel/20 text-sentinel border border-sentinel/30 hover:bg-sentinel/30 transition-colors disabled:opacity-50 rounded"
                    >
                      {mutation.isPending ? (
                        <><Loader2 size={12} className="animate-spin" /> Submitting...</>
                      ) : (
                        <><CheckCircle2 size={12} /> Submit Feedback</>
                      )}
                    </button>
                  )}

                  {mutation.isError && (
                    <p className="text-xs font-mono text-sentinel">
                      Submission failed. Try again.
                    </p>
                  )}
                </>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
