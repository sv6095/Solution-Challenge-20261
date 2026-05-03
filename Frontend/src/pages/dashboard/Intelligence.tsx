import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, useMemo, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  Radar, Globe, RefreshCw, ExternalLink, Filter,
  AlertTriangle, Clock, MapPin, Signal, DollarSign, Shield, Zap, Loader2, FlaskConical,
  Plane, Ship, Truck, CheckCircle,
} from "lucide-react";
import { Heatmap } from "@/mapcn/heatmap";
import { transformEventsToHeatmap } from "@/lib/risk-heatmap";
import { api } from "@/lib/api";
import { ReasoningPanel } from "@/components/workflow/ReasoningPanel";
import { CheckpointBanner } from "@/components/workflow/CheckpointBanner";
import type { IntelligenceGapItem, RiskEvent } from "@/lib/api";

type ViewMode = "feed" | "map";

type FeedSignal = Record<string, unknown> & {
  _category?: string;
};

type IncidentDetail = {
  id: string;
  event_title: string;
  event_description: string;
  severity: string;
  status: string;
  affected_nodes: Array<Record<string, unknown>>;
  affected_node_count: number;
  total_exposure_usd: number;
  min_stockout_days: number;
  gnn_confidence: number;
  route_options: Array<Record<string, unknown>>;
  recommendation: string;
  recommendation_detail: string;
  source_url?: string;
  backup_supplier?: Record<string, unknown>;
  value_at_risk_usd?: number;
  scenario_confidence?: Record<string, unknown>;
};

const SEVERITY: Record<string, { bg: string; text: string; icon: string }> = {
  CRITICAL: { bg: "bg-red-50 border-red-200", text: "text-red-600", icon: "★" },
  HIGH: { bg: "bg-orange-50 border-orange-200", text: "text-orange-600", icon: "◉" },
  MODERATE: { bg: "bg-yellow-50 border-yellow-200", text: "text-yellow-600", icon: "◎" },
  LOW: { bg: "bg-green-50 border-green-200", text: "text-green-600", icon: "○" },
};

const MODE_ICONS: Record<string, React.ElementType> = { air: Plane, sea: Ship, land: Truck };

