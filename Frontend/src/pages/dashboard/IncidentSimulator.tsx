import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Clock,
  DollarSign,
  ExternalLink,
  Plane,
  Send,
  Shield,
  Ship,
  Truck,
  Zap,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";

import { api } from "@/lib/api";
import { ReasoningPanel } from "@/components/workflow/ReasoningPanel";

const BASE = import.meta.env.VITE_API_URL ?? "/api";

import { getAccessToken, getUserId } from "@/lib/api";

function authHeaders(): HeadersInit {
  const token = getAccessToken();
  const userId = getUserId();
  return {
    "Content-Type": "application/json",
    "X-User-Id": userId,
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function authFetch<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, { ...options, headers: authHeaders() });
  if (!res.ok) throw new Error(`${url} -> ${res.status}`);
  return res.json();
}

type AffectedNode = {
  id: string;
  name: string;
  tier: number;
  country?: string;
  risk_score: number;
  exposure_usd: number;
  single_source?: boolean;
  detail?: string;
};

type RouteOption = {
  mode: string;
  description: string;
  transit_days: number;
  cost_usd: number;
  recommended: boolean;
  status_label?: string;
};

type MonteCarloSummary = {
  protected_rate?: number;
  route_reliability?: number;
  estimated_loss_avoided_usd?: number;
  expected_delay_days?: number;
  worst_case_loss_usd?: number;
  confidence_interval_low?: number;
  confidence_interval_high?: number;
  runs?: number;
};

type SimulationIncident = {
  id: string;
  event_title: string;
  event_description: string;
  severity: string;
  status: string;
  created_at: string;
  source_url?: string;
  pipeline_ms?: number;
  affected_node_count: number;
  affected_nodes: AffectedNode[];
  total_exposure_usd: number;
  min_stockout_days: number;
  gnn_confidence: number;
  recommendation: string;
  recommendation_detail: string;
  route_options: RouteOption[];
  backup_supplier?: {
    name: string;
    location: string;
    lead_time_days?: number;
    email?: string;
  };
  rfq_draft?: {
    provider?: string;
    to?: string;
    subject?: string;
    body?: string;
    editable?: boolean;
  };
  value_at_risk_usd?: number;
  monte_carlo?: MonteCarloSummary;
  simulation_only?: boolean;
};

const SEVERITY: Record<string, { bg: string; text: string; icon: string }> = {
  CRITICAL: { bg: "bg-red-50 border-red-200", text: "text-red-600", icon: "★" },
  HIGH: { bg: "bg-orange-50 border-orange-200", text: "text-orange-600", icon: "◉" },
  MODERATE: { bg: "bg-yellow-50 border-yellow-200", text: "text-yellow-600", icon: "◎" },
  LOW: { bg: "bg-green-50 border-green-200", text: "text-green-600", icon: "○" },
};

const MODE_ICONS: Record<string, React.ElementType> = { air: Plane, sea: Ship, land: Truck };

const STATUS_COLORS: Record<string, string> = {
  AWAITING_APPROVAL: "text-red-600 bg-red-50 border border-red-100",
  ANALYZED: "text-blue-600 bg-blue-50 border border-blue-100",
  DETECTED: "text-yellow-600 bg-yellow-50 border border-yellow-100",
  APPROVED: "text-green-600 bg-green-50 border border-green-100",
  RESOLVED: "text-emerald-600 bg-emerald-50 border border-emerald-100",
  DISMISSED: "text-slate-400 bg-slate-100",
};

