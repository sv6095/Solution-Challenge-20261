import { useState } from "react";
import { Loader2 } from "lucide-react";
import { useAuditLog } from "@/hooks/use-dashboard";
import { api } from "@/lib/api";

const AuditLog = () => {
  const { data: logs, isLoading } = useAuditLog();

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

      <div className="surface-container-high rounded-lg p-6">
        <div className="grid grid-cols-7 gap-2 text-label-sm text-secondary uppercase tracking-widest mb-4 px-2">
          <span>Log ID</span>
          <span>Event</span>
          <span>Supplier(s)</span>
          <span>Decision</span>
          <span>Executed By</span>
          <span>Timestamp</span>
          <span>Duration</span>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-12"><Loader2 className="animate-spin text-secondary" /></div>
        ) : logs?.length === 0 ? (
          <p className="text-body-md text-secondary text-center py-12">No audit records yet.</p>
        ) : (
          logs?.map((l) => (
            <div key={l.id} className="grid grid-cols-7 gap-2 items-center px-2 py-4 hover:bg-surface-highest/30 rounded-sm transition-colors">
              <span className="font-headline font-bold text-sm">{l.id}</span>
              <span className="text-body-md">{l.event}</span>
              <span className="text-body-md text-secondary">{l.suppliers}</span>
              <span className="text-body-md">{l.decision}</span>
              <span className="text-body-md text-secondary">{l.executedBy}</span>
              <span className="text-label-sm text-secondary">{l.timestamp}</span>
              <div className="flex items-center gap-2">
                <span className="font-headline font-bold text-sm text-sentinel">
                  {(l.durationMs / 1000).toFixed(1)}s
                </span>
                <a
                  href={api.audit.exportPdf(l.id)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sentinel text-label-sm hover:underline"
                  title="Download PDF"
                >
                  📄 PDF
                </a>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default AuditLog;