const Intelligence = () => {
  const [view, setView] = useState<ViewMode>("feed");
  const [typeFilter, setTypeFilter] = useState("");
  const [selectedSignalId, setSelectedSignalId] = useState("");
  const qc = useQueryClient();
  const navigate = useNavigate();

  const { data: categorized = {} } = useQuery({
    queryKey: ["signals", "categorized"],
    queryFn: api.signals.categorized,
    refetchInterval: 60_000,
  });
  const { data: events = [] } = useQuery<RiskEvent[]>({
    queryKey: ["risks", "events"],
    queryFn: () => api.risks.events(),
    refetchInterval: 60_000,
  });
  const refresh = useMutation({
    mutationFn: api.signals.refresh,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["signals"] }),
  });
  const monteCarlo = useMutation({
    mutationFn: (signal: FeedSignal) => api.intelligence.monteCarlo({ signal, runs: 300 }),
    onSuccess: async (result) => {
      await qc.invalidateQueries({ queryKey: ["incidents"] });
      await qc.invalidateQueries({ queryKey: ["intelligence", "simulation-incidents"] });
      const incidentId = String(result?.incident?.id || "");
      if (incidentId) {
        navigate(`/dashboard/incident-simulator?id=${encodeURIComponent(incidentId)}`);
      }
    },
  });

  // Flatten categorized signals into a single list
  const allSignals = useMemo<FeedSignal[]>(() => {
    const out: FeedSignal[] = [];
    if (categorized && typeof categorized === "object") {
      for (const [category, items] of Object.entries(categorized)) {
        if (Array.isArray(items)) {
          for (const item of items) {
            out.push({ ...(item as Record<string, unknown>), _category: category });
          }
        }
      }
    }
    return out.sort((left, right) => {
      const leftTime = Date.parse(String(left.time || left.published_at || left.detected_at || 0));
      const rightTime = Date.parse(String(right.time || right.published_at || right.detected_at || 0));
      return rightTime - leftTime;
    });
  }, [categorized]);

  const filteredSignals = useMemo(() => {
    if (!typeFilter) return allSignals;
    return allSignals.filter((s) => String(s._category || "").toLowerCase().includes(typeFilter.toLowerCase()));
  }, [allSignals, typeFilter]);
  const selectedSignal = useMemo(
    () => filteredSignals.find((signal) => String(signal.id || signal.signal_id || "") === selectedSignalId) ?? filteredSignals[0] ?? null,
    [filteredSignals, selectedSignalId],
  );

  const heatmapPoints = useMemo(() => transformEventsToHeatmap(events), [events]);
  const categories = useMemo(() => {
    return Object.keys(categorized || {}).filter((k) => {
      const items = (categorized as Record<string, unknown>)[k];
      return Array.isArray(items) && items.length > 0;
    });
  }, [categorized]);
  const simulationIncident = (monteCarlo.data?.incident ?? null) as IncidentDetail | null;
  const simulation = (monteCarlo.data?.simulation ?? null) as Record<string, unknown> | null;
  const dataQuality = (monteCarlo.data?.data_quality ?? null) as Record<string, unknown> | null;
  const noImpactReason = monteCarlo.data?.status === "no_impact" ? String(monteCarlo.data?.reason || "No supplier impact detected for this signal.") : null;
  const monteCarloError = monteCarlo.error instanceof Error ? monteCarlo.error.message : null;
  const selectedSignalKey = String(selectedSignal?.id || selectedSignal?.signal_id || "");
  const selectedSignalHasGeo = Boolean(
    selectedSignal && (Number(selectedSignal.lat || 0) !== 0 || Number(selectedSignal.lng || 0) !== 0),
  );

  useEffect(() => {
    if (!selectedSignalId && filteredSignals.length > 0) {
      setSelectedSignalId(String(filteredSignals[0].id || filteredSignals[0].signal_id || ""));
    }
  }, [filteredSignals, selectedSignalId]);

  useEffect(() => {
    monteCarlo.reset();
  }, [selectedSignalKey]);

  return (
    <div className="h-[calc(100vh-120px)] flex flex-col min-h-0">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-slate-200 bg-white shrink-0 mb-0 shadow-sm">
        <div className="flex items-center gap-3">
          <Radar size={16} className="text-red-500" />
          <span className="text-xs font-mono uppercase tracking-widest text-slate-500 font-bold">
            Intelligence · {allSignals.length} signals
          </span>
          {/* View toggle */}
          <div className="flex items-center gap-2 ml-4">
            <button
              onClick={() => setView("feed")}
              className={`px-4 py-1.5 text-xs font-mono uppercase font-bold tracking-widest transition-colors rounded ${
                view === "feed" ? "bg-red-50 text-red-600 border border-red-200" : "text-slate-500 hover:text-slate-900 hover:bg-slate-100"
              }`}
            >
              <Signal size={14} className="inline mr-2" /> Feed
            </button>
            <button
              onClick={() => setView("map")}
              className={`px-4 py-1.5 text-xs font-mono uppercase font-bold tracking-widest transition-colors rounded ${
                view === "map" ? "bg-red-50 text-red-600 border border-red-200" : "text-slate-500 hover:text-slate-900 hover:bg-slate-100"
              }`}
            >
              <Globe size={14} className="inline mr-2" /> Map
            </button>
          </div>
        </div>
        <button
          onClick={() => refresh.mutate()}
          disabled={refresh.isPending}
          className="flex items-center gap-2 text-xs font-mono uppercase font-bold tracking-widest px-4 py-1.5 bg-slate-50 text-slate-600 hover:text-slate-900 border border-slate-200 transition-colors rounded shadow-sm hover:bg-slate-100"
        >
          <RefreshCw size={14} className={refresh.isPending ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0 border border-t-0 border-slate-200 bg-white">
        {view === "feed" ? (
          <div className="h-full flex">
            {/* Category sidebar */}
            <div className="w-56 shrink-0 border-r border-slate-200/60 overflow-y-auto custom-scrollbar">
              <div className="px-4 py-3 border-b border-slate-200/60">
                <span className="text-[10px] sm:text-xs font-mono uppercase tracking-widest text-slate-400 font-bold">Categories</span>
              </div>
              <button
                onClick={() => setTypeFilter("")}
                className={`w-full text-left px-4 py-3 text-xs font-mono uppercase font-bold tracking-wide transition-colors ${
                  !typeFilter ? "bg-red-50 text-red-600 border-r-2 border-red-500" : "text-slate-500 hover:text-slate-900 hover:bg-slate-50"
                }`}
              >
                All ({allSignals.length})
              </button>
              {categories.map((cat) => {
                const count = Array.isArray((categorized as Record<string, unknown[]>)[cat])
                  ? (categorized as Record<string, unknown[]>)[cat].length
                  : 0;
                return (
                  <button
                    key={cat}
                    onClick={() => setTypeFilter(cat)}
                    className={`w-full text-left px-4 py-3 text-xs font-mono uppercase font-bold tracking-wide transition-colors ${
                      typeFilter === cat ? "bg-red-50 text-red-600 border-r-2 border-red-500" : "text-slate-500 hover:text-slate-900 hover:bg-slate-50"
                    }`}
                  >
                    {cat} ({count})
                  </button>
                );
              })}
            </div>

            {/* Signal list */}
            <div className="w-[420px] shrink-0 border-r border-slate-200/60 overflow-y-auto custom-scrollbar divide-y divide-slate-200/60">
              {filteredSignals.length === 0 && (
                <div className="p-8 text-center text-slate-400 font-mono text-sm font-medium">
                  No signals. Click Refresh to scan sources.
                </div>
              )}
              {filteredSignals.map((sig, i) => (
                <button
                  type="button"
                  key={i}
                  onClick={() => setSelectedSignalId(String(sig.id || sig.signal_id || ""))}
                  className={`w-full text-left px-5 py-5 transition-colors border-l-[3px] ${
                    selectedSignalKey === String(sig.id || sig.signal_id || "")
                      ? "bg-slate-50 border-l-red-500"
                      : "hover:bg-slate-50 border-l-transparent"
                  }`}
                >
                  <div className="flex items-start gap-4">
                    <div className="mt-1">
                      <AlertTriangle
                        size={16}
                        className={
                          String(sig.severity || "").toUpperCase() === "CRITICAL"
                            ? "text-red-500"
                            : String(sig.severity || "").toUpperCase() === "HIGH"
                            ? "text-orange-500"
                            : "text-yellow-500"
                        }
                      />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-3 mb-2">
                        <span className="text-[10px] sm:text-xs font-mono font-bold text-slate-500 uppercase tracking-widest bg-slate-50 px-2 py-1 rounded shadow-sm border border-slate-200">
                          {String(sig._category || sig.source || "—")}
                        </span>
                        <span className="text-[10px] sm:text-xs font-mono font-bold text-slate-500 uppercase tracking-widest">
                          {String(sig.source || "")}
                        </span>
                      </div>
                      <p className="text-sm sm:text-base text-slate-900 font-bold tracking-wide">
                        {String(sig.title || "Signal")}
                      </p>
                      <p className="text-sm text-slate-600 font-medium leading-relaxed line-clamp-2 mt-1">
                        {String(sig.description || sig.event_type || "")}
                      </p>
                      <div className="flex items-center gap-5 mt-3 text-xs font-mono text-slate-400 font-bold">
                        {Boolean(sig.location) && (
                          <span className="flex items-center gap-1.5">
                            <MapPin size={12} /> {String(sig.location)}
                          </span>
                        )}
                        {Boolean(sig.time || sig.published_at || sig.detected_at) && (
                          <span className="flex items-center gap-1.5">
                            <Clock size={12} /> {new Date(String(sig.time || sig.published_at || sig.detected_at)).toLocaleDateString()}
                          </span>
                        )}
                        {Boolean(sig.url) && (
                          <span className="flex items-center gap-1.5 text-blue-600">
                            <ExternalLink size={12} /> Source
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </button>
              ))}
            </div>

            {/* Incidents-style detail pane */}
            <div className="flex-1 bg-white flex flex-col min-h-0 overflow-y-auto custom-scrollbar">
              {!selectedSignal ? (
                <div className="flex-1 flex items-center justify-center text-slate-400 font-mono text-sm">
                  Select an intelligence signal to inspect
                </div>
              ) : (
                <div className="p-5 space-y-4">

                  <div>
                    <div className="flex items-center gap-3 mb-3">
                      <span className={`text-xs font-mono font-bold uppercase tracking-widest px-2.5 py-1 rounded border ${
                        (SEVERITY[String((simulationIncident?.severity || selectedSignal.severity || "LOW")).toUpperCase()] || SEVERITY.LOW).bg
                      } ${
                        (SEVERITY[String((simulationIncident?.severity || selectedSignal.severity || "LOW")).toUpperCase()] || SEVERITY.LOW).text
                      }`}>
                        {String(simulationIncident?.severity || selectedSignal.severity || "Signal")}
                      </span>
                      <span className="text-xs font-mono font-bold uppercase px-2.5 py-1 rounded text-blue-600 bg-blue-50 border border-blue-100">
                        {simulationIncident?.status || "INTELLIGENCE"}
                      </span>
                      <button
                        type="button"
                        onClick={() => selectedSignalHasGeo && selectedSignal && monteCarlo.mutate(selectedSignal)}
                        disabled={monteCarlo.isPending || !selectedSignalHasGeo}
                        className="ml-auto flex items-center gap-2 px-4 py-2 bg-red-500 text-white hover:bg-red-600 font-mono text-xs uppercase tracking-widest transition-colors rounded shadow-sm disabled:opacity-50"
                      >
                        {monteCarlo.isPending ? <Loader2 size={14} className="animate-spin" /> : <FlaskConical size={14} />}
                        {monteCarlo.isPending ? "Running..." : "Run Monte Carlo"}
                      </button>
                    </div>
                    <h2 className="font-headline text-2xl font-bold uppercase tracking-tight text-slate-900">
                      {String(selectedSignal.title || "Signal")}
                    </h2>
                    <p className="text-base text-slate-600 mt-2 leading-relaxed font-medium">
                      {String(selectedSignal.description || simulationIncident?.event_description || selectedSignal.event_type || "")}
                    </p>
                    <div className="flex items-center gap-4 mt-3 text-sm font-mono font-bold text-slate-400">
                      {Boolean(selectedSignal.location) && <span>{String(selectedSignal.location)}</span>}
                      {Boolean(selectedSignal.time || selectedSignal.published_at || selectedSignal.detected_at) && (
                        <span>
                          {new Date(String(selectedSignal.time || selectedSignal.published_at || selectedSignal.detected_at)).toLocaleString()}
                        </span>
                      )}
                      {Boolean(selectedSignal.url) && (
                        <a
                          href={String(selectedSignal.url)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center gap-1.5 text-red-500 hover:underline font-bold"
                        >
                          <ExternalLink size={12} /> Source
                        </a>
                      )}
                    </div>
                  </div>

                  {!simulationIncident ? (
                    <div className="border border-slate-200 bg-slate-50 rounded p-8 text-center shadow-inner">
                      <p className="text-sm font-mono uppercase tracking-widest text-slate-400 font-bold">
                        {noImpactReason ? "Simulation Completed" : monteCarloError ? "Simulation Failed" : "Select this signal and run the real workflow simulation."}
                      </p>
                      {noImpactReason ? (
                        <p className="text-sm text-slate-600 mt-3 leading-relaxed max-w-2xl mx-auto font-medium">
                          {noImpactReason}
                        </p>
                      ) : monteCarloError ? (
                        <p className="text-sm text-red-600 mt-3 leading-relaxed max-w-2xl mx-auto font-bold">
                          {monteCarloError}
                        </p>
                      ) : (
                        <p className="text-sm text-slate-600 mt-3 leading-relaxed max-w-2xl mx-auto font-medium">
                          {selectedSignalHasGeo
                            ? "The simulation uses this exact intelligence record plus the current tenant's supplier graph to produce an Incidents-style analysis and Monte Carlo summary for this location."
                            : "This signal has no usable geolocation yet, so Monte Carlo is disabled until the record is geocoded."}
                        </p>
                      )}
                      {(noImpactReason || monteCarloError) && dataQuality && (
                        <div className="mt-4 bg-white border border-slate-200 px-4 py-3 rounded text-sm text-slate-600 font-medium">
                          Data quality score: {Number(dataQuality.score || 0).toFixed(0)} ·
                          automation ready: {dataQuality.ready_for_automation ? " yes" : " no"}
                        </div>
                      )}
                    </div>
                  ) : (
                    <>
                      <div className="grid grid-cols-4 gap-2">
                        {[
                          {
                            label: "Exposure",
                            value: `$${Number(simulationIncident.total_exposure_usd || 0).toLocaleString()}`,
                            icon: DollarSign,
                            color: "text-red-500",
                          },
                          {
                            label: "Value At Risk",
                            value: `$${Number(simulationIncident.value_at_risk_usd || 0).toLocaleString()}`,
                            icon: Zap,
                            color: "text-orange-500",
                          },
                          {
                            label: "Stockout",
                            value: `${Number(simulationIncident.min_stockout_days || 0).toFixed(1)} days`,
                            icon: Clock,
                            color: Number(simulationIncident.min_stockout_days || 999) <= 5 ? "text-red-500" : "text-yellow-600",
                          },
                          {
                            label: "Praecantator Confidence",
                            value: `${(Number(simulationIncident.gnn_confidence || 0) * 100).toFixed(0)}%`,
                            icon: Shield,
                            color: "text-blue-600",
                          },
                        ].map((m) => (
                          <div key={m.label} className="border border-slate-200 bg-white p-4 rounded shadow-sm">
                            <div className="flex items-center gap-2 mb-2">
                              <m.icon size={12} className="text-slate-400" />
                              <span className="text-xs font-mono font-bold text-slate-400 uppercase tracking-widest">{m.label}</span>
                            </div>
                            <div className={`text-xl font-bold font-headline tracking-wide ${m.color}`}>{m.value}</div>
                          </div>
                        ))}
                      </div>

                      <div className="border border-slate-200 p-5 rounded bg-slate-50 shadow-inner">
                        <p className="text-xs font-mono font-bold uppercase tracking-widest text-slate-400 mb-4">
                          Affected Nodes · Praecantator-Scored
                        </p>
                        <div className="space-y-3 max-h-52 overflow-y-auto custom-scrollbar">
                          {(simulationIncident.affected_nodes || []).map((node, i) => {
                            const score = Number(node.risk_score || 0);
                            return (
                              <div
                                key={i}
                                className="flex items-center gap-4 py-3 px-4 bg-white border border-slate-200 shadow-sm rounded"
                              >
                                <div
                                  className="w-2.5 h-2.5 shrink-0 rounded-full"
                                  style={{
                                    backgroundColor:
                                      score >= 0.8 ? "#DC2626" : score >= 0.6 ? "#ea580c" : "#16a34a",
                                    boxShadow: `0 0 6px ${score >= 0.8 ? "#DC2626" : score >= 0.6 ? "#ea580c" : "#16a34a"}`,
                                  }}
                                />
                                <div className="flex-1 min-w-0">
                                  <span className="text-sm text-slate-900 font-bold tracking-wide truncate block">
                                    {String(node.name || "Node")}
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
                            <span className="text-red-600 text-xs font-mono font-bold uppercase tracking-wide">★ {String(simulationIncident.recommendation || "REVIEW")}</span>
                          </div>
                          <p className="text-sm text-slate-700 leading-relaxed font-semibold mt-1 whitespace-pre-line">
                            {String(simulationIncident.recommendation_detail || "")}
                          </p>
                        </div>

                        {simulationIncident.backup_supplier && (
                          <div className="bg-emerald-50 border border-emerald-200 px-4 py-3 mb-4 rounded shadow-sm">
                            <div className="flex items-center gap-2 mb-2">
                              <Shield size={14} className="text-emerald-600" />
                              <span className="text-xs font-mono font-bold text-emerald-600 uppercase tracking-widest">Backup Supplier</span>
                            </div>
                            <div className="mt-2 text-sm font-bold text-slate-900 font-headline">
                              {String(simulationIncident.backup_supplier.name || "")}
                              <span className="text-emerald-600 font-mono text-xs ml-3 border-l border-emerald-200 pl-3">
                                {String(simulationIncident.backup_supplier.location || "")}
                              </span>
                            </div>
                          </div>
                        )}

                        <div className="space-y-2">
                          {(simulationIncident.route_options || []).map((route, i) => {
                            const mode = String(route.mode || "");
                            const ModeIcon = MODE_ICONS[mode] || Truck;
                            const isRec = Boolean(route.recommended);
                            return (
                              <div
                                key={i}
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
                                <span className={`text-[10px] sm:text-xs font-mono font-bold uppercase px-2.5 py-1 rounded shrink-0 ${
                                  isRec ? "text-red-600 bg-red-100 border border-red-200" : "text-blue-600 bg-blue-50 border border-blue-100"
                                }`}>
                                  {String(isRec ? "REC" : route.status_label || "")}
                                </span>
                              </div>
                            );
                          })}
                        </div>
                      </div>

                      {simulation && (
                        <div className="border border-slate-200 p-5 rounded bg-slate-50 shadow-inner">
                          <p className="text-xs font-mono font-bold uppercase tracking-widest text-slate-400 mb-4">
                            Monte Carlo Summary
                          </p>
                          <div className="grid grid-cols-4 gap-2 mb-4">
                            <div className="border border-slate-200 bg-white p-4 rounded shadow-sm">
                              <div className="text-xs font-mono font-bold text-slate-400 uppercase tracking-widest">Protected Runs</div>
                              <div className="text-xl font-bold font-headline text-emerald-600 mt-2">
                                {(Number(simulation.protected_rate || 0) * 100).toFixed(0)}%
                              </div>
                            </div>
                            <div className="border border-slate-200 bg-white p-4 rounded shadow-sm">
                              <div className="text-xs font-mono font-bold text-slate-400 uppercase tracking-widest">Route Reliability</div>
                              <div className="text-xl font-bold font-headline text-blue-600 mt-2">
                                {(Number(simulation.route_reliability || 0) * 100).toFixed(0)}%
                              </div>
                            </div>
                            <div className="border border-slate-200 bg-white p-4 rounded shadow-sm">
                              <div className="text-xs font-mono font-bold text-slate-400 uppercase tracking-widest">Exposure Avoided</div>
                              <div className="text-xl font-bold font-headline text-red-600 mt-2">
                                ${Number(simulation.expected_exposure_avoided_usd || 0).toLocaleString()}
                              </div>
                            </div>
                            <div className="border border-slate-200 bg-white p-4 rounded shadow-sm">
                              <div className="text-xs font-mono font-bold text-slate-400 uppercase tracking-widest">Worst Case Loss</div>
                              <div className="text-xl font-bold font-headline text-orange-600 mt-2">
                                ${Number(simulation.worst_case_loss_usd || 0).toLocaleString()}
                              </div>
                            </div>
                          </div>

                          <div className="grid grid-cols-2 gap-4">
                            <div className="bg-white border border-slate-200 p-4 rounded shadow-sm">
                              <div className="text-xs font-mono font-bold uppercase tracking-widest text-slate-400 mb-3">Arrival Distribution</div>
                              <div className="space-y-2 text-sm text-slate-600 font-medium">
                                <div>P10: {Number(simulation.arrival_days_p10 || 0).toFixed(1)} days</div>
                                <div>P50: {Number(simulation.arrival_days_p50 || 0).toFixed(1)} days</div>
                                <div>P90: {Number(simulation.arrival_days_p90 || 0).toFixed(1)} days</div>
                              </div>
                            </div>
                            <div className="bg-white border border-slate-200 p-4 rounded shadow-sm">
                              <div className="text-xs font-mono font-bold uppercase tracking-widest text-slate-400 mb-3">Disruption Duration</div>
                              <div className="space-y-2 text-sm text-slate-600 font-medium">
                                <div>P10: {Number(simulation.disruption_days_p10 || 0).toFixed(1)} days</div>
                                <div>P50: {Number(simulation.disruption_days_p50 || 0).toFixed(1)} days</div>
                                <div>P90: {Number(simulation.disruption_days_p90 || 0).toFixed(1)} days</div>
                              </div>
                            </div>
                          </div>

                          {simulationIncident.scenario_confidence && (
                            <div className="mt-4 bg-blue-50 border border-blue-100 px-4 py-3 rounded text-sm text-slate-700 font-bold">
                              Scenario confidence: base {(Number(simulationIncident.scenario_confidence.base || 0) * 100).toFixed(0)}% ·
                              best {(Number(simulationIncident.scenario_confidence.best_case || 0) * 100).toFixed(0)}% ·
                              worst {(Number(simulationIncident.scenario_confidence.worst_case || 0) * 100).toFixed(0)}%
                            </div>
                          )}

                          {dataQuality && (
                            <div className="mt-4 bg-slate-100 border border-slate-200 px-4 py-3 rounded text-sm text-slate-600 font-bold">
                              Data quality score: {Number(dataQuality.score || 0).toFixed(0)} ·
                              automation ready: {dataQuality.ready_for_automation ? " yes" : " no"}
                            </div>
                          )}

                        </div>
                      )}

                      <CheckpointBanner incidentId={String(simulationIncident.id)} />
                      <ReasoningPanel workflowId={String(simulationIncident.id)} />
                    </>
                  )}
                </div>
              )}
            </div>
          </div>
        ) : (
          /* Map view */
          <div className="h-full">
            {heatmapPoints.length > 0 ? (
              <Heatmap data={heatmapPoints} />
            ) : (
              <div className="w-full h-full bg-slate-50 flex items-center justify-center">
                <p className="text-slate-400 font-mono text-sm font-bold uppercase tracking-widest">No events with geographic data</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default Intelligence;
