import { Loader2 } from "lucide-react";
import { useHazards, useNewsSignals, useDataSources } from "@/hooks/use-dashboard";

const SignalMonitor = () => {
  const { data: hazards, isLoading: hLoading } = useHazards();
  const { data: news, isLoading: nLoading } = useNewsSignals();
  const { data: sources, isLoading: sLoading } = useDataSources();

  return (
    <div>
      <h1 className="font-headline text-3xl font-bold tracking-tight-sentinel mb-2">Signal Intelligence Feed</h1>
      <p className="text-body-md text-secondary mb-8">Real-time multi-source threat intelligence aggregation.</p>

      <div className="grid lg:grid-cols-3 gap-4">
        {/* Natural Hazards */}
        <div className="surface-container-high rounded-lg p-6">
          <h2 className="font-headline font-bold text-sm uppercase tracking-widest mb-4 flex items-center gap-2">
            <span className="w-2 h-2 bg-blue-400 rounded-full animate-pulse-glow" />
            Natural Hazards
          </h2>
          {hLoading ? (
            <div className="flex justify-center py-8"><Loader2 className="animate-spin text-secondary" /></div>
          ) : hazards?.length === 0 ? (
            <p className="text-secondary text-body-md text-center py-8">No active hazards</p>
          ) : (
            <div className="space-y-3">
              {hazards?.map((h) => (
                <div key={h.id} className="surface-container rounded-lg p-4 relative">
                  <div className={`absolute left-0 top-0 bottom-0 w-1 rounded-l ${h.severity === "High" ? "bg-sentinel" : h.severity === "Medium" ? "bg-yellow-500" : "bg-green-500"}`} />
                  <div className="flex items-center gap-2 mb-1">
                    <span>{h.type}</span>
                    <h3 className="font-headline font-bold text-sm">{h.title}</h3>
                  </div>
                  <p className="text-label-sm text-secondary">{h.location} · {h.time}</p>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* News Signals */}
        <div className="surface-container-high rounded-lg p-6">
          <h2 className="font-headline font-bold text-sm uppercase tracking-widest mb-4 flex items-center gap-2">
            <span className="w-2 h-2 bg-sentinel rounded-full animate-pulse-glow" />
            Global News Intelligence
          </h2>
          {nLoading ? (
            <div className="flex justify-center py-8"><Loader2 className="animate-spin text-secondary" /></div>
          ) : news?.length === 0 ? (
            <p className="text-secondary text-body-md text-center py-8">No signals detected</p>
          ) : (
            <div className="space-y-3">
              {news?.map((n) => (
                <a
                  key={n.id}
                  href={n.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block surface-container rounded-lg p-4 hover:bg-surface-highest/30 transition-colors"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="glass-panel px-2 py-0.5 rounded-sm text-label-sm">{n.source}</span>
                    <span className="text-sentinel text-label-sm font-bold">{n.relevanceScore}% relevant</span>
                  </div>
                  <h3 className="font-headline font-bold text-sm mt-2">{n.title}</h3>
                  <p className="text-label-sm text-secondary mt-1">{n.location} · {n.time}</p>
                </a>
              ))}
            </div>
          )}
        </div>

        {/* Aggregation Status */}
        <div className="surface-container-high rounded-lg p-6">
          <h2 className="font-headline font-bold text-sm uppercase tracking-widest mb-4">Aggregation Engine Status</h2>
          {sLoading ? (
            <div className="flex justify-center py-8"><Loader2 className="animate-spin text-secondary" /></div>
          ) : (
            <div className="space-y-3">
              {sources?.map((s) => (
                <div key={s.id} className="surface-container rounded-lg p-4">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="font-headline font-bold text-sm">{s.name}</h3>
                    <span className={`flex items-center gap-1.5 text-label-sm font-bold ${s.active ? "text-green-500" : "text-yellow-500"}`}>
                      <span className={`w-2 h-2 rounded-full ${s.active ? "bg-green-500" : "bg-yellow-500"} animate-pulse-glow`} />
                      {s.active ? "Active" : "Fallback"}
                    </span>
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-label-sm text-secondary">
                    <div>
                      <p className="uppercase tracking-widest">Last Fetch</p>
                      <p className="text-foreground">{s.lastFetch}</p>
                    </div>
                    <div>
                      <p className="uppercase tracking-widest">Records</p>
                      <p className="text-foreground">{s.recordCount.toLocaleString()}</p>
                    </div>
                    <div>
                      <p className="uppercase tracking-widest">Latency</p>
                      <p className="text-foreground">{s.latencyMs != null ? `${s.latencyMs}ms` : "—"}</p>
                    </div>
                  </div>
                  {!s.active && <p className="text-label-sm text-yellow-500 mt-2">⚡ Using fallback — service degraded</p>}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default SignalMonitor;
