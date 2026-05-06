import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, useEffect } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import {
  AlertTriangle, ChevronDown, ChevronUp, Clock, DollarSign, MapPin,
  Plane, Ship, Truck, Check, X, Edit, Send, Info,
  Shield, Zap, ExternalLink, CheckCircle, Circle, Loader2, FileText,
} from "lucide-react";
import { ReasoningPanel } from "@/components/workflow/ReasoningPanel";
import { CheckpointBanner } from "@/components/workflow/CheckpointBanner";
import { GovernanceFeedbackWidget } from "@/components/workflow/GovernanceFeedbackWidget";
import { motion, AnimatePresence } from "motion/react";

const BASE = (import.meta.env.VITE_API_URL ?? "/api").replace(/\/+$/, "");

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
  if (!res.ok) throw new Error(`${url} → ${res.status}`);
  return res.json();
}

const fetchIncidents = (status?: string) =>
  authFetch<unknown[]>(`${BASE}/incidents${status ? `?status=${status}` : ""}`);
interface AffectedNode {
  id: string;
  name: string;
  location: string;
  tier: number;
  risk_score: number;
  exposure_usd: number;
  safety_stock_days: number;
  stockout_days: number;
  mode?: string;
  single_source?: boolean;
  country?: string;
  detail?: string;
  lat?: number;
  lng?: number;
}

interface Incident {
  id: string;
  event_id: string;
  event_title: string;
  event_description: string;
  severity: string;
  status: string;
  affected_nodes: AffectedNode[];
  affected_node_count: number;
  total_exposure_usd: number;
  min_stockout_days: number;
  gnn_confidence: number;
  created_at: string;
  source_url?: string;
  pipeline_ms?: number;
  route_options: {
    mode: string;
    description: string;
    transit_days: number;
    cost_usd: number;
    recommended: boolean;
    status_label?: string;
  }[];
  recommendation: string;
  recommendation_detail: string;
  backup_supplier?: {
    name: string;
    location: string;
    lead_time_days: number;
    email: string;
  };
  rfq_draft?: {
    provider: string;
    to: string;
    subject: string;
    body: string;
    editable: boolean;
  };
  awb_reference?: string;
  execution_timeline?: {
    action: string;
    time: string;
    detail: string;
  }[];
  approved_by?: string;
  approved_at?: string;
  resolved_at?: string;
  dismiss_reason?: string;
  simulation_outcome?: string;
  simulation_only?: boolean;
}

const fetchIncident = (id: string) =>
  authFetch<Incident>(`${BASE}/incidents/${id}`);
const approveIncident = (id: string, action: string, reason = "") =>
  authFetch<any>(`${BASE}/incidents/${id}/approve`, {
    method: "POST",
    body: JSON.stringify({ action, reason }),
  });

const STATUS_COLORS: Record<string, string> = {
  AWAITING_APPROVAL: "text-red-600 bg-red-50 border border-red-100",
  ANALYZED: "text-blue-600 bg-blue-50 border border-blue-100",
  DETECTED: "text-yellow-600 bg-yellow-50 border border-yellow-100",
  APPROVED: "text-green-600 bg-green-50 border border-green-100",
  RESOLVED: "text-emerald-600 bg-emerald-50 border border-emerald-100",
  DISMISSED: "text-slate-400 bg-slate-100",
};

const SEVERITY: Record<string, { bg: string; text: string; icon: string }> = {
  CRITICAL: { bg: "bg-red-50 border-red-200", text: "text-red-600", icon: "★" },
  HIGH: { bg: "bg-orange-50 border-orange-200", text: "text-orange-600", icon: "◉" },
  MODERATE: { bg: "bg-yellow-50 border-yellow-200", text: "text-yellow-600", icon: "◎" },
  LOW: { bg: "bg-green-50 border-green-200", text: "text-green-600", icon: "○" },
};

const MODE_ICONS: Record<string, React.ElementType> = { air: Plane, sea: Ship, land: Truck };

