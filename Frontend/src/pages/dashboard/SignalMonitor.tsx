import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2, Filter, Sparkles, Play } from "lucide-react";
import { useHazards, useNewsSignals, useDataSources } from "@/hooks/use-dashboard";
import { api } from "@/lib/api";

const formatWhen = (value: string) => {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString();
};

const toReadableLink = (url: string | undefined, title: string, location: string) => {
  const clean = (url ?? "").trim();
  if (clean.startsWith("http://") || clean.startsWith("https://")) return clean;
  if (clean && clean.includes(".")) return `https://${clean}`;
  return `https://www.google.com/search?q=${encodeURIComponent(`${title} ${location}`)}`;
};

const SignalMonitor = () => {
  const navigate = useNavigate();
  const { data: hazards, isLoading: hLoading } = useHazards();
  const { data: news, isLoading: nLoading } = useNewsSignals();
  const { data: sources, isLoading: sLoading } = useDataSources();
  const [severityFilter, setSeverityFilter] = useState<"all" | "High" | "Medium" | "Low">("all");
  const [selected, setSelected] = useState<{ kind: "hazard" | "news"; payload: any } | null>(null);
  const [summary, setSummary] = useState<string>("");
  const [summaryProvider, setSummaryProvider] = useState<string>("");
  const [summaryLoading, setSummaryLoading] = useState(false);

  const filteredHazards = useMemo(() => {
    const rows = hazards ?? [];
    if (severityFilter === "all") return rows;
    return rows.filter((h) => h.severity === severityFilter);
  }, [hazards, severityFilter]);

  const startWorkflow = () => {
    if (!selected) return;
    sessionStorage.setItem("preloaded_workflow_event", JSON.stringify(selected.payload));
    navigate("/dashboard/routes?entry=signal_monitor");
  };

  const runSummary = async () => {
    if (!selected) return;
    setSummaryLoading(true);
    try {
      const res = await api.workflow.analyze({
        event: selected.payload,
        suppliers: [],
      });
      setSummary(res.analysis);
      setSummaryProvider(res.provider);
    } catch {
      setSummary("Summary unavailable (configure Gemini/Groq keys).");
      setSummaryProvider("local");
    } finally {
      setSummaryLoading(false);
    }
  };

  return (
    <div>
      <h1 className="font-headline text-3xl font-bold tracking-tight-sentinel mb-2">Signal Intelligence Feed</h1>
      <p className="text-body-md text-secondary mb-8">Real-time multi-source threat intelligence aggregation.</p>

      <div className="flex items-center gap-3 mb-4">
        <div className="glass-panel px-3 py-2 rounded-sm flex items-center gap-2">
          <Filter size={14} className="text-secondary" />
          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value as any)}
            className="bg-transparent text-body-md text-foreground focus:outline-none"
          >
            <option value="all">All severities</option>
            <option value="High">High</option>
            <option value="Medium">Medium</option>
            <option value="Low">Low</option>
          </select>
        </div>
        {selected ? (
          <button
            onClick={startWorkflow}
            className="glass-panel px-4 py-2 rounded-sm text-body-md hover:bg-white/10 transition-colors flex items-center gap-2"
          >
            <Play size={16} className="text-sentinel" />
            Start workflow for this event
          </button>
        ) : null}
      </div>

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
              {filteredHazards?.map((h) => (
                <button
                  key={h.id}
                  onClick={() => {
                    setSelected({ kind: "hazard", payload: h });
                    setSummary("");
                    setSummaryProvider("");
                  }}
                  className="w-full text-left block surface-container rounded-lg p-4 relative hover:bg-surface-highest/40 transition-colors"
                >
                  <div className={`absolute left-0 top-0 bottom-0 w-1 rounded-l ${h.severity === "High" ? "bg-sentinel" : h.severity === "Medium" ? "bg-yellow-500" : "bg-green-500"}`} />
                  <div className="flex items-center gap-2 mb-1">
                    <span>{h.type}</span>
                    <h3 className="font-headline font-bold text-sm">{h.title}</h3>
                  </div>
                  <p className="text-label-sm text-secondary">{h.location} · {formatWhen(h.time)}</p>
                </button>
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
                <button
                  key={n.id}
                  onClick={() => {
                    setSelected({ kind: "news", payload: n });
                    setSummary("");
                    setSummaryProvider("");
                  }}
                  className="w-full text-left block surface-container rounded-lg p-4 hover:bg-surface-highest/30 transition-colors"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="glass-panel px-2 py-0.5 rounded-sm text-label-sm">{n.source}</span>
                    <span className="text-sentinel text-label-sm font-bold">{(n.relevanceScore * 100).toFixed(1)}% relevant</span>
                  </div>
                  <h3 className="font-headline font-bold text-sm mt-2">{n.title}</h3>
                  <p className="text-label-sm text-secondary mt-1">{n.location} · {formatWhen(n.time)}</p>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Detail panel */}
        <div className="surface-container-high rounded-lg p-6">
          <h2 className="font-headline font-bold text-sm uppercase tracking-widest mb-4">Event Detail</h2>
          {!selected ? (
            <p className="text-body-md text-secondary">Select a signal on the left to view details and start a workflow run.</p>
          ) : (
            <div className="space-y-4">
              <div className="surface-container rounded-lg p-4">
                <p className="text-label-sm text-secondary uppercase tracking-widest">{selected.kind === "hazard" ? "Natural hazard" : "News signal"}</p>
                <h3 className="font-headline font-bold text-lg mt-2">{selected.payload.title}</h3>
                <p className="text-body-md text-secondary mt-2">
                  {selected.kind === "hazard"
                    ? `${selected.payload.location} · ${formatWhen(selected.payload.time)}`
                    : `${selected.payload.location} · ${formatWhen(selected.payload.time)} · ${(selected.payload.relevanceScore * 100).toFixed(1)}% relevant`}
                </p>
                <a
                  className="text-sentinel text-label-sm hover:underline mt-3 inline-block"
                  href={toReadableLink(selected.payload.url, selected.payload.title, selected.payload.location)}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Open source link →
                </a>
              </div>

              <div className="surface-container rounded-lg p-4">
                <div className="flex items-center justify-between">
                  <h4 className="font-headline font-bold text-sm">Preliminary summary</h4>
                  <button
                    onClick={runSummary}
                    className="glass-panel px-3 py-2 rounded-sm text-label-sm hover:bg-white/10 transition-colors flex items-center gap-2"
                  >
                    <Sparkles size={14} className="text-sentinel" />
                    Generate
                  </button>
                </div>
                {summaryLoading ? (
                  <div className="flex justify-center py-6"><Loader2 className="animate-spin text-secondary" /></div>
                ) : summary ? (
                  <div className="mt-3 space-y-2">
                    <div className="text-label-sm text-secondary uppercase tracking-widest">
                      Engine: <span className="text-sentinel">{summaryProvider || "local"}</span>
                    </div>
                    <div className="text-body-md text-secondary whitespace-pre-wrap leading-relaxed">{summary}</div>
                  </div>
                ) : (
                  <p className="text-body-md text-secondary mt-3">Generate a quick summary to triage and decide whether to start the workflow.</p>
                )}
              </div>

              <div className="surface-container rounded-lg p-4">
                <h4 className="font-headline font-bold text-sm mb-2">Aggregation engine status</h4>
                {sLoading ? (
                  <div className="flex justify-center py-6"><Loader2 className="animate-spin text-secondary" /></div>
                ) : (
                  <div className="space-y-2">
                    {sources?.map((s) => (
                      <div key={s.id} className="flex items-center justify-between text-body-md">
                        <span className="text-secondary">{s.name}</span>
                        <span className={s.active ? "text-green-500" : "text-yellow-500"}>{s.active ? "Active" : "Fallback"}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default SignalMonitor;
