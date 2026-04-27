/**
 * CheckpointBanner
 * ================
 * Shown at the top of an incident when it has a PENDING operator-verification
 * checkpoint. Two CTAs: Verify (sign-off) or Override (accept risk with reason).
 *
 * Placed inside Incidents.tsx detail pane, above the action buttons.
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldAlert, ShieldCheck, ShieldOff, Loader2, AlertTriangle, Clock } from "lucide-react";
import { motion, AnimatePresence } from "motion/react";

const BASE = import.meta.env.VITE_API_URL ?? "/api";

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

interface Checkpoint {
  checkpoint_id: string;
  incident_id: string;
  risk_trigger: string;
  risk_level: string;
  exposure_usd: number;
  gnn_confidence: number;
  status: "PENDING" | "VERIFIED" | "OVERRIDDEN" | "EXPIRED";
  verified_by: string;
  verified_at: string;
  override_reason: string;
  created_at: string;
  expires_at: string;
}

interface Props {
  incidentId: string;
}

export function CheckpointBanner({ incidentId }: Props) {
  const qc = useQueryClient();
  const [overrideReason, setOverrideReason] = useState("");
  const [showOverride, setShowOverride] = useState(false);

  const { data, isLoading } = useQuery<{ checkpoint: Checkpoint | null }>({
    queryKey: ["checkpoint", incidentId],
    queryFn: async () => {
      const r = await fetch(`${BASE}/governance/checkpoints/${incidentId}`, {
        headers: authHeaders(),
      });
      if (!r.ok) return { checkpoint: null };
      return r.json();
    },
    refetchInterval: 30_000,
    enabled: !!incidentId,
  });

  const verifyMut = useMutation({
    mutationFn: async (checkpoint_id: string) => {
      const r = await fetch(`${BASE}/governance/checkpoints/verify`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ checkpoint_id }),
      });
      if (!r.ok) throw new Error(await r.text());
      return r.json();
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["checkpoint", incidentId] });
      qc.invalidateQueries({ queryKey: ["governance-checkpoints"] });
    },
  });

  const overrideMut = useMutation({
    mutationFn: async ({ checkpoint_id, reason }: { checkpoint_id: string; reason: string }) => {
      const r = await fetch(`${BASE}/governance/checkpoints/override`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ checkpoint_id, reason }),
      });
      if (!r.ok) throw new Error(await r.text());
      return r.json();
    },
    onSuccess: () => {
      setShowOverride(false);
      setOverrideReason("");
      qc.invalidateQueries({ queryKey: ["checkpoint", incidentId] });
      qc.invalidateQueries({ queryKey: ["governance-checkpoints"] });
    },
  });

  if (isLoading || !data?.checkpoint) return null;

  const chk = data.checkpoint;

  // VERIFIED / OVERRIDDEN: show compact status bar
  if (chk.status === "VERIFIED" || chk.status === "OVERRIDDEN") {
    return (
      <div
        className={`flex items-center gap-3 px-4 py-2.5 rounded border text-xs font-mono ${
          chk.status === "VERIFIED"
            ? "bg-emerald-50 border-emerald-200 text-emerald-700"
            : "bg-yellow-50 border-yellow-200 text-yellow-700"
        }`}
      >
        {chk.status === "VERIFIED" ? <ShieldCheck size={13} /> : <ShieldOff size={13} />}
        <span className="font-bold uppercase tracking-widest">
          Checkpoint {chk.status === "VERIFIED" ? "Verified" : "Overridden"}
        </span>
        <span className="text-slate-500 ml-2">
          by {chk.verified_by || "operator"} ·{" "}
          {chk.verified_at ? new Date(chk.verified_at).toLocaleString() : ""}
        </span>
        {chk.override_reason && (
          <span className="text-yellow-600 ml-2 italic truncate max-w-xs">
            "{chk.override_reason}"
          </span>
        )}
      </div>
    );
  }

  // PENDING
  if (chk.status !== "PENDING") return null;

  const expiresAt = new Date(chk.expires_at);
  const hoursLeft = Math.max(0, (expiresAt.getTime() - Date.now()) / 3_600_000);

  return (
    <motion.div
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      className="border border-orange-200 bg-orange-50 rounded shadow-sm"
    >
      {/* Header */}
      <div className="flex items-start gap-3 px-4 py-3">
        <ShieldAlert size={16} className="text-orange-500 mt-0.5 shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 mb-1">
            <span className="text-xs font-mono font-bold text-orange-700 uppercase tracking-widest">
              Operator Verification Required
            </span>
            <span className="text-orange-600 text-[10px] font-mono flex items-center gap-1">
              <Clock size={10} />
              {hoursLeft.toFixed(1)}h remaining
            </span>
          </div>
          {/* Triggers as pills */}
          <div className="flex flex-wrap gap-1.5 mt-1">
            {chk.risk_trigger.split(" | ").map((t, i) => (
              <span
                key={i}
                className="text-[10px] font-mono bg-orange-100 border border-orange-200 text-orange-700 px-2 py-0.5 rounded shadow-sm"
              >
                {t}
              </span>
            ))}
          </div>
        </div>
        {/* Quick stats */}
        <div className="text-right shrink-0 text-[10px] font-mono text-slate-500 space-y-1">
          <div>Exposure: <span className="text-orange-600 font-bold">${Number(chk.exposure_usd || 0).toLocaleString()}</span></div>
          <div>Praecantator: <span className="text-orange-600 font-bold">{(Number(chk.gnn_confidence || 0) * 100).toFixed(0)}%</span></div>
        </div>
      </div>

      {/* Action bar */}
      <div className="flex items-center gap-2 px-4 pb-3">
        <button
          onClick={() => verifyMut.mutate(chk.checkpoint_id)}
          disabled={verifyMut.isPending}
          className="flex items-center gap-2 px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white text-xs font-mono font-bold uppercase tracking-widest transition-colors rounded shadow-sm disabled:opacity-50"
        >
          {verifyMut.isPending ? (
            <><Loader2 size={12} className="animate-spin" /> Verifying...</>
          ) : (
            <><ShieldCheck size={12} /> Verify &amp; Approve</>
          )}
        </button>
        <button
          onClick={() => setShowOverride(!showOverride)}
          className="flex items-center gap-2 px-4 py-2 border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 hover:text-slate-900 text-xs font-mono font-bold uppercase tracking-widest transition-colors rounded shadow-sm"
        >
          <ShieldOff size={12} className="text-yellow-600" />
          Override Risk
        </button>
      </div>

      {/* Override reason panel */}
      <AnimatePresence>
        {showOverride && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden border-t border-orange-200"
          >
            <div className="px-4 pb-4 pt-3 space-y-2 bg-white">
              <div className="flex items-center gap-2 text-[10px] font-mono text-orange-600">
                <AlertTriangle size={10} />
                Override reason is required and written to the immutable audit log.
              </div>
              <textarea
                value={overrideReason}
                onChange={(e) => setOverrideReason(e.target.value)}
                placeholder="State your reason for overriding this checkpoint..."
                rows={2}
                className="w-full text-xs font-mono bg-white border border-slate-200 text-slate-900 px-3 py-2 rounded resize-none shadow-sm focus:outline-none focus:border-orange-500 focus:ring-1 focus:ring-orange-500 placeholder:text-slate-400"
              />
              <button
                onClick={() => overrideMut.mutate({ checkpoint_id: chk.checkpoint_id, reason: overrideReason })}
                disabled={overrideReason.trim().length < 3 || overrideMut.isPending}
                className="flex items-center gap-2 px-4 py-1.5 bg-yellow-500 hover:bg-yellow-600 text-white text-xs font-mono font-bold uppercase tracking-widest transition-colors rounded shadow-sm disabled:opacity-40"
              >
                {overrideMut.isPending ? (
                  <><Loader2 size={11} className="animate-spin" /> Overriding...</>
                ) : (
                  "Confirm Override"
                )}
              </button>
              {overrideMut.isError && (
                <p className="text-xs font-mono text-red-600">Override failed. Try again.</p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