const Incidents = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedId = searchParams.get("id");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [rfqExpanded, setRfqExpanded] = useState(false);
  const [approveLoading, setApproveLoading] = useState(false);
  const [executionResult, setExecutionResult] = useState<Record<string, unknown> | null>(null);
  const qc = useQueryClient();
  const navigate = useNavigate();

  const { data: incidentsRaw = [] } = useQuery({
    queryKey: ["incidents", statusFilter],
    queryFn: () => fetchIncidents(statusFilter || undefined),
    refetchInterval: 15_000,
  });
  const incidents: Record<string, unknown>[] = Array.isArray(incidentsRaw) ? incidentsRaw as Record<string, unknown>[] : [];

  const { data: detail, refetch: refetchDetail } = useQuery<Incident>({
    queryKey: ["incident", selectedId],
    queryFn: () => authFetch<Incident>(`${BASE}/incidents/${selectedId}`),
    enabled: !!selectedId,
  });

  const action = useMutation({
    mutationFn: async (vars: { id: string; action: string; reason?: string }) => {
      if (vars.action === "approve") setApproveLoading(true);
      const result = await approveIncident(vars.id, vars.action, vars.reason);
      return result;
    },
    onSuccess: (data) => {
      if (data?.execution_timeline) {
        setExecutionResult(data);
      }
      setApproveLoading(false);
      qc.invalidateQueries({ queryKey: ["incidents"] });
      qc.invalidateQueries({ queryKey: ["incident", selectedId] });
      qc.invalidateQueries({ queryKey: ["command"] });
      setTimeout(() => refetchDetail(), 500);
    },
    onError: (err: any) => {
      setApproveLoading(false);
      const detail = err.message || "Failed to approve decision.";
      alert(`Approval Failed: ${detail}`);
    },
  });

  useEffect(() => {
    setExecutionResult(null);
    setRfqExpanded(false);
  }, [selectedId]);

  useEffect(() => {
    if (!selectedId && incidents.length > 0) {
      setSearchParams({ id: String(incidents[0].id) });
    }
  }, [incidents, selectedId, setSearchParams]);

  const statuses = ["", "AWAITING_APPROVAL", "ANALYZED", "APPROVED", "RESOLVED", "DISMISSED"];
  const canExecuteIncident =
    detail?.status === "AWAITING_APPROVAL" &&
    String(detail?.simulation_outcome || "").toLowerCase() !== "no_impact" &&
    !Boolean(detail?.simulation_only && Number(detail?.affected_node_count || 0) === 0);

  return (
    <div className="h-[calc(100vh-120px)] flex gap-0 min-h-0">
      <div className="w-[360px] shrink-0 border border-slate-200 bg-white flex flex-col min-h-0 shadow-sm">
        <div className="px-5 py-4 border-b border-slate-200 shrink-0 bg-white">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle size={16} className="text-red-500" />
            <span className="text-xs font-mono font-bold uppercase tracking-widest text-slate-500">
              Crisis Center · {incidents.length}
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

        <div className="flex-1 overflow-y-auto custom-scrollbar divide-y divide-slate-200/60">
          {incidents.length === 0 && (
            <div className="p-8 text-center text-slate-400 text-sm font-mono font-medium">
              No active incidents found.
            </div>
          )}

          {incidents.map((incident: any) => {
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
                    {String(incident.event_title || "Disruption")}
                  </span>
                  <span className="text-[10px] sm:text-xs font-mono font-bold text-slate-400">
                    {new Date(String(incident.created_at)).toLocaleDateString()}
                  </span>
                </div>
                <div className="flex items-center gap-4 text-xs font-mono font-bold text-slate-400 pl-[26px]">
                  <span className="text-red-500">{Number(incident.affected_node_count || 0)} nodes</span>
                  <span>${Number(incident.total_exposure_usd || 0).toLocaleString()}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="flex-1 border border-l-0 border-slate-200 bg-white flex flex-col min-h-0 overflow-y-auto custom-scrollbar shadow-inner">
        {!selectedId ? (
          <div className="flex-1 flex items-center justify-center text-slate-400 font-mono text-sm font-bold">
            Select an incident to review orchestration logic.
          </div>
        ) : !detail ? (
          <div className="flex-1 flex items-center justify-center text-slate-400 font-mono text-sm font-bold uppercase tracking-widest">
            Fetching incident detail...
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
                {String(detail.event_title || "Disruption")}
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

                {(() => {
                  // ── Country centroid fallback (used when nodes have no / same coords) ──
                  const COUNTRY_CENTROIDS: Record<string, [number, number]> = {
                    IN: [20.59, 78.96], CN: [35.86, 104.19], US: [37.09, -95.71], DE: [51.16, 10.45],
                    GB: [55.37, -3.43], JP: [36.20, 138.25], KR: [35.90, 127.86], SG: [1.35, 103.82],
                    AE: [23.42, 53.84], SA: [23.88, 45.08], AU: [-25.27, 133.77], BR: [-14.23, -51.92],
                    FR: [46.22, 2.21], NL: [52.13, 5.29], MX: [23.63, -102.55], VN: [14.05, 108.27],
                    TH: [15.87, 100.99], MY: [4.21, 101.97], ID: [-0.79, 113.92], PH: [12.88, 121.77],
                    PK: [30.37, 69.34], BD: [23.68, 90.35], TW: [23.69, 120.96], HK: [22.39, 114.11],
                    ZA: [-30.56, 22.93], NG: [9.08, 8.67], EG: [26.82, 30.80], TR: [38.96, 35.24],
                    PL: [51.92, 19.14], IT: [41.87, 12.56], ES: [40.46, -3.74], CA: [56.13, -106.35],
                    RU: [61.52, 105.31], UA: [48.37, 31.16], IL: [31.04, 34.85], MA: [31.79, -7.09],
                  };

                  // ── Derive real origin from affected nodes ─────────────────
                  const nodes = detail?.affected_nodes || [];

                  // Origin: first affected node with valid lat/lng
                  const originNode = nodes.find(n => n.lat != null && n.lng != null && (n.lat !== 0 || n.lng !== 0)) || nodes[0];
                  let originLat = originNode?.lat ?? 0;
                  let originLng = originNode?.lng ?? 0;
                  const originLabel = originNode?.name || originNode?.country || "Origin";

                  // If origin has no coords, use country centroid
                  if (!originLat && !originLng && originNode?.country) {
                    const cc = COUNTRY_CENTROIDS[String(originNode.country).toUpperCase().slice(0, 2)];
                    if (cc) { originLat = cc[0]; originLng = cc[1]; }
                  }

                  // Destination: backup_supplier coords if present, else highest-exposure node that differs from origin
                  let destLat = 0, destLng = 0, destLabel = "Destination";
                  if (detail.backup_supplier) {
                    if ((detail.backup_supplier as any).lat != null) {
                      destLat = Number((detail.backup_supplier as any).lat);
                      destLng = Number((detail.backup_supplier as any).lng);
                    }
                    destLabel = detail.backup_supplier.name || detail.backup_supplier.location || "Backup Supplier";
                    // If backup supplier has no coords, try its location as country code
                    if (!destLat && !destLng) {
                      const loc = String(detail.backup_supplier.location || "").trim().toUpperCase().slice(0, 2);
                      const cc = COUNTRY_CENTROIDS[loc];
                      if (cc) { destLat = cc[0]; destLng = cc[1]; }
                    }
                  } else {
                    // Pick the node with highest exposure that is geographically different from origin
                    const sorted = [...nodes]
                      .filter(n => n.lat != null && n.lng != null)
                      .sort((a, b) => Number(b.exposure_usd || 0) - Number(a.exposure_usd || 0));
                    const destNode = sorted.find(n => n.id !== originNode?.id) || sorted[1] || null;
                    if (destNode) {
                      destLat = destNode.lat ?? 0;
                      destLng = destNode.lng ?? 0;
                      destLabel = destNode.name || destNode.country || "Destination";
                    }
                  }

                  // If dest still has no coords, fall back to a different country centroid
                  if (!destLat && !destLng) {
                    // Use the country of the backup_supplier or the second affected node's country
                    const fallbackCountry = (detail.backup_supplier?.location || nodes[1]?.country || "SG")
                      .toString().trim().toUpperCase().slice(0, 2);
                    const cc = COUNTRY_CENTROIDS[fallbackCountry] || COUNTRY_CENTROIDS["SG"]!;
                    destLat = cc[0]; destLng = cc[1];
                  }

                  // ── Haversine from real coordinates ──────────────────────
                  function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
                    if (lat1 === lat2 && lon1 === lon2) return 0;
                    const R = 6371, r = Math.PI / 180;
                    const dLat = (lat2 - lat1) * r, dLon = (lon2 - lon1) * r;
                    const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * r) * Math.cos(lat2 * r) * Math.sin(dLon / 2) ** 2;
                    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
                  }

                  let dist = haversineKm(originLat, originLng, destLat, destLng);

                  // If same coords (nodes are co-located), synthesise a plausible intra-country distance
                  if (dist < 1) {
                    // Pick a different centroid as destination — nearest major hub
                    const altOrder = ["SG", "AE", "NL", "US", "JP", "DE", "AU"];
                    const originCC = String(originNode?.country || "").toUpperCase().slice(0, 2);
                    const altKey = altOrder.find(k => k !== originCC) || "SG";
                    const alt = COUNTRY_CENTROIDS[altKey]!;
                    destLat = alt[0]; destLng = alt[1]; destLabel = altKey + " Hub";
                    dist = haversineKm(originLat, originLng, destLat, destLng);
                  }

                  // Speed / cost constants (industry averages)
                  const AIR_KMH = 800, AIR_USD_PER_KM = 0.95;
                  const LAND_KMH = 80, LAND_USD_PER_KM = 0.18;
                  const SEA_KMH = 35, SEA_USD_PER_KM = 0.05;
                  const LAND_MAX_KM = 3000; // viability cap

                  const airDist = dist, airDays = dist > 0 ? (dist / AIR_KMH) / 24 : 0, airCost = dist * AIR_USD_PER_KM;
                  const landDist = dist, landDays = dist > 0 ? (dist / LAND_KMH) / 24 : 0, landCost = dist * LAND_USD_PER_KM;
                  const seaDist = dist * 1.25, seaDays = dist > 0 ? (seaDist / SEA_KMH) / 24 : 0, seaCost = seaDist * SEA_USD_PER_KM;

                  const fmtDist = Math.round(dist).toLocaleString();

                  // Patch the recommendation_detail text that backend emits with "0km" placeholders
                  let finalRecDetail = String(detail.recommendation_detail || "")
                    .replace(/0km direct/gi, `${fmtDist} km direct`)
                    .replace(/\b0\s*km\b/gi, `${fmtDist} km`)
                    .replace(/\$0\/tonne/gi, airCost > 0 ? `$${Math.round(airCost).toLocaleString()}/tonne` : "Cost TBD")
                    .replace(/GNN confidence/gi, "Praecantator confidence");

                  // Build RouteViewer URL with real lat/lng so the map renders the correct path
                  function openRouteViewer(mode: string, days: number, cost: number) {
                    const params = new URLSearchParams({
                      mode,
                      fromLat: String(originLat), fromLng: String(originLng), fromLabel: originLabel,
                      toLat: String(destLat), toLng: String(destLng), toLabel: destLabel,
                      cost: String(Math.round(cost)),
                      days: String(days.toFixed(1)),
                      incident: String(detail?.event_title || ""),
                    });
                    navigate(`/dashboard/route-viewer?${params.toString()}`);
                  }

                  return (
                    <>
                      {/* ── Route header showing real origin → destination ── */}
                      {dist > 0 && (
                        <div className="flex items-center gap-2 mb-4 text-xs font-mono text-slate-500 bg-white border border-slate-200 rounded px-3 py-2 shadow-sm">
                          <MapPin size={11} className="text-red-400 shrink-0" />
                          <span className="truncate font-bold text-slate-700">{originLabel}</span>
                          <span className="text-slate-300 shrink-0">→</span>
                          <span className="truncate font-bold text-slate-700">{destLabel}</span>
                          <span className="ml-auto shrink-0 font-bold text-slate-400">{Math.round(dist).toLocaleString()} km</span>
                        </div>
                      )}

                      <div className="bg-red-50 border border-red-200 px-5 py-4 mb-4 rounded shadow-sm">
                        <div className="flex items-center gap-2 mb-2">
                          <span className="text-red-600 text-xs font-mono font-bold uppercase tracking-wide">
                            ★ {String(detail.recommendation || "REVIEW")}
                          </span>
                        </div>
                        <p className="text-sm text-slate-700 leading-relaxed font-semibold mt-1 whitespace-pre-line">
                          {finalRecDetail}
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
                            </span>
                          </div>
                        </div>
                      )}

                      <div className="space-y-2">
                        {(detail.route_options || []).map((route, i) => {
                          const ModeIcon = MODE_ICONS[String(route.mode)] || Truck;
                          const isRec = Boolean(route.recommended);
                          const mode = String(route.mode);

                          // Derive distance/days/cost from real coordinates, fallback to backend values
                          let routeDist = 0, routeDays = 0, routeCost = 0;
                          if (mode === "air")  { routeDist = airDist;  routeDays = airDays;  routeCost = airCost;  }
                          if (mode === "land") { routeDist = landDist; routeDays = landDays; routeCost = landCost; }
                          if (mode === "sea")  { routeDist = seaDist;  routeDays = seaDays;  routeCost = seaCost;  }

                          // If backend already has non-zero values, prefer them
                          if (Number(route.transit_days) > 0) routeDays = Number(route.transit_days);
                          if (Number(route.cost_usd) > 0)     routeCost = Number(route.cost_usd);

                          const isViable = mode !== "land" || routeDist <= LAND_MAX_KM;
                          const routeFmtDist = Math.round(routeDist).toLocaleString();
                          // Always replace 0km placeholders with real computed distance
                          const finalDesc = isViable
                            ? String(route.description || "")
                                .replace(/0km direct/gi, `${routeFmtDist} km direct`)
                                .replace(/\b0\s*km\b/gi, `${routeFmtDist} km`)
                                .replace(/\btbd\s*km\b/gi, `${routeFmtDist} km`)
                            : "Not viable — no road/rail corridor between origin and destination";

                          return (
                            <div
                              key={`${mode}-${i}`}
                              onClick={isViable ? () => openRouteViewer(mode, routeDays, routeCost) : undefined}
                              className={`flex items-center gap-4 px-4 py-3.5 rounded border transition-all ${
                                isRec ? "border-red-200 bg-red-50/50 shadow-sm" : "border-slate-200 bg-white"
                              } ${isViable ? "cursor-pointer hover:shadow-md hover:border-slate-300 active:scale-[0.99]" : "opacity-60"}`}
                            >
                              <ModeIcon size={18} className={isRec ? "text-red-500" : "text-slate-400"} />
                              <div className="flex-1 min-w-0">
                                <span className={`text-sm font-bold block tracking-wide ${isRec ? "text-slate-900" : "text-slate-700"}`}>
                                  {isViable ? finalDesc : <span className="text-slate-400">{finalDesc}</span>}
                                </span>
                                {isViable && (
                                  <span className="text-[10px] font-mono text-slate-400 mt-0.5 block">
                                    Click to view route map
                                  </span>
                                )}
                              </div>
                              <div className="text-right shrink-0 space-y-1 mr-4">
                                {isViable && routeDays > 0 && (
                                  <div className="text-xs font-mono font-bold text-slate-500 flex items-center gap-1.5 justify-end">
                                    <Clock size={12} className="text-slate-400" /> {routeDays.toFixed(1)}d
                                  </div>
                                )}
                                {isViable && routeCost > 0 && (
                                  <div className="text-xs font-mono font-bold text-slate-500 flex items-center gap-1.5 justify-end">
                                    <DollarSign size={12} className="text-slate-400" /> ${Math.round(routeCost).toLocaleString()}
                                  </div>
                                )}
                              </div>
                              <span className={`text-[10px] sm:text-xs font-mono font-bold uppercase px-2.5 py-1 rounded shrink-0 shadow-sm ${
                                isRec
                                  ? "text-red-600 bg-red-100 border border-red-200"
                                  : isViable
                                    ? "text-blue-600 bg-blue-50 border border-blue-100"
                                    : "text-slate-400 bg-slate-100 border border-slate-200"
                              }`}>
                                {isRec ? "REC" : isViable ? (route.status_label || mode.toUpperCase()) : "N/A"}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    </>
                  );
                })()}
      </div>

            {detail.rfq_draft && (
              <div className="border border-slate-200 bg-white rounded shadow-sm overflow-hidden mb-4">
                <div className="w-full flex items-center justify-between px-4 py-3 bg-slate-50 border-b border-slate-100">
                  <div className="flex items-center gap-2">
                    <Send size={12} className="text-blue-500" />
                    <span className="text-xs font-mono font-bold uppercase tracking-widest text-slate-500">
                      Draft RFQ · AI AGENT
                    </span>
                  </div>
                </div>
                <div className="px-5 pb-5 space-y-3 text-sm bg-slate-50 pt-4">
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
                        <div className="flex justify-end gap-3 pt-2">
                          <button
                            type="button"
                            className="px-4 py-2 bg-white border border-slate-200 text-slate-600 hover:text-slate-900 font-mono text-xs uppercase tracking-widest transition-colors rounded shadow-sm font-bold"
                          >
                            Edit Case
                          </button>
                          <button
                            type="button"
                            className="px-4 py-2 bg-red-500 text-white hover:bg-red-600 font-mono text-xs uppercase tracking-widest transition-colors rounded shadow-sm font-bold"
                          >
                            Send RFQ
                          </button>
                        </div>
                </div>
              </div>
            )}

            <CheckpointBanner incidentId={String(detail.id)} />
            <ReasoningPanel workflowId={String(detail.id)} />
            {/* ── Execution Timeline (shows after approval) ── */}
            {(((executionResult?.execution_timeline || detail.execution_timeline || []) as any[]).length > 0) && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="border border-emerald-500/30 bg-emerald-500/5 p-4"
              >
                <div className="flex items-center gap-3 mb-4">
                  <CheckCircle size={16} className="text-emerald-500" />
                  <span className="text-xs font-mono font-bold uppercase tracking-widest text-emerald-400">
                    Execution Complete
                  </span>
                  {(executionResult?.awb_reference || detail.awb_reference) && (
                    <span className="ml-auto text-xs font-mono font-bold text-emerald-400 bg-emerald-500/10 px-2.5 py-1 rounded">
                      {String(executionResult?.awb_reference || detail.awb_reference)}
                    </span>
                  )}
                </div>
                <div className="space-y-0">
                  {(((executionResult?.execution_timeline || detail.execution_timeline || []) as any[])).map(
                    (step: any, i: number) => (
                      <motion.div
                        key={i}
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: i * 0.15 }}
                        className="flex items-start gap-3 py-2"
                      >
                        <div className="flex flex-col items-center mt-0.5">
                           <CheckCircle size={12} className="text-emerald-500" />
                           {i < ((executionResult?.execution_timeline || detail.execution_timeline || []) as any[]).length - 1 && (
                             <div className="w-px h-full min-h-[16px] bg-emerald-500/30 mt-1" />
                           )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-3">
                            <span className="text-sm font-bold text-gray-100">
                              {String(step.action || "")}
                            </span>
                            <span className="text-xs font-mono text-emerald-400 font-bold">
                              {String(step.time || "")}
                            </span>
                          </div>
                          <p className="text-sm text-gray-300 mt-1 leading-relaxed">
                            {String(step.detail || "")}
                          </p>
                        </div>
                      </motion.div>
                    )
                  )}
                </div>
              </motion.div>
            )}

            {/* ── Post-status banners ── */}
            {detail.status === "RESOLVED" && !executionResult && !(detail.execution_timeline && detail.execution_timeline.length > 0) && (
              <div className="bg-emerald-500/10 border border-emerald-500/30 px-5 py-4 rounded">
                <p className="text-emerald-400 text-sm font-mono font-semibold flex items-center gap-2">
                  <CheckCircle size={16} />
                  Resolved by {String(detail.approved_by || "system")} at{" "}
                  {detail.resolved_at ? new Date(String(detail.resolved_at)).toLocaleString() : "—"}
                </p>
              </div>
            )}

            {detail.status === "APPROVED" && (
              <div className="bg-green-500/10 border border-green-500/30 px-5 py-4 rounded">
                <p className="text-green-400 text-sm font-mono font-semibold flex items-center gap-2">
                  <Check size={16} />
                  Approved by {String(detail.approved_by || "user")} at{" "}
                  {detail.approved_at ? new Date(String(detail.approved_at)).toLocaleString() : "—"}
                </p>
              </div>
            )}

            {detail.status === "DISMISSED" && (
              <div className="bg-surface-high border border-border/50 px-5 py-4 rounded">
                <p className="text-gray-400 text-sm font-mono font-semibold text-center">
                  Dismissed: {String(detail.dismiss_reason || "No reason given")}
                </p>
              </div>
            )}

            {/* ── Governance Feedback Loop ── */}
            <GovernanceFeedbackWidget
              incidentId={String(detail.id)}
              status={String(detail.status)}
            />

            {/* ── Action Buttons ── */}
            {canExecuteIncident && (
              <div className="flex items-center gap-3 pt-6 pb-4 border-t border-slate-200 mt-6">
                <button
                  onClick={() => action.mutate({ id: String(detail.id), action: "approve" })}
                  disabled={action.isPending || approveLoading}
                  className="flex items-center gap-2 px-5 py-2.5 bg-green-600 hover:bg-green-700 text-white font-mono text-xs uppercase tracking-widest transition-all disabled:opacity-50 rounded shadow-sm"
                >
                  {approveLoading ? (
                    <>
                      <Loader2 size={14} className="animate-spin" />
                      Executing...
                    </>
                  ) : (
                    <>
                      <Check size={14} />
                      Approve & Execute
                    </>
                  )}
                </button>
                <button
                  onClick={() => action.mutate({ id: String(detail.id), action: "override", reason: "Manual override" })}
                  disabled={action.isPending}
                  className="flex items-center gap-2 px-5 py-2.5 border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 font-mono text-xs uppercase tracking-widest transition-colors rounded shadow-sm font-bold"
                >
                  <Edit size={14} />
                  Override
                </button>
                <button
                  onClick={() => {
                    const reason = prompt("Reason for dismissal:");
                    if (reason) action.mutate({ id: String(detail.id), action: "dismiss", reason });
                  }}
                  disabled={action.isPending}
                  className="flex items-center gap-2 px-5 py-2.5 border border-slate-200 bg-white hover:bg-slate-50 text-slate-400 font-mono text-xs uppercase tracking-widest font-bold transition-colors rounded shadow-sm"
                >
                  <X size={14} />
                  Dismiss
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default Incidents;
