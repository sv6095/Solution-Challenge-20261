import { useState, useEffect } from "react";
import { CheckCircle, Circle, Zap, FileText, Loader2 } from "lucide-react";
import { useDashboardEvents, useRiskSuppliers } from "@/hooks/use-dashboard";
import { useWorkflowEvent } from "@/hooks/use-workflow-event";

const STAGES = ["DETECT", "ASSESS", "DECIDE", "ACT", "AUDIT"];

const WorkflowEngine = () => {
  const [currentStage, setCurrentStage] = useState(1);
  const { data: events, isLoading: eLoading } = useDashboardEvents();
  const { data: suppliers, isLoading: sLoading } = useRiskSuppliers();
  const workflowEvent = useWorkflowEvent("demo-workflow-001");

  useEffect(() => {
    if (!workflowEvent?.stage) return;
    const stageIndex = STAGES.findIndex((s) => s.toLowerCase() === workflowEvent.stage?.toLowerCase());
    if (stageIndex >= 0) {
      setCurrentStage(stageIndex);
    }
  }, [workflowEvent?.stage]);

  // Advance to DETECT when we have a critical event
  const activeEvent = events?.find((e) => e.severity === "CRITICAL") ?? events?.[0];
  const affectedSuppliers = suppliers?.filter((s) => s.exposureScore > 60).slice(0, 3);

  return (
    <div>
      {/* Stage Progress */}
      <div className="flex items-center justify-between mb-10 max-w-3xl mx-auto">
        {STAGES.map((stage, i) => (
          <div key={stage} className="flex items-center gap-2">
            <button
              onClick={() => setCurrentStage(i)}
              className={`flex items-center justify-center w-10 h-10 rounded-full transition-all ${
                i < currentStage ? "bg-surface-highest text-foreground" :
                i === currentStage ? "bg-sentinel text-background sentinel-glow" :
                "bg-surface-high text-secondary"
              }`}
              title={stage}
              aria-label={stage}
            >
              {i < currentStage ? <CheckCircle size={18} /> : <Circle size={18} />}
            </button>
            <span className={`text-label-sm uppercase tracking-widest hidden md:block ${i === currentStage ? "text-sentinel font-bold" : "text-secondary"}`}>
              {stage}
            </span>
            {i < STAGES.length - 1 && <div className="w-12 lg:w-24 h-px bg-border mx-2" />}
          </div>
        ))}
      </div>

      <div className="grid lg:grid-cols-[1fr_1fr] gap-6">
        {/* Left: AI Analysis */}
        <div className="space-y-4">
          <div className="surface-container-high rounded-lg p-6 relative">
            <div className="absolute left-0 top-0 bottom-0 w-1 rounded-l bg-sentinel" />
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 bg-sentinel/20 rounded-lg flex items-center justify-center">
                <Zap size={20} className="text-sentinel" />
              </div>
              <div>
                <h2 className="font-headline text-xl font-bold">
                  {currentStage === 0 ? "Detecting signals…" :
                   currentStage === 1 ? "Gemini is analyzing…" :
                   currentStage === 2 ? "Deciding optimal response…" :
                   currentStage === 3 ? "Executing actions…" :
                   "Audit complete"}
                </h2>
                <p className="text-body-md text-secondary">
                  {currentStage <= 1 ? "Deep-scanning multi-tier nodes" :
                   currentStage === 2 ? "Evaluating risk mitigation options" :
                   currentStage === 3 ? "Dispatching workflows" :
                   "Review workflow execution record"}
                </p>
              </div>
            </div>
            <div className="h-px bg-border my-4" />
            {eLoading ? (
              <div className="flex justify-center py-4"><Loader2 className="animate-spin text-secondary" /></div>
            ) : activeEvent ? (
              <p className="text-body-md text-secondary leading-relaxed">{activeEvent.description}</p>
            ) : (
              <p className="text-body-md text-secondary leading-relaxed">No critical events detected. All systems nominal.</p>
            )}
          </div>

          {/* Live Incident Stream */}
          <div className="surface-container-high rounded-lg p-6">
            <span className="text-label-sm text-secondary uppercase tracking-widest">Live Incident Stream</span>
            {eLoading ? (
              <div className="mt-3 flex justify-center"><Loader2 className="animate-spin text-secondary" /></div>
            ) : events?.slice(0, 3).map((ev) => (
              <div key={ev.id} className="surface-container rounded-lg p-4 mt-3 relative">
                <div className={`absolute left-0 top-0 bottom-0 w-1 rounded-l ${ev.severity === "CRITICAL" || ev.severity === "HIGH" ? "bg-sentinel" : "bg-yellow-500"}`} />
                <div className="flex items-center gap-2 mb-1">
                  <span className={ev.severity === "CRITICAL" ? "text-sentinel" : "text-yellow-500"}>▲</span>
                  <h3 className="font-headline font-bold text-sm">{ev.title}</h3>
                </div>
                <p className="text-body-md text-secondary">{ev.description}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Right: Impact + Suppliers */}
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="surface-container-high rounded-lg p-6 relative">
              <div className="absolute left-0 top-0 bottom-0 w-1 rounded-l bg-sentinel" />
              <div className="flex items-center justify-between mb-2">
                <span className="text-sentinel">📊</span>
                <span className="glass-panel px-2 py-0.5 rounded-sm text-label-sm">Estimated</span>
              </div>
              <p className="text-label-sm text-secondary uppercase tracking-widest">Supplier Exposure</p>
              <p className="font-headline text-3xl font-bold mt-1">
                {sLoading ? "—" : `${affectedSuppliers?.length ?? 0} nodes`}
              </p>
              <p className="text-label-sm text-secondary mt-1">above 60% threshold</p>
            </div>

            <div className="surface-container-high rounded-lg p-6 relative">
              <div className="absolute left-0 top-0 bottom-0 w-1 rounded-l bg-sentinel" />
              <div className="flex items-center justify-between mb-2">
                <span className="text-sentinel">⚠</span>
                <span className="glass-panel px-2 py-0.5 rounded-sm text-label-sm text-sentinel">
                  {eLoading ? "…" : (events?.filter((e) => e.severity === "CRITICAL")?.length ?? 0) > 0 ? "Critical" : "Moderate"}
                </span>
              </div>
              <p className="text-label-sm text-secondary uppercase tracking-widest">Active Events</p>
              <p className="font-headline text-3xl font-bold mt-1">
                {eLoading ? "—" : events?.length ?? 0}
              </p>
              <p className="text-body-md text-secondary mt-2">Across {new Set(events?.map((e) => e.region)).size ?? 0} regions.</p>
            </div>
          </div>

          {/* Affected Suppliers */}
          <div className="surface-container-high rounded-lg p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-headline font-bold text-lg">High Exposure Nodes</h3>
              <span className="text-label-sm text-secondary uppercase tracking-widest">
                {sLoading ? "…" : `${affectedSuppliers?.length ?? 0} Nodes`}
              </span>
            </div>
            {sLoading ? (
              <div className="flex justify-center py-4"><Loader2 className="animate-spin text-secondary" /></div>
            ) : affectedSuppliers?.length === 0 ? (
              <p className="text-body-md text-secondary text-center py-4">No high-exposure suppliers.</p>
            ) : (
              <div className="space-y-3">
                {affectedSuppliers?.map((s) => (
                  <div key={s.id} className="flex items-center justify-between py-3">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 surface-container-highest rounded-sm flex items-center justify-center">
                        <FileText size={14} className="text-secondary" />
                      </div>
                      <div>
                        <p className="font-headline font-bold text-sm">{s.name}</p>
                        <p className="text-label-sm text-secondary">{s.location} · {s.tier}</p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className={`text-body-md font-bold ${s.exposureScore > 75 ? "text-sentinel" : "text-yellow-500"}`}>
                        {s.exposureScore > 75 ? "Critical Impact" : "Moderate Risk"}
                      </p>
                      <p className="text-label-sm text-secondary">Score: {s.exposureScore.toFixed(1)}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <button
            onClick={() => setCurrentStage((s) => Math.min(s + 1, STAGES.length - 1))}
            disabled={currentStage >= STAGES.length - 1}
            className="w-full bg-foreground text-background py-3 rounded-sm font-medium flex items-center justify-center gap-2 hover:opacity-90 transition-opacity disabled:opacity-40"
          >
            {currentStage >= STAGES.length - 1 ? "Workflow Complete ✓" : `Advance to ${STAGES[currentStage + 1]} →`}
          </button>
        </div>
      </div>
    </div>
  );
};

export default WorkflowEngine;
