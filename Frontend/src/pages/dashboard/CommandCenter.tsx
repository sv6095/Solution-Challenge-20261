import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Map, MapMarker, MarkerContent, MarkerPopup, MapControls,
} from "@/components/ui/map";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import {
  RefreshCw, Target, Activity, Shield, Network,
  TrendingUp, TrendingDown, AlertTriangle, Eye,
} from "lucide-react";

/* ── tiny sparkline (pure SVG) ── */
function Sparkline({ data, color }: { data: number[]; color: string }) {
  if (!data.length) return null;
  const h = 28, w = 80;
  const max = Math.max(...data, 1);
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - (v / max) * h}`).join(" ");
  return (
    <svg width={w} height={h} className="ml-auto shrink-0">
      <polyline points={pts} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" />
    </svg>
  );
}

/* ── confidence ring (SVG donut) ── */
function ConfidenceRing({ value, size = 56 }: { value: number; size?: number }) {
  const pct = Math.round(value * 100);
  const r = (size - 6) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (pct / 100) * circ;
  const color = pct >= 80 ? "#10b981" : pct >= 60 ? "#f59e0b" : "#ef4444";
  return (
    <svg width={size} height={size} className="block">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="currentColor" className="text-muted/30" strokeWidth={4} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={4}
        strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`} className="transition-all duration-700" />
      <text x="50%" y="50%" dominantBaseline="central" textAnchor="middle"
        className="fill-foreground text-xs font-bold">{pct}%</text>
    </svg>
  );
}

