import { ExternalLink, Loader2 } from "lucide-react";
import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar";
import { FilterSidebar } from "@/app/logistics/components/filter-sidebar";
import { NetworkMap } from "@/app/logistics/components/network-map";
import {
  useDashboardKpis,
  useDashboardEvents,
  useDashboardWorkflows,
  useDashboardSuppliers,
  useNetworkGraph,
} from "@/hooks/use-dashboard";

const severityColor = (s: string) =>
  s === "CRITICAL" || s === "HIGH" ? "bg-sentinel/20 text-sentinel" : "bg-yellow-500/20 text-yellow-500";

const formatWhen = (value: string) => {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString();
};

const DashboardHome = () => {
  const { data: kpis, isLoading: kpisLoading } = useDashboardKpis();
  const { data: events, isLoading: eventsLoading } = useDashboardEvents();
  const { data: workflows, isLoading: wfLoading } = useDashboardWorkflows();
  const { data: suppliers, isLoading: suppLoading } = useDashboardSuppliers();
  const { data: graph } = useNetworkGraph();
  const hubs = graph?.hubs ?? [];
  const routes = graph?.routes ?? [];

  return (
    <div>
      <div className="mb-8">
        <h1 className="font-headline text-3xl font-bold tracking-tight-sentinel">Operational Nexus</h1>
        <p className="text-body-md text-secondary mt-1">Real-time supply chain kinetic monitoring and risk mitigation.</p>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {kpisLoading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="surface-container-high rounded-lg p-5 animate-pulse">
              <div className="h-3 w-24 bg-surface-highest rounded mb-3" />
              <div className="h-8 w-16 bg-surface-highest rounded" />
            </div>
          ))
        ) : kpis ? (
          [
            { label: "Total Suppliers", value: kpis.totalSuppliers.toLocaleString(), sub: "Monitored", subColor: "text-secondary" },
            { label: "Active Risk Events", value: kpis.activeRiskEvents.toString(), sub: "▲ Active", subColor: "text-sentinel", highlight: true },
            { label: "Avg Exposure", value: kpis.avgExposure.toFixed(1), sub: "Out of 100", subColor: "text-secondary" },
            { label: "RFQs Sent", value: kpis.rfqsSent.toLocaleString(), sub: "Last 30d", subColor: "text-sentinel" },
          ].map((kpi) => (
            <div key={kpi.label} className="surface-container-high rounded-lg p-5">
              <p className="text-label-sm uppercase tracking-widest text-secondary">{kpi.label}</p>
              <div className="flex items-baseline gap-2 mt-2">
                <span className={`font-headline text-3xl font-bold ${kpi.highlight ? "text-sentinel" : ""}`}>{kpi.value}</span>
                <span className={`text-body-md ${kpi.subColor}`}>{kpi.sub}</span>
              </div>
            </div>
          ))
        ) : null}
      </div>

      {/* Logistics Network Map */}
      <div className="surface-container-high rounded-lg overflow-hidden mb-8 border border-surface-highest h-[520px]">
        <SidebarProvider className="min-h-0 h-full w-full flex relative overflow-hidden" style={{ "--sidebar-width": "18rem" } as React.CSSProperties}>
          <FilterSidebar hubs={hubs} routes={routes} />
          <SidebarInset className="relative flex-1 bg-transparent m-0 overflow-hidden">
            <NetworkMap hubs={hubs} routes={routes} />
          </SidebarInset>
        </SidebarProvider>
      </div>

      {/* Active Events + Workflow Delta */}
      <div className="grid lg:grid-cols-[1fr_380px] gap-4 mb-8">
        {/* Active Events */}
        <div className="surface-container-high rounded-lg p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-headline text-lg font-bold uppercase tracking-widest">Active Events</h2>
            <span className="text-label-sm text-sentinel uppercase tracking-widest cursor-pointer">View All</span>
          </div>
          <div className="space-y-4">
            {eventsLoading ? (
              Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="surface-container rounded-lg p-4 animate-pulse">
                  <div className="h-3 w-3/4 bg-surface-highest rounded mb-2" />
                  <div className="h-3 w-full bg-surface-highest rounded" />
                </div>
              ))
            ) : (
              events?.map((ev) => (
                <a
                  key={ev.id}
                  href={ev.url || `https://www.google.com/search?q=${encodeURIComponent(`${ev.title} ${ev.region}`)}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block surface-container rounded-lg p-4 relative hover:bg-surface-highest/40 transition-colors"
                >
                  <div className="absolute left-0 top-0 bottom-0 w-1 rounded-l bg-sentinel" />
                  <div className="flex items-center justify-between mb-1">
                    <h3 className="font-headline font-bold text-sm">{ev.title}</h3>
                    <span className={`text-label-sm px-2 py-0.5 rounded-sm font-bold uppercase ${severityColor(ev.severity)}`}>
                      {ev.severity}
                    </span>
                  </div>
                  <p className="text-body-md text-secondary mb-2">{ev.description}</p>
                  <div className="flex items-center justify-between text-label-sm text-secondary">
                    <span>⏱ {formatWhen(ev.timestamp)}</span>
                    <span>👤 {ev.analyst}</span>
                  </div>
                </a>
              ))
            )}
          </div>
        </div>

        {/* Workflow Delta */}
        <div className="surface-container-high rounded-lg p-6">
          <h2 className="font-headline text-lg font-bold uppercase tracking-widest mb-4">Workflow Delta</h2>
          <div className="space-y-4">
            {wfLoading ? (
              Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="flex gap-3 animate-pulse">
                  <div className="w-2 h-2 rounded-full bg-surface-highest mt-2 shrink-0" />
                  <div className="flex-1">
                    <div className="h-3 w-1/2 bg-surface-highest rounded mb-2" />
                    <div className="h-3 w-full bg-surface-highest rounded" />
                  </div>
                </div>
              ))
            ) : (
              workflows?.map((wf) => (
                <div key={wf.id} className="flex gap-3">
                  <div className={`w-2 h-2 rounded-full mt-2 shrink-0 ${wf.status === "complete" ? "bg-green-400" : wf.status === "active" ? "bg-sentinel" : "bg-secondary"}`} />
                  <div>
                    <h3 className="font-headline font-bold text-sm">{wf.title}</h3>
                    <p className="text-body-md text-secondary">{wf.description.replace("api-public", "System")}</p>
                    <span className="text-label-sm text-secondary">{formatWhen(wf.timestamp)}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Priority Exposure Nodes */}
      <div className="surface-container-high rounded-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-headline text-lg font-bold uppercase tracking-widest">Priority Exposure Nodes</h2>
        </div>
        <div className="text-label-sm text-secondary uppercase tracking-widest grid grid-cols-5 gap-2 mb-3 px-2">
          <span className="col-span-2">Supplier Node</span>
          <span>Risk Category</span>
          <span>Exposure</span>
          <span>Action</span>
        </div>
        {suppLoading ? (
          <div className="flex items-center justify-center py-10"><Loader2 className="animate-spin text-secondary" /></div>
        ) : (
          suppliers?.map((s) => (
            <div key={s.id} className="grid grid-cols-5 gap-2 items-center px-2 py-3 hover:bg-surface-highest/30 rounded-sm transition-colors">
              <div className="col-span-2">
                <p className="font-headline font-bold text-sm">{s.name}</p>
                <p className="text-label-sm text-secondary">{s.location}</p>
              </div>
              <span className="glass-panel px-2 py-1 rounded-sm text-label-sm text-center">{s.category}</span>
              <div className="flex items-center gap-2">
                <div className="flex-1 h-1.5 bg-surface rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full ${s.exposureScore > 70 ? "bg-sentinel" : "bg-yellow-500"}`}
                    ref={(el) => { if (el) el.style.width = `${s.exposureScore}%`; }}
                  />
                </div>
                <span className="font-headline text-sm font-bold">{s.exposureScore.toFixed(1)}</span>
              </div>
              <button title={`View ${s.name}`} aria-label={`View details for ${s.name}`} className="text-secondary hover:text-foreground transition-colors">
                <ExternalLink size={16} />
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default DashboardHome;
