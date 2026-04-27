/**
 * Compliance.tsx — v4 Governance & Audit Dashboard
 * =================================================
 * Five tabs:
 *   1. Incidents      — resolved incident ledger (existing)
 *   2. Post-Action    — action delivery verification dashboard
 *   3. Replay         — after-action incident replay
 *   4. Metrics        — governance precision/recall/F1
 *   5. System Log     — raw audit log
 */
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { generateAuditReport } from "@/lib/generateAuditReport";
import {
  Shield, Download, FileText, Clock,
  ChevronDown, ChevronUp, Check, X, AlertTriangle,
  CheckCircle2, XCircle, HelpCircle, RefreshCw,
  Activity, BarChart3, Play, Loader2, ExternalLink, FileDown,
} from "lucide-react";
import { motion, AnimatePresence } from "motion/react";
import { api } from "@/lib/api";

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

async function authFetch<T>(url: string, opts?: RequestInit): Promise<T> {
  const r = await fetch(url, { ...opts, headers: authHeaders() });
  if (!r.ok) throw new Error(`${url} → ${r.status}`);
  return r.json();
}

const STATUS_BADGE: Record<string, { bg: string; text: string; icon: React.ElementType }> = {
  RESOLVED:          { bg: "bg-emerald-50",  text: "text-emerald-600", icon: Check },
  APPROVED:          { bg: "bg-green-50",    text: "text-green-600",   icon: Check },
  DISMISSED:         { bg: "bg-slate-100",   text: "text-slate-400",   icon: X },
  AWAITING_APPROVAL: { bg: "bg-red-50",      text: "text-red-600",     icon: AlertTriangle },
};

const VERDICT_META: Record<string, { label: string; color: string; bg: string; icon: React.ElementType }> = {
  TRUE_POSITIVE:  { label: "True Positive",  color: "text-emerald-600", bg: "bg-emerald-50 border-emerald-200", icon: CheckCircle2 },
  FALSE_POSITIVE: { label: "False Positive", color: "text-red-600",     bg: "bg-red-50 border-red-200",         icon: XCircle },
  FALSE_NEGATIVE: { label: "False Negative", color: "text-orange-600",  bg: "bg-orange-50 border-orange-200",   icon: AlertTriangle },
  UNCERTAIN:      { label: "Uncertain",      color: "text-slate-400",   bg: "bg-slate-50 border-slate-200",      icon: HelpCircle },
};

type Tab = "incidents" | "post-action" | "replay" | "metrics" | "audit";

// ── Sub-components ────────────────────────────────────────────────────────────