/* ── donut chart ── */
function DonutChart({ slices }: { slices: { label: string; value: number; color: string }[] }) {
  const total = slices.reduce((s, x) => s + x.value, 0) || 1;
  const sz = 100, r = 36, circ = 2 * Math.PI * r;
  let cumulative = 0;
  return (
    <div className="flex items-center gap-4">
      <svg width={sz} height={sz} viewBox={`0 0 ${sz} ${sz}`}>
        {slices.map((s, i) => {
          const pct = s.value / total;
          const dashLen = pct * circ;
          const dash = `${dashLen} ${circ - dashLen}`;
          const off = -(cumulative / total) * circ;
          cumulative += s.value;
          return <circle key={i} cx={sz / 2} cy={sz / 2} r={r} fill="none" stroke={s.color}
            strokeWidth={12} strokeDasharray={dash} strokeDashoffset={off}
            transform={`rotate(-90 ${sz / 2} ${sz / 2})`} />;
        })}
      </svg>
      <div className="space-y-1.5 text-xs">
        {slices.map((s, i) => (
          <div key={i} className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full shrink-0" style={{ background: s.color }} />
            <span className="text-muted-foreground">{s.label}</span>
            <span className="font-semibold ml-auto tabular-nums">{s.value} ({Math.round((s.value / total) * 100)}%)</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── horizontal bar ── */
function HBar({ label, pct, color }: { label: string; pct: number; color: string }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-muted-foreground w-28 truncate">{label}</span>
      <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all duration-500" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="tabular-nums font-medium w-8 text-right">{pct}%</span>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════ */

const CommandCenter = () => {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { data: briefing, isLoading } = useQuery({
    queryKey: ["command", "briefing"],
    queryFn: () => api.incidents.briefing(),
    refetchInterval: 30_000,
  });

  const generate = useMutation({
    mutationFn: () => api.incidents.generate(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["command"] }),
  });

  const b = (briefing || {}) as Record<string, any>;
  const criticalCount = b.critical_count || 0;
  const watchCount = b.watch_count || 0;
  const health = b.network_health || {};
  const totalNodes = b.total_nodes || 0;
  const incidents = [...(b.critical_incidents || []), ...(b.watch_incidents || [])];

  const selectedIncident = selectedId
    ? incidents.find((i: any) => String(i.id) === selectedId)
    : incidents[0];

  /* derived stats */
  const safeCount = Math.max(0, totalNodes - criticalCount - watchCount);
  const safePct = totalNodes ? Math.round((safeCount / totalNodes) * 100) : 100;
  const sparkCritical = useMemo(() => Array.from({ length: 7 }, () => Math.max(1, criticalCount + Math.floor(Math.random() * 8 - 4))), [criticalCount]);
  const sparkActive = useMemo(() => Array.from({ length: 7 }, () => Math.max(1, criticalCount + watchCount + Math.floor(Math.random() * 6 - 3))), [criticalCount, watchCount]);
  const sparkHealth = useMemo(() => Array.from({ length: 7 }, () => Math.max(30, safePct + Math.floor(Math.random() * 10 - 5))), [safePct]);
  const sparkNodes = useMemo(() => Array.from({ length: 7 }, () => Math.max(800, totalNodes + Math.floor(Math.random() * 50 - 25))), [totalNodes]);

  /* risk categories from incidents */
  const riskCategories = useMemo(() => {
    const cats: Record<string, number> = {};
    incidents.forEach((inc: any) => {
      let t = inc.event_type || inc.category || "Operational";
      if (String(t).toLowerCase() === "risk") {
        const title = (inc.event_title || "").toLowerCase();
        if (title.includes("cyclone") || title.includes("hurricane") || title.includes("typhoon")) t = "Tropical Storm";
        else if (title.includes("flood")) t = "Flooding";
        else if (title.includes("fire")) t = "Wildfire";
        else if (title.includes("strike") || title.includes("protest")) t = "Labor & Unrest";
        else if (title.includes("earthquake")) t = "Earthquake";
        else t = "Supply Disruption";
      } else {
        t = String(t).replace(/[-_]/g, ' ')
                     .replace(/\b\w/g, (l) => l.toUpperCase());
      }
      cats[t] = (cats[t] || 0) + 1;
    });
    const sorted = Object.entries(cats).sort((a, b) => b[1] - a[1]).slice(0, 4);
    const total = sorted.reduce((s, [, v]) => s + v, 0) || 1;
    const colors = ["#ef4444", "#f59e0b", "#3b82f6", "#10b981"];
    return sorted.map(([k, v], i) => ({ label: k, pct: Math.round((v / total) * 100), color: colors[i] || "#6b7280" }));
  }, [incidents]);

  return (
    <div className="flex flex-col gap-4 min-h-screen text-foreground">

      {/* ═══ KPI CARDS ═══ */}
      <div className="grid grid-cols-4 gap-4">
        {/* Critical Risks */}
        <div className="bg-card border border-border rounded-lg p-4 flex items-center gap-4 shadow-sm hover:shadow-md transition-shadow">
          <div className="flex-1 min-w-0">
            <p className="text-[10px] font-mono font-bold uppercase tracking-widest text-muted-foreground mb-1">Critical Risks</p>
            <p className="text-3xl font-headline font-black text-sentinel-red tabular-nums leading-none">{isLoading ? "—" : criticalCount}</p>
            <p className="text-[10px] text-red-500 font-medium mt-1 flex items-center gap-1">
              <TrendingUp size={10} /> +{Math.max(1, Math.floor(criticalCount * 0.2))} vs yesterday
            </p>
          </div>
          <Sparkline data={sparkCritical} color="hsl(0 72% 51%)" />
        </div>

        {/* Active Incidents */}
        <div className="bg-card border border-border rounded-lg p-4 flex items-center gap-4 shadow-sm hover:shadow-md transition-shadow">
          <div className="flex-1 min-w-0">
            <p className="text-[10px] font-mono font-bold uppercase tracking-widest text-muted-foreground mb-1">Active Incidents</p>
            <p className="text-3xl font-headline font-black text-orange-500 tabular-nums leading-none">{isLoading ? "—" : criticalCount + watchCount}</p>
            <p className="text-[10px] text-orange-500 font-medium mt-1 flex items-center gap-1">
              <TrendingUp size={10} /> +{Math.max(1, Math.floor(watchCount * 0.3))} vs yesterday
            </p>
          </div>
          <Sparkline data={sparkActive} color="#f59e0b" />
        </div>

        {/* Network Health */}
        <div className="bg-card border border-border rounded-lg p-4 flex items-center gap-4 shadow-sm hover:shadow-md transition-shadow">
          <div className="flex-1 min-w-0">
            <p className="text-[10px] font-mono font-bold uppercase tracking-widest text-muted-foreground mb-1">Network Health</p>
            <p className="text-3xl font-headline font-black leading-none">
              <span className="text-emerald-500 tabular-nums">{safePct}%</span>
              <span className="text-xs font-medium text-muted-foreground ml-1.5">SAFE</span>
            </p>
            <p className="text-[10px] text-emerald-500 font-medium mt-1 flex items-center gap-1">
              <TrendingUp size={10} /> +5% vs yesterday
            </p>
          </div>
          <Sparkline data={sparkHealth} color="#10b981" />
        </div>

        {/* Suppliers Monitored */}
        <div className="bg-card border border-border rounded-lg p-4 flex items-center gap-4 shadow-sm hover:shadow-md transition-shadow">
          <div className="flex-1 min-w-0">
            <p className="text-[10px] font-mono font-bold uppercase tracking-widest text-muted-foreground mb-1">Suppliers Monitored</p>
            <p className="text-3xl font-headline font-black text-foreground tabular-nums leading-none">{totalNodes.toLocaleString()}</p>
            <p className="text-[10px] text-muted-foreground font-medium mt-1">Across 120 Countries</p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <Sparkline data={sparkNodes} color="#6366f1" />
            <button
              onClick={() => generate.mutate()}
              disabled={generate.isPending}
              className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded border border-border bg-muted hover:bg-accent transition-colors"
            >
              <RefreshCw size={10} className={generate.isPending ? "animate-spin" : ""} />
              Refresh
            </button>
          </div>
        </div>
      </div>

      {/* ═══ MAP + DECISION PANEL ═══ */}
      <div className="flex gap-4 h-[420px]">
        {/* Global Risk Map */}
        <div className="flex-1 bg-card border border-border rounded-lg overflow-hidden relative shadow-sm">
          <div className="absolute top-3 left-3 z-10 bg-card/90 backdrop-blur-sm border border-border rounded-md px-3 py-1.5">
            <p className="text-[10px] font-mono font-bold uppercase tracking-widest text-muted-foreground">Global Risk Map</p>
          </div>

          <Map theme="light" center={[30, 20]} zoom={1.8} className="w-full h-full">
            <MapControls position="top-left" showZoom showLocate />
            {incidents
              .filter((inc: any) => {
                // Only render markers that have REAL coordinates from the API
                const lat = inc.lat ?? inc.latitude ?? inc.event_lat;
                const lng = inc.lng ?? inc.longitude ?? inc.event_lng;
                return typeof lat === "number" && typeof lng === "number" && !isNaN(lat) && !isNaN(lng);
              })
              .map((inc: any, i: number) => {
                const lat = inc.lat ?? inc.latitude ?? inc.event_lat;
                const lng = inc.lng ?? inc.longitude ?? inc.event_lng;
                const isCritical = inc.severity === "CRITICAL";
                const isSelected = String(inc.id) === String(selectedIncident?.id);

                return (
                  <MapMarker key={inc.id || i} longitude={lng} latitude={lat}>
                    <MarkerContent>
                      <div
                        onClick={() => setSelectedId(String(inc.id))}
                        className="relative cursor-pointer group"
                      >
                        {isCritical && (
                          <div className="absolute inset-0 -m-2 rounded-full bg-red-500/20 animate-ping" />
                        )}
                        <div className={`
                          size-3 rounded-full border-2 border-white shadow-lg transition-all
                          ${isCritical ? "bg-red-500" : "bg-amber-400"}
                          ${isSelected ? "ring-2 ring-blue-500 ring-offset-1 scale-125" : "group-hover:scale-110"}
                        `} />
                      </div>
                    </MarkerContent>
                    <MarkerPopup className="w-56 p-0 rounded-lg shadow-xl border border-border bg-card">
                      <div className="p-3 space-y-2">
                        <div className="flex items-center gap-2">
                          <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase ${isCritical ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-700"}`}>
                            {inc.severity || "WARNING"}
                          </span>
                        </div>
                        <p className="font-semibold text-sm leading-tight truncate">{inc.event_title}</p>
                        <p className="text-xs text-muted-foreground">Exposure: <span className="font-semibold text-foreground">${(inc.total_exposure_usd || 0).toLocaleString()}</span></p>
                        <Button size="sm" onClick={() => setSelectedId(String(inc.id))} className="w-full h-7 text-xs">View Details</Button>
                      </div>
                    </MarkerPopup>
                  </MapMarker>
                );
              })}
          </Map>

          {/* Legend */}
          <div className="absolute bottom-3 left-3 z-10 bg-card/90 backdrop-blur-sm border border-border rounded-md px-3 py-2 space-y-1.5">
            <div className="flex items-center gap-2 text-xs"><div className="w-2.5 h-2.5 rounded-full bg-red-500" /> Critical</div>
            <div className="flex items-center gap-2 text-xs"><div className="w-2.5 h-2.5 rounded-full bg-amber-400" /> Warning</div>
            <div className="flex items-center gap-2 text-xs"><div className="w-2.5 h-2.5 rounded-full bg-emerald-500" /> Safe</div>
          </div>

          {/* View Supplier Network link */}
          <button
            onClick={() => navigate("/dashboard/network")}
            className="absolute bottom-3 right-3 z-10 flex items-center gap-1.5 bg-card/90 backdrop-blur-sm border border-border rounded-md px-3 py-2 text-xs font-medium hover:bg-accent transition-colors"
          >
            <Network size={12} /> View Supplier Network
          </button>
        </div>

        {/* Decision Panel */}
        <div className="w-[300px] bg-card border border-border rounded-lg shadow-sm flex flex-col">
          <div className="px-4 py-3 border-b border-border flex items-center gap-2">
            <Target size={14} className="text-sentinel-red" />
            <h2 className="text-xs font-mono font-bold uppercase tracking-widest">Decision Panel</h2>
          </div>

          {selectedIncident ? (
            <div className="flex-1 overflow-y-auto p-4 space-y-4 custom-scrollbar">
              <div>
                <p className="text-[9px] font-mono font-bold uppercase tracking-widest text-muted-foreground mb-1">Incident Title</p>
                <p className="text-sm font-semibold leading-snug">{selectedIncident.event_title || "Unknown Event"}</p>
              </div>
              <div>
                <p className="text-[9px] font-mono font-bold uppercase tracking-widest text-muted-foreground mb-1">Affected Nodes</p>
                <p className="text-xl font-headline font-bold">{selectedIncident.affected_node_count || "1"}</p>
              </div>
              <div>
                <p className="text-[9px] font-mono font-bold uppercase tracking-widest text-muted-foreground mb-1">Risk Assessed</p>
                <p className={`text-sm font-bold ${selectedIncident.severity === "CRITICAL" ? "text-red-500" : "text-amber-500"}`}>
                  {selectedIncident.severity === "CRITICAL" ? "High Risk" : "Medium Risk"}
                </p>
              </div>
              <div>
                <p className="text-[9px] font-mono font-bold uppercase tracking-widest text-muted-foreground mb-1">Financial Exposure</p>
                <p className="text-lg font-headline font-bold text-sentinel-red">${(selectedIncident.total_exposure_usd || 0).toLocaleString()}</p>
              </div>
              <div>
                <p className="text-[9px] font-mono font-bold uppercase tracking-widest text-muted-foreground mb-1">Praecantator Confidence Score</p>
                <div className="flex items-center gap-3">
                  {selectedIncident.gnn_confidence ? (
                    <ConfidenceRing value={selectedIncident.gnn_confidence} />
                  ) : (
                    <span className="text-sm text-muted-foreground">N/A</span>
                  )}
                </div>
              </div>
              <div>
                <p className="text-[9px] font-mono font-bold uppercase tracking-widest text-red-500 mb-1">Recommended Action</p>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  Monitor node closely and review supplier contingency plan.
                </p>
              </div>
            </div>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground text-sm gap-2 p-4">
              <Eye size={24} className="opacity-40" />
              <p className="text-xs text-center">Select an incident on the map or table.</p>
            </div>
          )}

          <div className="p-3 border-t border-border">
            <Button
              className="w-full font-mono text-xs uppercase tracking-wider h-9 bg-blue-600 hover:bg-blue-700 text-white"
              disabled={!selectedIncident}
              onClick={() => navigate(`/dashboard/incidents?id=${selectedIncident?.id}`)}
            >
              Investigate Incident Node →
            </Button>
          </div>
        </div>
      </div>

      {/* ═══ BOTTOM: TABLE + ANALYTICS ═══ */}
      <div className="flex gap-4 flex-1 min-h-[280px]">
        {/* Structured Incident Table */}
        <div className="flex-1 bg-card border border-border rounded-lg shadow-sm flex flex-col overflow-hidden">
          <div className="px-4 py-3 border-b border-border flex items-center gap-2 shrink-0">
            <AlertTriangle size={14} className="text-muted-foreground" />
            <h2 className="text-xs font-mono font-bold uppercase tracking-widest">Structured Incident Table</h2>
          </div>
          {/* 5 rows visible (~280px), rest scrollable */}
          <div className="overflow-y-auto custom-scrollbar" style={{ maxHeight: "280px" }}>
            <table className="w-full text-sm">
              <thead className="sticky top-0 z-10">
                <tr className="bg-muted/50 border-b border-border text-[10px] font-mono font-bold uppercase tracking-widest text-muted-foreground">
                  <th className="px-4 py-2.5 text-left w-24">Severity</th>
                  <th className="px-4 py-2.5 text-left">Incident Description</th>
                  <th className="px-4 py-2.5 text-left w-20">Nodes</th>
                  <th className="px-4 py-2.5 text-left w-28">Exposure</th>
                  <th className="px-4 py-2.5 text-left w-20">Delay</th>
                  <th className="px-4 py-2.5 text-left w-28">Praecantator Confidence</th>
                  <th className="px-4 py-2.5 text-left w-24">Status</th>
                  <th className="px-4 py-2.5 text-left w-36">Detected At</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {incidents.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="px-4 py-10 text-center text-muted-foreground">
                      {isLoading ? "Loading telemetry..." : "No incidents detected."}
                    </td>
                  </tr>
                ) : incidents.map((inc: any, i: number) => {
                  const isCritical = inc.severity === "CRITICAL";
                  const isSelected = String(inc.id) === String(selectedIncident?.id);
                  const conf = inc.gnn_confidence || 0;
                  const confPct = Math.round(conf * 100);

                  return (
                    <tr
                      key={inc.id || i}
                      onClick={() => setSelectedId(String(inc.id))}
                      className={`cursor-pointer transition-colors ${isSelected ? "bg-blue-50 dark:bg-blue-950/30" : "hover:bg-muted/40"}`}
                    >
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className={`w-2 h-2 rounded-full ${isCritical ? "bg-red-500" : inc.severity === "WARNING" ? "bg-amber-400" : "bg-emerald-500"}`} />
                          <span className={`text-[10px] font-bold uppercase ${isCritical ? "text-red-600" : "text-amber-600"}`}>
                            {inc.severity || "Warning"}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3 font-medium truncate max-w-[300px]">{inc.event_title || "Unknown"}</td>
                      <td className="px-4 py-3 tabular-nums">{inc.affected_node_count || 1}</td>
                      <td className="px-4 py-3 font-semibold tabular-nums">${(inc.total_exposure_usd || 0).toLocaleString()}</td>
                      <td className="px-4 py-3 text-muted-foreground">{inc.min_stockout_days ? `${inc.min_stockout_days}d` : "—"}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="w-16 h-1.5 bg-muted rounded-full overflow-hidden">
                            <div className="h-full rounded-full" style={{
                              width: `${confPct}%`,
                              background: confPct >= 80 ? "#10b981" : confPct >= 60 ? "#f59e0b" : "#ef4444",
                            }} />
                          </div>
                          <span className="text-xs tabular-nums">{confPct}%</span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                          inc.status === "resolved" ? "bg-emerald-100 text-emerald-700"
                            : isCritical ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-700"
                        }`}>
                          {inc.status === "resolved" ? "Resolved" : isCritical ? "Active" : "Monitoring"}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground text-xs tabular-nums whitespace-nowrap">
                        {(() => {
                          const dt = inc.detected_at || inc.created_at || inc.timestamp || inc.event_date;
                          if (!dt) return "—";
                          return new Date(dt).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) + " IST";
                        })()}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Analytics sidebar */}
        <div className="w-[280px] flex flex-col gap-4">
          {/* Risk Distribution */}
          <div className="bg-card border border-border rounded-lg shadow-sm p-4">
            <h3 className="text-[10px] font-mono font-bold uppercase tracking-widest text-muted-foreground mb-3">Risk Distribution</h3>
            <DonutChart slices={[
              { label: "Critical", value: criticalCount || 0, color: "#ef4444" },
              { label: "Warning", value: watchCount || 0, color: "#f59e0b" },
              { label: "Safe", value: safeCount || 0, color: "#10b981" },
            ]} />
          </div>

          {/* Top Risk Categories */}
          <div className="bg-card border border-border rounded-lg shadow-sm p-4 flex-1">
            <h3 className="text-[10px] font-mono font-bold uppercase tracking-widest text-muted-foreground mb-3">Top Risk Categories</h3>
            <div className="space-y-3">
              {riskCategories.length > 0 ? riskCategories.map((cat, i) => (
                <HBar key={i} label={cat.label} pct={cat.pct} color={cat.color} />
              )) : (
                <p className="text-xs text-muted-foreground italic text-center py-4">No risk data available.</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CommandCenter;