const IncidentSimulator = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedId = searchParams.get("id");
  const [statusFilter, setStatusFilter] = useState("");
  const [rfqExpanded, setRfqExpanded] = useState(false);

  const { data: simulations = [] } = useQuery({
    queryKey: ["intelligence", "simulation-incidents", statusFilter],
    queryFn: () => api.intelligence.simulationIncidents(statusFilter || undefined),
    refetchInterval: 15_000,
  });

  const { data: detail } = useQuery<SimulationIncident>({
    queryKey: ["simulation-incident", selectedId],
    queryFn: () => authFetch<SimulationIncident>(`${BASE}/incidents/${selectedId}`),
    enabled: !!selectedId,
  });

  useEffect(() => {
    setRfqExpanded(false);
  }, [selectedId]);

  useEffect(() => {
    if (!selectedId && simulations.length > 0) {
      setSearchParams({ id: String(simulations[0].id) });
    }
  }, [simulations, selectedId, setSearchParams]);

  const statuses = ["", "ANALYZED", "AWAITING_APPROVAL"];
  const monteCarlo = detail?.monte_carlo || {};
  const isNoImpactResult =
    String(detail?.status || "").toUpperCase() === "ANALYZED" &&
    Number(detail?.affected_node_count || 0) === 0;

  return (
    <div className="h-[calc(100vh-120px)] flex gap-0 min-h-0">
      <div className="w-[360px] shrink-0 border border-slate-200 bg-white flex flex-col min-h-0">
        <div className="px-5 py-4 border-b border-slate-200 shrink-0">
          <div className="flex items-center gap-2 mb-3">
            <Zap size={16} className="text-red-500" />
            <span className="text-xs font-mono font-bold uppercase tracking-widest text-slate-500">
              Monte Carlo · {simulations.length}
            </span>
          </div>
          <div className="flex flex-wrap gap-2">
            {statuses.map((s) => (
              <button
                key={s || "all"}
                onClick={() => setStatusFilter(s)}
                className={`text-[10px] sm:text-xs font-mono font-bold uppercase tracking-widest px-2.5 py-1 transition-colors rounded ${
                  statusFilter === s
                    ? "bg-red-50 text-red-600 border border-red-200"
                    : "bg-slate-100 text-slate-500 hover:text-slate-900"
                }`}
              >
                {s || "ALL"}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto custom-scrollbar divide-y divide-slate-200/50">
          {simulations.length === 0 && (
            <div className="p-8 text-center text-slate-400 text-sm font-mono space-y-3 font-medium">
              <p>No Monte Carlo runs yet.</p>
              <Link
                to="/dashboard/intelligence"
                className="inline-flex items-center gap-2 text-red-500 hover:underline font-bold"
              >
                Open Intelligence
              </Link>
            </div>
          )}

          {simulations.map((incident) => {
            const sev = SEVERITY[String(incident.severity)] || SEVERITY.LOW;
            const isSelected = String(incident.id) === selectedId;
            return (
              <div
                key={String(incident.id)}
                onClick={() => setSearchParams({ id: String(incident.id) })}
                className={`px-5 py-4 cursor-pointer transition-all border-l-[3px] ${
                  isSelected
                    ? "bg-slate-50 border-l-red-500"
                    : "hover:bg-slate-50 border-l-transparent"
                }`}
              >
                <div className="flex items-center gap-3 mb-2">
                  <span className={`${sev.text} text-base`}>{sev.icon}</span>
                  <span className="text-sm font-bold text-slate-900 truncate flex-1 tracking-wide">
                    {String(incident.event_title || "Simulation")}
                  </span>
                  <span className="text-[10px] sm:text-xs font-mono font-bold uppercase px-2 py-0.5 rounded text-blue-600 bg-blue-50 border border-blue-100">
                    SIM
                  </span>
                </div>
                <div className="flex items-center gap-4 text-xs font-mono font-bold text-slate-400 pl-[26px]">
                  <span>{Number(incident.affected_node_count || 0)} nodes</span>
                  <span>${Number(incident.total_exposure_usd || 0).toLocaleString()}</span>
                  <span>Praecantator {(Number(incident.gnn_confidence || 0) * 100).toFixed(0)}%</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="flex-1 border border-l-0 border-slate-200 bg-white flex flex-col min-h-0 overflow-y-auto custom-scrollbar shadow-inner">
        {!selectedId ? (
          <div className="flex-1 flex items-center justify-center text-slate-400 font-mono text-sm font-bold">
            Run Monte Carlo from Intelligence to open a simulation.
          </div>
        ) : !detail ? (
          <div className="flex-1 flex items-center justify-center text-slate-400 font-mono text-sm font-bold uppercase tracking-widest">
            Loading simulation...
          </div>
        ) : (
          <div className="p-5 space-y-4">
            <div>
              <div className="flex items-center gap-3 mb-3">
                <span
                  className={`text-xs font-mono font-bold uppercase tracking-widest px-2.5 py-1 rounded border shadow-sm ${
                    (SEVERITY[String(detail.severity)] || SEVERITY.LOW).bg
                  } ${(SEVERITY[String(detail.severity)] || SEVERITY.LOW).text}`}
                >
                  {String(detail.severity)}
                </span>
                <span className="text-xs font-mono font-bold uppercase px-2.5 py-1 rounded text-blue-600 bg-blue-50 border border-blue-100">
                  Intelligence
                </span>
                <span
                  className={`text-xs font-mono font-bold uppercase px-2.5 py-1 rounded shadow-sm ${
                    STATUS_COLORS[String(detail.status)] || ""
                  }`}
                >
                  {String(detail.status || "").replace(/_/g, " ")}
                </span>
                {detail.pipeline_ms && Number(detail.pipeline_ms) > 0 && (
                  <span className="text-xs font-mono font-bold text-slate-400 ml-auto flex items-center gap-1.5 bg-slate-50 px-2 py-1 rounded border border-slate-200">
                    <Zap size={12} className="text-red-500" />
                    Pipeline: {Number(detail.pipeline_ms).toFixed(0)}ms
                  </span>
                )}
              </div>
              <h2 className="font-headline text-2xl font-bold uppercase tracking-tight text-slate-900">
                {String(detail.event_title || "Simulation")}
              </h2>
              <p className="text-base text-slate-600 mt-2 leading-relaxed font-medium">
                {String(detail.event_description || "")}
              </p>
              <div className="flex items-center gap-4 mt-3 text-sm font-mono font-bold text-slate-400">
                <span>Detected: {detail.created_at ? new Date(String(detail.created_at)).toLocaleString() : "—"}</span>
                {detail.source_url && (
                  <a
                    href={String(detail.source_url)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1.5 text-red-500 hover:underline font-bold"
                  >
                    <ExternalLink size={12} /> Source
                  </a>
                )}
              </div>
            </div>

            <div className="grid grid-cols-4 gap-2">
              {[
                {
                  label: "Exposure",
                  value: `$${Number(detail.total_exposure_usd || 0).toLocaleString()}`,
                  icon: DollarSign,
                  color: "text-red-500",
                },

                {
                  label: "Stockout",
                  value: `${Number(detail.min_stockout_days || 0).toFixed(1)} days`,
                  icon: Clock,
                  color: Number(detail.min_stockout_days || 999) <= 5 ? "text-red-500" : "text-yellow-600",
                },
                {
                  label: "Praecantator Confidence",
                  value: `${(Number(detail.gnn_confidence || 0) * 100).toFixed(0)}%`,
                  icon: Shield,
                  color: "text-blue-600",
                },
              ].map((metric) => (
                <div key={metric.label} className="border border-slate-200 bg-white p-4 rounded shadow-sm">
                  <div className="flex items-center gap-2 mb-2">
                    <metric.icon size={12} className="text-slate-400" />
                    <span className="text-xs font-mono font-bold text-slate-400 uppercase tracking-widest">
                      {metric.label}
                    </span>
                  </div>
                  <div className={`text-xl font-bold font-headline tracking-wide ${metric.color}`}>
                    {metric.value}
                  </div>
                </div>
              ))}
            </div>

            {isNoImpactResult && (
              <div className="border border-slate-200 p-5 rounded bg-slate-50 shadow-inner">
                <p className="text-xs font-mono font-bold uppercase tracking-widest text-slate-400 mb-4">
                  Simulation Outcome
                </p>
                <div className="bg-white border border-slate-200 px-5 py-6 rounded text-center shadow-sm">
                  <p className="text-sm font-mono uppercase tracking-widest text-slate-400 font-bold">
                    Simulation Completed
                  </p>
                  <p className="text-sm text-slate-600 mt-3 leading-relaxed font-medium">
                    {String(
                      detail.recommendation_detail ||
                        "Selected intelligence signal does not intersect the current supplier graph.",
                    )}
                  </p>
                </div>
              </div>
            )}

            <div className="border border-slate-200 p-5 rounded bg-slate-50 shadow-inner">
              <p className="text-xs font-mono font-bold uppercase tracking-widest text-slate-400 mb-4">
                Affected Nodes · Praecantator-Scored
              </p>
              <div className="space-y-3 max-h-52 overflow-y-auto custom-scrollbar">
                {(detail.affected_nodes || []).map((node, i) => {
                  const score = Number(node.risk_score || 0);
                  return (
                    <div
                      key={`${node.id}-${i}`}
                      className="flex items-center gap-4 py-3 px-4 bg-white border border-slate-200 shadow-sm rounded"
                    >
                      <div
                        className="w-2.5 h-2.5 shrink-0 rounded-full"
                        style={{
                          backgroundColor: score >= 0.8 ? "#DC2626" : score >= 0.6 ? "#ea580c" : "#16a34a",
                          boxShadow: `0 0 6px ${score >= 0.8 ? "#DC2626" : score >= 0.6 ? "#ea580c" : "#16a34a"}`,
                        }}
                      />
                      <div className="flex-1 min-w-0">
                        <span className="text-sm text-slate-900 font-bold tracking-wide truncate block">
                          {String(node.name || "Node")}
                          {Boolean(node.single_source) && (
                            <span className="text-[10px] sm:text-xs ml-2 text-red-600 font-mono font-bold bg-red-50 border border-red-100 px-1.5 py-0.5 rounded shadow-sm uppercase tracking-wider">
                              Sole Source
                            </span>
                          )}
                        </span>
                        <span className="text-xs font-mono font-bold text-slate-500 mt-1 block">
                          Tier {Number(node.tier || 1)} · {String(node.country || "—")}
                          {Boolean(node.detail) && ` · ${String(node.detail)}`}
                        </span>
                      </div>
                      <div className="text-right shrink-0">
                        <div className="text-sm font-bold" style={{ color: score >= 0.8 ? "#DC2626" : score >= 0.6 ? "#ea580c" : "#16a34a" }}>
                          {(score * 100).toFixed(0)}%
                        </div>
                        <div className="text-xs font-mono font-bold text-slate-500 mt-1">
                          ${Number(node.exposure_usd || 0).toLocaleString()}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="border border-slate-200 p-5 rounded bg-slate-50 shadow-inner">
              <p className="text-xs font-mono font-bold uppercase tracking-widest text-slate-400 mb-4">
                Recommended Response
              </p>
              <div className="bg-red-50 border border-red-200 px-5 py-4 mb-4 rounded shadow-sm">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-red-600 text-xs font-mono font-bold uppercase tracking-wide">
                    ★ {String(detail.recommendation || "REVIEW")}
                  </span>
                </div>
                <p className="text-sm text-slate-700 leading-relaxed font-semibold mt-1 whitespace-pre-line">
                  {String(detail.recommendation_detail || "")}
                </p>
              </div>

              {detail.backup_supplier && (
                <div className="bg-emerald-50 border border-emerald-200 px-4 py-3 mb-4 rounded shadow-sm">
                  <div className="flex items-center gap-2 mb-2">
                    <Shield size={14} className="text-emerald-600" />
                    <span className="text-xs font-mono font-bold text-emerald-600 uppercase tracking-widest">
                      Backup Supplier
                    </span>
                  </div>
                  <div className="mt-2 text-sm font-bold text-slate-900 font-headline">
                    {String(detail.backup_supplier.name || "")}
                    <span className="text-emerald-600 font-mono text-xs ml-3 border-l border-emerald-200 pl-3">
                      {String(detail.backup_supplier.location || "")}
                      {detail.backup_supplier.lead_time_days && ` · ${detail.backup_supplier.lead_time_days}d lead`}
                    </span>
                  </div>
                </div>
              )}

              <div className="space-y-2">
                {(detail.route_options || []).map((route, i) => {
                  const ModeIcon = MODE_ICONS[String(route.mode)] || Truck;
                  const isRec = Boolean(route.recommended);
                  return (
                    <div
                      key={`${route.mode}-${i}`}
                      className={`flex items-center gap-4 px-4 py-3.5 rounded border transition-shadow ${
                        isRec ? "border-red-200 bg-red-50/50 shadow-sm" : "border-slate-200 bg-white"
                      }`}
                    >
                      <ModeIcon size={18} className={isRec ? "text-red-500" : "text-slate-400"} />
                      <div className="flex-1 min-w-0">
                        <span className={`text-sm font-bold block tracking-wide ${isRec ? "text-slate-900" : "text-slate-700"}`}>
                          {String(route.description || "")}
                        </span>
                      </div>
                      <div className="text-right shrink-0 space-y-1 mr-4">
                        {Number(route.transit_days || 0) > 0 && (
                          <div className="text-xs font-mono font-bold text-slate-500 flex items-center gap-1.5 justify-end">
                            <Clock size={12} className="text-slate-400" /> {Number(route.transit_days || 0).toFixed(1)}d
                          </div>
                        )}
                        {Number(route.cost_usd || 0) > 0 && (
                          <div className="text-xs font-mono font-bold text-slate-500 flex items-center gap-1.5 justify-end">
                            <DollarSign size={12} className="text-slate-400" /> ${Number(route.cost_usd || 0).toLocaleString()}
                          </div>
                        )}
                      </div>
                      <span className={`text-[10px] sm:text-xs font-mono font-bold uppercase px-2.5 py-1 rounded shrink-0 shadow-sm ${
                        isRec
                          ? "text-red-600 bg-red-100 border border-red-200"
                          : "text-blue-600 bg-blue-50 border border-blue-100"
                      }`}>
                        {String(isRec ? "REC" : route.status_label || "")}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>

            {detail.rfq_draft && (
              <div className="border border-slate-200 bg-white rounded shadow-sm overflow-hidden">
                <button
                  onClick={() => setRfqExpanded((open) => !open)}
                  className="w-full flex items-center justify-between px-4 py-3 hover:bg-slate-50 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <Send size={12} className="text-blue-500" />
                    <span className="text-xs font-mono font-bold uppercase tracking-widest text-slate-500">
                      Draft RFQ · AI AGENT
                    </span>
                  </div>
                  {rfqExpanded ? <ChevronUp size={14} className="text-slate-400" /> : <ChevronDown size={14} className="text-slate-400" />}
                </button>
                <AnimatePresence>
                  {rfqExpanded && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                      className="overflow-hidden"
                    >
                      <div className="px-5 pb-5 space-y-3 text-sm border-t border-slate-100 pt-4 bg-slate-50">
                        <div className="flex items-baseline">
                          <span className="text-slate-400 font-mono font-bold w-16">To:</span>
                          <span className="text-slate-900 font-bold">{String(detail.rfq_draft.to || "—")}</span>
                        </div>
                        <div className="flex items-baseline">
                          <span className="text-slate-400 font-mono font-bold w-16">Subject:</span>
                          <span className="text-slate-900 font-bold font-headline">{String(detail.rfq_draft.subject || "—")}</span>
                        </div>
                        <pre className="text-sm text-slate-700 bg-white border border-slate-200 p-4 rounded whitespace-pre-wrap font-mono leading-relaxed max-h-[400px] overflow-y-auto custom-scrollbar font-medium">
                          {String(detail.rfq_draft.body || "")}
                        </pre>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            )}

            <div className="border border-slate-200 p-5 rounded bg-slate-50 shadow-inner">
              <p className="text-xs font-mono font-bold uppercase tracking-widest text-slate-400 mb-4">
                Monte Carlo Summary
              </p>
              <div className="grid grid-cols-4 gap-2 mb-4">
                <div className="border border-slate-200 bg-white p-4 rounded shadow-sm">
                  <div className="text-xs font-mono font-bold text-slate-400 uppercase tracking-widest">Protected Runs</div>
                  <div className="text-xl font-bold font-headline text-emerald-600 mt-2">
                    {(Number(monteCarlo.protected_rate || 0) * 100).toFixed(0)}%
                  </div>
                </div>
                <div className="border border-slate-200 bg-white p-4 rounded shadow-sm">
                  <div className="text-xs font-mono font-bold text-slate-400 uppercase tracking-widest">Route Reliability</div>
                  <div className="text-xl font-bold font-headline text-blue-600 mt-2">
                    {(Number(monteCarlo.route_reliability || 0) * 100).toFixed(0)}%
                  </div>
                </div>
                <div className="border border-slate-200 bg-white p-4 rounded shadow-sm">
                  <div className="text-xs font-mono font-bold text-slate-400 uppercase tracking-widest">Loss Avoided</div>
                  <div className="text-xl font-bold font-headline text-orange-600 mt-2">
                    ${Number(monteCarlo.estimated_loss_avoided_usd || 0).toLocaleString()}
                  </div>
                </div>
                <div className="border border-slate-200 bg-white p-4 rounded shadow-sm">
                  <div className="text-xs font-mono font-bold text-slate-400 uppercase tracking-widest">Expected Delay</div>
                  <div className="text-xl font-bold font-headline text-yellow-600 mt-2">
                    {Number(monteCarlo.expected_delay_days || 0).toFixed(1)}d
                  </div>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div className="border border-slate-200 bg-white p-4 rounded shadow-sm">
                  <div className="text-xs font-mono font-bold text-slate-400 uppercase tracking-widest">Worst Case</div>
                  <div className="text-lg font-bold font-headline text-red-600 mt-2">
                    ${Number(monteCarlo.worst_case_loss_usd || 0).toLocaleString()}
                  </div>
                </div>
                <div className="border border-slate-200 bg-white p-4 rounded shadow-sm">
                  <div className="text-xs font-mono font-bold text-slate-400 uppercase tracking-widest">Confidence Band</div>
                  <div className="text-lg font-bold font-headline text-slate-900 mt-2">
                    {Number(monteCarlo.confidence_interval_low || 0).toFixed(0)}% - {Number(monteCarlo.confidence_interval_high || 0).toFixed(0)}%
                  </div>
                </div>
                <div className="border border-slate-200 bg-white p-4 rounded shadow-sm">
                  <div className="text-xs font-mono font-bold text-slate-400 uppercase tracking-widest">Runs</div>
                  <div className="text-lg font-bold font-headline text-slate-900 mt-2">
                    {Number(monteCarlo.runs || 0).toLocaleString()}
                  </div>
                </div>
              </div>
            </div>

            <ReasoningPanel workflowId={String(detail.id)} />
          </div>
        )}
      </div>
    </div>
  );
};

export default IncidentSimulator;
