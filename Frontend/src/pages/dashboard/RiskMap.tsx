import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Heatmap } from "@mapcn/heatmap";
import { useRiskEvents, useRiskSuppliers } from "@/hooks/use-dashboard";

const RiskMap = () => {
  const navigate = useNavigate();
  const { data: events } = useRiskEvents();
  const { data: suppliers } = useRiskSuppliers();
  const [modeFilter, setModeFilter] = useState<"all" | "sea" | "air" | "land">("all");

  const heatData = useMemo(
    () =>
      (events ?? [])
        .filter((e) => modeFilter === "all" ? true : String((e as any).mode || "").toLowerCase() === modeFilter)
        .map((e) => ({
          id: e.id,
          title: e.title,
          description: e.description,
          severity: e.severity,
          lng: e.lng,
          lat: e.lat,
          severity_score:
            e.severity === "CRITICAL" ? 100 : e.severity === "HIGH" ? 75 : e.severity === "MEDIUM" ? 50 : 25,
        })),
    [events, modeFilter],
  );

  const criticalNodes = useMemo(
    () =>
      (suppliers ?? [])
        .filter((s) => s.exposureScore >= 75)
        .map((s) => ({
          lat: s.lat,
          lng: s.lng,
          score: s.exposureScore,
        })),
    [suppliers],
  );

  return (
    <div className="space-y-4">
      <h1 className="font-headline text-3xl font-bold tracking-tight-sentinel">Risk Map</h1>
      <p className="text-body-md text-secondary">Live risk events and supplier exposure from backend datasets.</p>
      <div className="flex items-center gap-3">
        <div className="glass-panel px-3 py-2 rounded-sm">
          <select
            value={modeFilter}
            onChange={(e) => setModeFilter(e.target.value as any)}
            className="bg-transparent text-body-md text-foreground focus:outline-none"
          >
            <option value="all">All modes</option>
            <option value="sea">Sea</option>
            <option value="air">Air</option>
            <option value="land">Land</option>
          </select>
        </div>
        <p className="text-label-sm text-secondary uppercase tracking-widest">Click a risk signal to start workflow</p>
      </div>
      <div className="surface-container-high rounded-lg p-3 h-[640px]">
        <Heatmap
          data={heatData}
          criticalNodes={criticalNodes}
          intensity="severity_score"
          onSelectRisk={(risk) => {
            sessionStorage.setItem("preloaded_workflow_event", JSON.stringify({
              id: risk.id,
              title: risk.title,
              description: risk.description,
              severity: risk.severity,
              lat: risk.lat,
              lng: risk.lng,
              region: "",
              timestamp: new Date().toISOString(),
            }));
            navigate("/dashboard/routes?entry=risk_map");
          }}
        />
      </div>
    </div>
  );
};

export default RiskMap;
