import { Loader2, ExternalLink } from "lucide-react";
import { useExposureSummary, useExposureSuppliers } from "@/hooks/use-dashboard";


const ExposureScores = () => {
  const { data: summary, isLoading: sLoading } = useExposureSummary();
  const { data: suppliers, isLoading: suppLoading } = useExposureSuppliers();

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="font-headline text-3xl font-bold tracking-tight-sentinel">Exposure Risk Analysis</h1>
          <p className="text-body-md text-secondary mt-1">Comprehensive vulnerability assessment across all monitored nodes.</p>
        </div>
        <button
          className="glass-panel px-4 py-2 rounded-sm text-body-md hover:bg-white/10 transition-colors"
          onClick={() => window.open("/api/exposure/export.csv")}
        >
          Export CSV
        </button>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        {sLoading ? (
          Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="surface-container-high rounded-lg p-5 animate-pulse">
              <div className="h-3 w-24 bg-surface-highest rounded mb-3" />
              <div className="h-8 w-16 bg-surface-highest rounded" />
            </div>
          ))
        ) : summary ? (
          <>
            <div className="surface-container-high rounded-lg p-5">
              <p className="text-label-sm text-secondary uppercase tracking-widest">Avg Exposure Score</p>
              <div className="flex items-baseline gap-2 mt-2">
                <span className="font-headline text-3xl font-bold">{summary.avgScore.toFixed(1)}</span>
                <span className="text-body-md text-secondary">/ 100</span>
              </div>
            </div>
            <div className="surface-container-high rounded-lg p-5">
              <p className="text-label-sm text-secondary uppercase tracking-widest">Critical Nodes</p>
              <span className="font-headline text-3xl font-bold text-sentinel mt-2 block">{summary.criticalNodes}</span>
            </div>
            <div className="surface-container-high rounded-lg p-5">
              <p className="text-label-sm text-secondary uppercase tracking-widest">Total Monitored</p>
              <span className="font-headline text-3xl font-bold mt-2 block">{summary.totalMonitored}</span>
            </div>
          </>
        ) : null}
      </div>

      {/* Table */}
      <div className="surface-container-high rounded-lg p-6">
        <div className="grid grid-cols-7 gap-2 text-label-sm text-secondary uppercase tracking-widest mb-4 px-2">
          <span className="col-span-2">Supplier Node</span>
          <span>Tier</span>
          <span>Risk Category</span>
          <span>Exposure Score</span>
          <span>Trend</span>
          <span>Status</span>
        </div>

        {suppLoading ? (
          <div className="flex items-center justify-center py-12"><Loader2 className="animate-spin text-secondary" /></div>
        ) : suppliers?.length === 0 ? (
          <p className="text-body-md text-secondary text-center py-12">No supplier data available.</p>
        ) : (
          suppliers?.map((s) => (
            <div key={s.id} className="grid grid-cols-7 gap-2 items-center px-2 py-4 hover:bg-surface-highest/30 rounded-sm transition-colors">
              <div className="col-span-2">
                <p className="font-headline font-bold text-sm">{s.name}</p>
                <p className="text-label-sm text-secondary">{s.country}</p>
              </div>
              <span className="glass-panel px-2 py-1 rounded-sm text-label-sm text-center">{s.tier}</span>
              <span className="text-body-md text-secondary">{s.category}</span>
              <div className="flex items-center gap-2">
                <div className="flex-1 h-1.5 bg-surface rounded-full overflow-hidden">
                  {/* NOSONAR - Dynamic width required */}
                  <div
                    className={`h-full rounded-full ${s.exposureScore > 80 ? "bg-sentinel" : s.exposureScore > 60 ? "bg-yellow-500" : "bg-green-500"}`}
                    ref={(el) => { if (el) el.style.width = `${s.exposureScore}%`; }}
                  />
                </div>
                <span className="font-headline text-sm font-bold">{s.exposureScore.toFixed(1)}</span>
              </div>
              <span className="text-body-md text-center">
                {s.trend === "up" ? "↑" : s.trend === "down" ? "↓" : "→"}
              </span>
              <span className={`text-label-sm px-2 py-1 rounded-sm text-center font-bold ${
                s.status === "Critical" ? "bg-sentinel/20 text-sentinel" :
                s.status === "High" ? "bg-sentinel/10 text-sentinel" :
                s.status === "Medium" ? "bg-yellow-500/20 text-yellow-500" :
                "bg-green-500/20 text-green-500"
              }`}>
                {s.status}
              </span>
            </div>
          ))
        )}
      </div>

      <div className="surface-container-high rounded-lg p-6 mt-4">
        <h3 className="font-headline font-bold text-sm uppercase tracking-widest mb-2">Score Methodology</h3>
        <p className="text-body-md text-secondary">
          Score = weighted sum of: Proximity to event (40%) + Supplier tier criticality (30%) + Event severity (30%).
          Recalculated every 15 minutes using Vertex AI.
        </p>
      </div>
    </div>
  );
};

export default ExposureScores;