/** Gauge bar for precision / recall / F1 */
function MetricBar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div>
      <div className="flex justify-between text-xs font-headline mb-1.5 font-bold">
        <span className="text-slate-400 uppercase tracking-widest">{label}</span>
        <span className={`${color}`}>{(value * 100).toFixed(1)}%</span>
      </div>
      <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${value * 100}%` }}
          transition={{ duration: 0.7, ease: "easeOut" }}
          className={`h-full rounded-full ${color.replace("text-", "bg-")}`}
        />
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

const Compliance = () => {
  const [tab, setTab] = useState<Tab>("incidents");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const qc = useQueryClient();

  // ── Data fetches ──
  const { data: incidents = [] } = useQuery({
    queryKey: ["incidents"],
    queryFn: () => authFetch<unknown[]>(`${BASE}/incidents`),
    refetchInterval: 30_000,
  });

  const { data: auditLog = [] } = useQuery({
    queryKey: ["audit"],
    queryFn: () => authFetch<unknown[]>(`${BASE}/audit`),
    refetchInterval: 60_000,
  });

  const { data: postActionData } = useQuery({
    queryKey: ["post-action-list"],
    queryFn: () => authFetch<{ records: any[]; total: number }>(`${BASE}/governance/post-action`),
    refetchInterval: 30_000,
    enabled: tab === "post-action",
  });

  const { data: replayData } = useQuery({
    queryKey: ["replay-history"],
    queryFn: () => authFetch<{ runs: any[]; total: number }>(`${BASE}/governance/replay/history`),
    refetchInterval: 60_000,
    enabled: tab === "replay",
  });

  const { data: govMetrics } = useQuery({
    queryKey: ["governance-summary"],
    queryFn: () => authFetch<any>(`${BASE}/governance/summary`),
    refetchInterval: 60_000,
    enabled: tab === "metrics",
  });

  const replayMut = useMutation({
    mutationFn: async (run_id: string) =>
      authFetch<any>(`${BASE}/orchestration/replay/autonomous/${run_id}`, { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["replay-history"] });
      qc.invalidateQueries({ queryKey: ["incidents"] });
    },
  });

  // ── Derived ──
  const resolvedIncidents = (incidents as Record<string, unknown>[]).filter((i) =>
    ["RESOLVED", "APPROVED", "DISMISSED"].includes(String(i.status))
  );
  const postRecords = postActionData?.records ?? [];
  const replayRuns  = replayData?.runs ?? [];
  const gm          = govMetrics ?? {};

  const TABS: { key: Tab; label: string; count?: number; icon: React.ElementType }[] = [
    { key: "incidents",    label: "Incidents",    count: resolvedIncidents.length, icon: Shield },
    { key: "post-action",  label: "Post-Action",  count: postRecords.length,       icon: CheckCircle2 },
    { key: "replay",       label: "Replay",       count: replayRuns.length,        icon: Play },
    { key: "metrics",      label: "Metrics",                                       icon: BarChart3 },
    { key: "audit",        label: "System Log",   count: (auditLog as any[]).length, icon: FileText },
  ];

  return (
    <div className="h-[calc(100vh-120px)] flex flex-col min-h-0">
      {/* ── Header ── */}
      <div className="flex items-center justify-between px-5 py-3 border border-slate-200 bg-white shrink-0 rounded-t-xl">
        <div className="flex items-center gap-3 flex-wrap">
          <Shield size={16} className="text-red-500" />
          <span className="text-xs font-headline uppercase tracking-[0.2em] text-slate-500 font-bold">
            Compliance &amp; Governance
          </span>
          {/* Tab pills */}
          <div className="flex items-center gap-1 flex-wrap ml-4 bg-slate-50 p-1 rounded-lg border border-slate-200">
            {TABS.map((t) => {
              const Icon = t.icon;
              return (
                <button
                  key={t.key}
                  onClick={() => setTab(t.key)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-headline font-bold uppercase tracking-widest transition-all rounded-md ${
                    tab === t.key
                      ? "bg-white text-red-600 shadow-sm ring-1 ring-slate-200"
                      : "text-slate-400 hover:text-slate-600 hover:bg-white/50"
                  }`}
                >
                  <Icon size={11} />
                  {t.label}
                  {t.count !== undefined && t.count > 0 && (
                    <span className={`ml-1.5 text-[9px] font-mono px-1.5 py-0.5 rounded ${
                      tab === t.key ? "bg-red-50 text-red-600" : "bg-slate-200 text-slate-500"
                    }`}>
                      {t.count}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* Export actions */}
        <div className="flex items-center gap-2">
          {tab === "incidents" && (
            <button
              onClick={() => {
                const rows = resolvedIncidents.map((inc) =>
                  [
                    String(inc.id || ""), String(inc.event_title || "").replace(/,/g, ";"),
                    String(inc.severity || ""), String(inc.status || ""),
                    Number(inc.affected_node_count || 0), Number(inc.total_exposure_usd || 0),
                    (Number(inc.gnn_confidence || 0) * 100).toFixed(0) + "%",
                    String(inc.recommendation || ""), String(inc.created_at || ""),
                  ].join(",")
                );
                const csv = ["ID,Title,Severity,Status,Nodes,Exposure,Praecantator Confidence,Recommendation,Created", ...rows].join("\n");
                const blob = new Blob([csv], { type: "text/csv" });
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url; a.download = `compliance_${new Date().toISOString().slice(0, 10)}.csv`; a.click();
                URL.revokeObjectURL(url);
              }}
              className="flex items-center gap-1.5 text-[10px] font-mono uppercase font-bold tracking-widest px-3 py-1.5 bg-white text-slate-600 hover:text-red-600 border border-slate-200 hover:border-red-200 transition-all rounded shadow-sm"
            >
              <Download size={12} /> CSV
            </button>
          )}
          <button
            onClick={() => window.open(`${BASE}/audit/export`, "_blank")}
            className="flex items-center gap-1.5 text-[10px] font-mono uppercase font-bold tracking-widest px-3 py-1.5 bg-white text-slate-600 hover:text-red-600 border border-slate-200 hover:border-red-200 transition-all rounded shadow-sm"
          >
            <FileText size={12} /> PDF
          </button>
          {/* ── Full DOCX Audit Report ── */}
          <button
            disabled={reportLoading}
            onClick={async () => {
              setReportLoading(true);
              try {
                await generateAuditReport(
                  incidents as any[],
                  auditLog as any[],
                  govMetrics,
                  postRecords,
                );
              } finally {
                setReportLoading(false);
              }
            }}
            className="flex items-center gap-1.5 text-[10px] font-mono uppercase font-bold tracking-widest px-3 py-1.5 bg-red-600 text-white hover:bg-red-700 border border-red-600 transition-all rounded shadow-sm disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {reportLoading
              ? <><Loader2 size={12} className="animate-spin" /> Generating...</>
              : <><FileDown size={12} /> Download Report</>}
          </button>
        </div>
      </div>

      {/* ── Content ── */}
      <div className="flex-1 min-h-0 border border-t-0 border-slate-200 bg-white overflow-y-auto custom-scrollbar rounded-b-xl shadow-sm">

        {/* ── Tab: Incidents (resolved ledger) ── */}
        {tab === "incidents" && (
          <div className="divide-y divide-slate-100">
            {resolvedIncidents.length === 0 && (
              <div className="p-12 text-center text-slate-400 font-mono font-bold text-sm uppercase tracking-widest">
                No resolved incidents in ledger.
              </div>
            )}
            {resolvedIncidents.map((inc) => {
              const badge = STATUS_BADGE[String(inc.status)] || STATUS_BADGE.RESOLVED;
              const BadgeIcon = badge.icon;
              const isExpanded = expandedId === String(inc.id);
              return (
                <div key={String(inc.id)}>
                  <div
                    onClick={() => setExpandedId(isExpanded ? null : String(inc.id))}
                    className={`flex items-center gap-5 px-6 py-4 cursor-pointer transition-colors ${
                      isExpanded ? "bg-slate-50" : "hover:bg-slate-50"
                    }`}
                  >
                    <div className="w-10 flex justify-center">
                      <span className={`inline-flex items-center justify-center w-8 h-8 rounded-lg shadow-sm border border-slate-200 ${badge.bg}`}>
                        <BadgeIcon size={16} className={badge.text} />
                      </span>
                    </div>
                    <div className="flex-1 min-w-0">
                      <span className="text-sm text-slate-900 font-bold tracking-tight truncate block uppercase">
                        {String(inc.event_title || "Incident")}
                      </span>
                      <span className="text-xs font-mono font-bold text-slate-400 mt-1 block uppercase tracking-wide">
                        {Number(inc.affected_node_count || 0)} nodes ·
                        <span className="text-red-500 font-extrabold ml-1">
                          ${Number(inc.total_exposure_usd || 0).toLocaleString()} VAL
                        </span>
                      </span>
                    </div>
                    <div className="flex items-center gap-6 text-xs font-mono font-bold text-slate-400 shrink-0">
                      <span className={`uppercase px-2.5 py-1 rounded shadow-inner text-[10px] tracking-widest bg-white border border-slate-200 ${badge.text}`}>
                        {String(inc.status || "").replace(/_/g, " ")}
                      </span>
                      <span className="flex items-center gap-1.5 text-[10px]">
                        <Clock size={12} className="text-slate-300" />
                        {inc.created_at ? new Date(String(inc.created_at)).toLocaleDateString() : "—"}
                      </span>
                      {isExpanded ? <ChevronUp size={16} className="text-red-500" /> : <ChevronDown size={16} />}
                    </div>
                  </div>
                  {isExpanded && (
                    <div className="px-6 pb-6 pl-21 bg-slate-50/50 border-t border-slate-100">
                      <div className="grid grid-cols-4 gap-6 py-6 text-sm">
                        <div className="border border-slate-200 bg-white p-4 rounded-lg shadow-sm">
                          <span className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-widest block mb-2">Severity</span>
                          <span className="text-slate-900 font-bold uppercase tracking-tight">{String(inc.severity || "—")}</span>
                        </div>
                        <div className="border border-slate-200 bg-white p-4 rounded-lg shadow-sm">
                          <span className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-widest block mb-2">Praecantator Confidence</span>
                          <span className="text-blue-600 font-bold">{(Number(inc.gnn_confidence || 0) * 100).toFixed(0)}%</span>
                        </div>
                        <div className="border border-slate-200 bg-white p-4 rounded-lg shadow-sm col-span-2">
                          <span className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-widest block mb-2">Decision Log</span>
                          <span className="text-slate-700 font-medium leading-relaxed truncate block" title={String(inc.recommendation || "—")}>
                            {String(inc.recommendation || "—")}
                          </span>
                        </div>
                      </div>
                      {/* OODA pipeline timeline */}
                      <div className="border border-slate-200 p-5 bg-white rounded-lg shadow-sm border-l-4 border-l-red-500">
                        <p className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-widest mb-4">Autonomous Execution Timeline</p>
                        <div className="flex items-center justify-between mx-4">
                          {[
                            { stage: "DETECT",  time: inc.created_at,  done: true },
                            { stage: "ANALYZE", time: inc.analyzed_at, done: true },
                            { stage: "DECIDE",  time: inc.approved_at, done: inc.status !== "DISMISSED" },
                            { stage: "EXECUTE", time: inc.resolved_at || inc.approved_at, done: inc.status === "APPROVED" || inc.status === "RESOLVED" },
                            { stage: "AUDIT",   time: inc.updated_at,  done: true },
                          ].map((step, idx, arr) => (
                            <div key={step.stage} className="flex flex-col items-center relative group">
                              <div className={`w-3 h-3 rounded-full z-10 transition-transform group-hover:scale-125 ${
                                step.done ? "bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.4)]" : "bg-slate-200"
                              }`} />
                              <span className={`text-[10px] font-mono font-bold mt-2 tracking-wide ${step.done ? "text-slate-900" : "text-slate-400"}`}>
                                {step.stage}
                              </span>
                              <span className="text-[9px] font-mono text-slate-400 mt-1 uppercase">
                                {step.time ? new Date(String(step.time)).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : "—"}
                              </span>
                              {idx < arr.length - 1 && (
                                <div className={`absolute h-0.5 w-[calc(100%+4rem)] top-1.5 left-1.5 -z-0 ${
                                  arr[idx+1].done ? "bg-red-200" : "bg-slate-100"
                                }`} />
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* ── Tab: Post-Action Verification ── */}
        {tab === "post-action" && (
          <div>
            {postRecords.length === 0 && (
              <div className="p-12 text-center text-slate-400 font-mono font-bold text-sm uppercase tracking-widest">
                No active verification records found.
              </div>
            )}
            <div className="divide-y divide-slate-100">
              {postRecords.map((rec: any) => {
                const allOk = rec.actions_total > 0 && rec.actions_failed === 0;
                const hasFail = rec.actions_failed > 0;
                const verdict = rec.feedback_verdict;
                const vd = verdict ? VERDICT_META[verdict] : null;
                return (
                  <div key={rec.incident_id} className="px-6 py-5 hover:bg-slate-50 transition-colors">
                    <div className="flex items-start gap-5">
                      {/* Delivery indicator */}
                      <div className="mt-1 shrink-0">
                        {rec.actions_total === 0 ? (
                          <div className="w-10 h-10 rounded-lg flex items-center justify-center bg-slate-100 border border-slate-200">
                            <HelpCircle size={18} className="text-slate-400" />
                          </div>
                        ) : hasFail ? (
                          <div className="w-10 h-10 rounded-lg flex items-center justify-center bg-red-50 border border-red-200">
                            <XCircle size={18} className="text-red-500" />
                          </div>
                        ) : allOk ? (
                          <div className="w-10 h-10 rounded-lg flex items-center justify-center bg-emerald-50 border border-emerald-200">
                            <CheckCircle2 size={18} className="text-emerald-500" />
                          </div>
                        ) : (
                          <div className="w-10 h-10 rounded-lg flex items-center justify-center bg-blue-50 border border-blue-200">
                            <Activity size={18} className="text-blue-500 animate-pulse" />
                          </div>
                        )}
                      </div>

                      {/* Main content */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-3 flex-wrap mb-2">
                          <span className="text-base font-headline font-bold text-slate-900 uppercase tracking-tight">
                            {String(rec.event_title || "Incident")}
                          </span>
                          <span className={`text-[10px] font-mono font-bold uppercase px-2.5 py-1 rounded shadow-sm border ${
                            STATUS_BADGE[rec.status]?.bg} ${STATUS_BADGE[rec.status]?.text} ${STATUS_BADGE[rec.status]?.text.replace('text-', 'border-')}/30`}>
                            {String(rec.status || "").replace(/_/g, " ")}
                          </span>
                          {vd && (
                            <span className={`flex items-center gap-1.5 text-[10px] font-mono font-bold uppercase px-2.5 py-1 rounded border shadow-sm ${vd.bg} ${vd.color}`}>
                              <vd.icon size={11} />{vd.label}
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-6 text-[10px] font-mono font-bold text-slate-400 uppercase tracking-widest">
                          <span className="text-red-500">${Number(rec.total_exposure_usd || 0).toLocaleString()} Exposure</span>
                          <span className="flex items-center gap-1.5 px-2 py-0.5 bg-slate-100 rounded">
                            <Activity size={12} className="text-slate-500" />
                            {rec.actions_delivered}/{rec.actions_total} delivered
                            {hasFail && (
                              <span className="text-red-600 font-extrabold ml-1">· {rec.actions_failed} FAILED</span>
                            )}
                          </span>
                          {rec.resolved_at && (
                            <span className="flex items-center gap-1.5">
                              <Clock size={12} className="text-slate-300" />
                              {new Date(String(rec.resolved_at)).toLocaleString()}
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Detail link */}
                      <a
                        href={`/dashboard/incidents?id=${rec.incident_id}`}
                        className="shrink-0 group px-4 py-2 bg-slate-50 hover:bg-red-50 border border-slate-200 hover:border-red-200 rounded text-[10px] font-mono font-bold text-slate-500 hover:text-red-600 transition-all shadow-sm flex items-center gap-2 uppercase tracking-widest"
                      >
                        Details <ExternalLink size={12} className="group-hover:translate-x-0.5 transition-transform" />
                      </a>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ── Tab: Replay (after-action review) ── */}
        {tab === "replay" && (
          <div>
            <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50">
              <div className="flex items-start gap-3">
                <HelpCircle size={16} className="text-blue-500 mt-0.5" />
                <p className="text-[11px] font-mono font-bold text-slate-500 uppercase tracking-widest leading-relaxed">
                  Historical Analysis Mode: Replay autonomous execution paths to verify reasoning logic. 
                  Replays generate a new <span className="text-blue-600">audit trail</span> without re-executing external API impacts.
                </p>
              </div>
            </div>
            {replayRuns.length === 0 && (
              <div className="p-12 text-center text-slate-400 font-mono font-bold text-sm uppercase tracking-widest">
                No orchestration history found.
              </div>
            )}
            <div className="divide-y divide-slate-100">
              {replayRuns.map((run: any) => {
                const isRunning = replayMut.isPending && replayMut.variables === run.run_id;
                return (
                  <div key={run.run_id} className="flex items-center gap-6 px-6 py-5 hover:bg-slate-50 transition-colors">
                    <div className="w-10 h-10 rounded-lg bg-blue-50 border border-blue-100 flex items-center justify-center shadow-sm">
                      <Play size={18} className="text-blue-500 fill-blue-500/10" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-4 mb-2 flex-wrap">
                        <span className="text-sm font-headline font-bold text-slate-900 uppercase tracking-tight">
                          {String(run.orchestration_path || "autonomous_pipeline")}
                        </span>
                        <span className={`text-[10px] font-mono font-bold uppercase px-2.5 py-1 rounded shadow-sm border ${
                          run.status === "COMPLETED"
                            ? "bg-emerald-50 text-emerald-600 border-emerald-200"
                            : run.status === "FAILED"
                            ? "bg-red-50 text-red-600 border-red-200"
                            : "bg-amber-50 text-amber-600 border-amber-200"
                        }`}>
                          {String(run.status || "UNKNOWN")}
                        </span>
                      </div>
                      <div className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-widest flex items-center gap-6">
                        <span className="bg-slate-100 px-2 py-0.5 rounded">ID: {String(run.run_id).slice(0, 8)}…{String(run.run_id).slice(-4)}</span>
                        {run.created_at && (
                          <span className="flex items-center gap-1.5 text-slate-400">
                            <Clock size={12} className="text-slate-300" />
                            {new Date(String(run.created_at)).toLocaleString()}
                          </span>
                        )}
                      </div>
                    </div>
                    <button
                      onClick={() => replayMut.mutate(run.run_id)}
                      disabled={replayMut.isPending}
                      className="flex items-center gap-2.5 px-5 py-2.5 text-[10px] font-mono font-bold uppercase tracking-widest bg-white border border-slate-200 hover:border-red-500 hover:text-red-600 transition-all rounded shadow-sm disabled:opacity-40 disabled:hover:border-slate-200 disabled:hover:text-slate-500"
                    >
                      {isRunning ? (
                        <><Loader2 size={13} className="animate-spin" /> RUNNING...</>
                      ) : (
                        <><RefreshCw size={13} /> INITIATE REPLAY</>
                      )}
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ── Tab: Governance Metrics ── */}
        {tab === "metrics" && (
          <div className="p-8 space-y-8 bg-slate-50/30">
            {!govMetrics && (
              <div className="text-center text-slate-400 font-mono font-bold text-sm py-12 uppercase tracking-[0.2em] animate-pulse">Calculating Governance Precision...</div>
            )}
            {govMetrics && (
              <>
                {/* KPI strip */}
                <div className="grid grid-cols-4 gap-4">
                  {[
                    { label: "Feedback Loop",     value: String(gm.total_feedback ?? 0), color: "text-slate-900" },
                    { label: "Praecantator Precision", value: `${((gm.precision ?? 0) * 100).toFixed(1)}%`,  color: "text-emerald-600" },
                    { label: "Praecantator Recall",    value: `${((gm.recall ?? 0) * 100).toFixed(1)}%`,    color: "text-blue-600" },
                    { label: "Stability Score",   value: `${((gm.f1_score ?? 0) * 100).toFixed(1)}%`,  color: "text-red-500" },
                  ].map((m) => (
                    <div key={m.label} className="border border-slate-200 bg-white p-6 rounded-xl shadow-sm border-b-4 border-b-slate-100">
                      <div className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-[0.15em] mb-3">{m.label}</div>
                      <div className={`text-3xl font-headline font-bold tracking-tight ${m.color}`}>{m.value}</div>
                    </div>
                  ))}
                </div>

                {/* Metric bars */}
                <div className="grid grid-cols-2 gap-8">
                  <div className="border border-slate-200 bg-white p-8 rounded-xl shadow-sm space-y-6">
                    <p className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-[0.2em] mb-4">Pipeline Quality Index</p>
                    <MetricBar label="Detection Precision"  value={gm.precision  ?? 0} color="text-emerald-500" />
                    <MetricBar label="Risk Recall Rate"     value={gm.recall     ?? 0} color="text-blue-500" />
                    <MetricBar label="Composite F1 Score"   value={gm.f1_score   ?? 0} color="text-red-500" />
                  </div>

                  {/* Verdict breakdown */}
                  <div className="border border-slate-200 bg-white p-8 rounded-xl shadow-sm">
                    <p className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-[0.2em] mb-6">Model Classification Verification</p>
                    <div className="grid grid-cols-2 gap-4">
                      {Object.entries(VERDICT_META).map(([key, vd]) => {
                        const Icon = vd.icon;
                        const count = (gm.verdicts ?? {})[key] ?? 0;
                        const total = gm.total_feedback || 1;
                        const pct = Math.round((count / total) * 100);
                        return (
                          <div key={key} className={`flex items-center gap-4 px-5 py-4 rounded-lg border shadow-sm transition-all hover:bg-white uppercase tracking-wider ${vd.bg.split(' ')[0]}`}>
                            <Icon size={16} className={vd.color} />
                            <div className="flex-1 min-w-0">
                              <div className={`text-[10px] font-mono font-bold uppercase tracking-widest ${vd.color}`}>{vd.label}</div>
                              <div className="text-[10px] font-mono text-slate-400 mt-1">{pct}% of sample</div>
                            </div>
                            <span className={`text-2xl font-headline font-bold ${vd.color}`}>{count}</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>

                {/* False positive by stage */}
                {Object.keys(gm.false_positive_by_stage ?? {}).length > 0 && (
                  <div className="border border-slate-200 bg-white p-8 rounded-xl shadow-sm">
                    <p className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-[0.2em] mb-6">
                      Pipeline Friction Analysis · FP Clusters
                    </p>
                    <div className="grid grid-cols-3 gap-6">
                      {Object.entries(gm.false_positive_by_stage ?? {}).map(([stage, count]) => (
                        <div key={stage} className="flex flex-col p-4 bg-slate-50 border border-slate-100 rounded-lg">
                          <span className="text-[10px] font-mono text-slate-500 font-bold uppercase tracking-widest mb-2 border-b border-slate-200 pb-2">{stage.replace(/_/g, " ")}</span>
                          <span className="text-2xl font-headline text-red-500 font-bold uppercase tracking-tighter">
                            {String(count)} <span className="text-xs text-slate-400 ml-1">Detected</span>
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Pending checkpoints */}
                {Number(gm.pending_checkpoints ?? 0) > 0 && (
                  <div className="border-2 border-amber-200 bg-amber-50 px-8 py-6 rounded-xl flex items-center gap-5 shadow-lg animate-pulse">
                    <div className="w-12 h-12 bg-amber-200 rounded-full flex items-center justify-center shrink-0">
                      <AlertTriangle size={24} className="text-amber-600" />
                    </div>
                    <div>
                      <p className="text-sm font-headline font-bold text-amber-900 uppercase tracking-[0.1em]">
                        {gm.pending_checkpoints} HIGH-RISK DECISIONS PENDING
                      </p>
                      <p className="text-[11px] font-mono font-bold text-amber-700 mt-1 uppercase tracking-widest">
                        System requires manual sign-off for critical interventions.
                      </p>
                    </div>
                    <a
                      href="/dashboard/incidents"
                      className="ml-auto bg-amber-600 text-white px-6 py-2.5 rounded-lg text-xs font-mono font-bold uppercase tracking-widest hover:bg-amber-700 transition-colors shadow-md"
                    >
                      Audit Now
                    </a>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* ── Tab: System Audit Log ── */}
        {tab === "audit" && (
          <div className="divide-y divide-slate-100">
            {(auditLog as any[]).length === 0 && (
              <div className="p-12 text-center text-slate-400 font-mono font-bold text-sm uppercase tracking-widest">
                Audit Trail Empty.
              </div>
            )}
            {(auditLog as any[]).map((entry: any, i: number) => (
              <div key={i} className="flex items-center gap-8 px-8 py-3.5 hover:bg-slate-50 transition-colors font-mono">
                <span className="text-[10px] font-bold text-slate-400 w-44 shrink-0 uppercase tracking-widest">
                  {entry.timestamp ? new Date(String(entry.timestamp)).toLocaleString() : "—"}
                </span>
                <span className="text-[10px] font-bold tracking-[0.2em] text-red-500 uppercase w-56 shrink-0 truncate border-l-2 border-slate-100 pl-4">
                  {String(entry.action || "—")}
                </span>
                <span className="text-[11px] font-bold text-slate-600 truncate flex-1 uppercase tracking-tight">
                  {String(entry.payload || "—").replace(/[{}"]/g, '')}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default Compliance;
