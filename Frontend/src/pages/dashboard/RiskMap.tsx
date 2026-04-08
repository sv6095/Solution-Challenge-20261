import { useMemo } from "react";
import { Heatmap } from "@mapcn/heatmap";
import { useRiskEvents } from "@/hooks/use-dashboard";

const RiskMap = () => {
  const { data: events } = useRiskEvents();

  const heatData = useMemo(
    () =>
      (events ?? []).map((e) => ({
        lng: e.lng,
        lat: e.lat,
        severity_score:
          e.severity === "CRITICAL" ? 100 : e.severity === "HIGH" ? 75 : e.severity === "MEDIUM" ? 50 : 25,
      })),
    [events],
  );

  return (
    <div className="space-y-4">
      <h1 className="font-headline text-3xl font-bold tracking-tight-sentinel">Risk Map</h1>
      <p className="text-body-md text-secondary">Live risk events and supplier exposure from backend datasets.</p>
      <div className="surface-container-high rounded-lg p-3 min-h-[640px]">
        <Heatmap data={heatData} intensity="severity_score" />
      </div>
    </div>
  );
};

export default RiskMap;
