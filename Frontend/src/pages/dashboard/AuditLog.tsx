import { useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { useComplianceSummary, useWorkflowReports } from "@/hooks/use-dashboard";
import { api } from "@/lib/api";

const AuditLog = () => {
  const { data: reports, isLoading } = useWorkflowReports();
  const { data: compliance } = useComplianceSummary();
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string | null>(null);
  const selected = useMemo(() => reports?.find((r) => r.workflow_id === selectedWorkflowId) ?? null, [reports, selectedWorkflowId]);
  const [detail, setDetail] = useState<Record<string, any> | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const loadDetail = async (workflowId: string) => {
    setDetailLoading(true);
    try {
      const json = await api.workflows.reportJson(workflowId);
      setDetail(json as any);
    } finally {
      setDetailLoading(false);
    }
  };

  const timeline = useMemo(() => {
    if (!detail) return [];
    const detect = (detail as any).detect || {};
    const assess = (detail as any).assess || {};
    const decide = (detail as any).decide || {};
    const act = (detail as any).act || {};
    const audit = (detail as any).audit || {};
    return [
      { stage: "DETECT", at: detect.detected_at || detect.event?.timestamp, text: detect.event?.title || "Signal detected" },
      { stage: "ASSESS", at: assess.assessed_at || null, text: "Assessment completed" },
      { stage: "DECIDE", at: decide.decided_at || null, text: `Recommended: ${decide.recommended_mode || "—"}` },
      { stage: "ACT", at: act.executed_at || null, text: `Action: ${act.decision || "—"}` },
      { stage: "AUDIT", at: audit.completed_at || null, text: "Audit record generated" },
    ].filter((t) => t.at);
  }, [detail]);

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="font-headline text-3xl font-bold tracking-tight-sentinel">Compliance Audit Trail</h1>
          <p className="text-body-md text-secondary mt-1">Immutable, timestamped records of every workflow execution.</p>
        </div>
        <a
          href={api.audit.exportAll()}
          target="_blank"
          rel="noopener noreferrer"
          className="glass-panel px-4 py-2 rounded-sm text-body-md hover:bg-white/10 transition-colors"
        >
          Export All
        </a>
      </div>

      {compliance ? (
        <div className="grid grid-cols-3 gap-4 mb-6">
          <div className="surface-container-high rounded-lg p-5">
            <p className="text-label-sm text-secondary uppercase tracking-widest">Total workflows</p>
            <p className="font-headline text-3xl font-bold mt-2">{compliance.total_workflows}</p>
          </div>
          <div className="surface-container-high rounded-lg p-5">
            <p className="text-label-sm text-secondary uppercase tracking-widest">Avg response time</p>
            <p className="font-headline text-3xl font-bold mt-2">{compliance.avg_response_time_seconds}s</p>
          </div>
          <div className="surface-container-high rounded-lg p-5">
            <p className="text-label-sm text-secondary uppercase tracking-widest">Actions breakdown</p>
            <p className="text-body-md text-secondary mt-2">
              {Object.entries(compliance.actions_breakdown || {}).map(([k, v]) => `${k}:${v}`).slice(0, 4).join(" · ") || "—"}
            </p>
          </div>
        </div>
      ) : null}

      <div className="surface-container-high rounded-lg p-6">
        <div className="grid grid-cols-6 gap-2 text-label-sm text-secondary uppercase tracking-widest mb-4 px-2">
          <span>Workflow ID</span>
          <span>Event</span>
          <span>Region</span>
          <span>Action</span>
          <span>Response Time</span>
          <span>Export</span>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-12"><Loader2 className="animate-spin text-secondary" /></div>
        ) : reports?.length === 0 ? (
          <p className="text-body-md text-secondary text-center py-12">No audit records yet.</p>
        ) : (
          reports?.map((r) => {
            const summary = (r.summary ?? {}) as any;
            return (
              <div
                key={r.workflow_id}
                className="grid grid-cols-6 gap-2 items-center px-2 py-4 hover:bg-surface-highest/30 rounded-sm transition-colors cursor-pointer"
                onClick={() => {
                  setSelectedWorkflowId(r.workflow_id);
                  loadDetail(r.workflow_id);
                }}
                role="button"
                tabIndex={0}
              >
                <span className="font-headline font-bold text-sm">{r.workflow_id}</span>
                <span className="text-body-md">{summary.event_title ?? "—"}</span>
                <span className="text-body-md text-secondary">{summary.region ?? "—"}</span>
                <span className="text-body-md">{summary.action_taken ?? "—"}</span>
                <span className="font-headline font-bold text-sm text-sentinel">
                  {summary.response_time_seconds != null ? `${summary.response_time_seconds}s` : "—"}
                </span>
                <a
                  href={api.workflows.reportPdfUrl(r.workflow_id)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sentinel text-label-sm hover:underline"
                  title="Download PDF"
                  onClick={(e) => e.stopPropagation()}
                >
                  📄 PDF
                </a>
              </div>
            );
          })
        )}
      </div>

      {selected ? (
        <div className="surface-container-high rounded-lg p-6 mt-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-headline font-bold text-lg">Workflow detail</h2>
            <div className="flex items-center gap-2">
              <a
                href={api.workflows.reportPdfUrl(selected.workflow_id)}
                target="_blank"
                rel="noopener noreferrer"
                className="glass-panel px-4 py-2 rounded-sm text-body-md hover:bg-white/10 transition-colors"
              >
                Download PDF
              </a>
              {detail ? (
                <button
                  className="glass-panel px-4 py-2 rounded-sm text-body-md hover:bg-white/10 transition-colors"
                  onClick={() => {
                    const blob = new Blob([JSON.stringify(detail, null, 2)], { type: "application/json" });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = `${selected.workflow_id}.json`;
                    a.click();
                    URL.revokeObjectURL(url);
                  }}
                >
                  Export JSON
                </button>
              ) : null}
            </div>
          </div>
          <p className="text-body-md text-secondary">
            Workflow ID: <span className="text-foreground font-medium">{selected.workflow_id}</span>
          </p>
          <p className="text-body-md text-secondary mt-2">
            Last updated: <span className="text-foreground font-medium">{selected.updated_at}</span>
          </p>

          <div className="h-px bg-border my-4" />
          {detailLoading ? (
            <div className="flex items-center justify-center py-8"><Loader2 className="animate-spin text-secondary" /></div>
          ) : detail ? (
            <div className="space-y-4">
              <h3 className="font-headline font-bold text-lg">Timeline</h3>
              <div className="space-y-2">
                {timeline.map((t) => (
                  <div key={t.stage} className="surface-container rounded-lg p-4 flex items-center justify-between">
                    <div>
                      <p className="text-label-sm text-secondary uppercase tracking-widest">{t.stage}</p>
                      <p className="text-body-md">{t.text}</p>
                    </div>
                    <p className="text-label-sm text-secondary">{new Date(t.at).toLocaleString()}</p>
                  </div>
                ))}
              </div>
              <h3 className="font-headline font-bold text-lg">Raw record (read-only)</h3>
              <pre className="surface-container rounded-lg p-4 text-xs text-secondary overflow-auto max-h-[360px] whitespace-pre-wrap">
                {JSON.stringify(detail, null, 2)}
              </pre>
            </div>
          ) : (
            <p className="text-body-md text-secondary">Select a workflow run to load details.</p>
          )}
        </div>
      ) : null}
    </div>
  );
};

export default AuditLog;
