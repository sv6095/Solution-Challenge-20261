import { type ReactNode } from "react";
import { Map, MapControls, MapMarker, MarkerContent, MarkerTooltip } from "@/components/ui/map";

type Node = {
  id: string;
  label?: string;
  exposure?: number;
  lng?: number;
  lat?: number;
};

type Props = {
  nodes?: Node[];
  edges?: unknown[];
  riskOverlay?: unknown;
  children?: ReactNode;
};

export function LogisticsNetwork({ nodes = [], riskOverlay }: Props) {
  const geoNodes = nodes.filter((n) => typeof n.lng === "number" && typeof n.lat === "number");
  const center: [number, number] =
    geoNodes.length > 0 ? [Number(geoNodes[0].lng), Number(geoNodes[0].lat)] : [103.8198, 1.3521];

  return (
    <div className="relative h-full w-full rounded-md border border-border overflow-hidden">
      <div className="absolute left-3 top-3 z-10 rounded bg-background/85 px-2 py-1 text-xs text-secondary">
        Logistics Network | Nodes: {nodes.length}
      </div>
      <div className="absolute right-3 top-3 z-10 rounded bg-background/85 px-2 py-1 text-xs text-secondary">
        Nodes: {nodes.length} | Overlay: {JSON.stringify(riskOverlay ?? {})}
      </div>
      <Map center={center} zoom={2.2}>
        <MapControls showZoom />
        {geoNodes.map((n) => (
          <MapMarker key={n.id} longitude={Number(n.lng)} latitude={Number(n.lat)}>
            <MarkerContent>
              <div className="size-3 rounded-full border border-white bg-blue-500 shadow-md" />
            </MarkerContent>
            <MarkerTooltip className="text-xs">
              {(n.label ?? n.id) + (typeof n.exposure === "number" ? ` | Exposure ${n.exposure.toFixed(1)}` : "")}
            </MarkerTooltip>
          </MapMarker>
        ))}
      </Map>
      <div className="absolute bottom-3 left-3 right-3 z-10 rounded bg-background/85 px-3 py-2 text-xs text-secondary max-h-20 overflow-auto">
        {nodes.map((n) => (
          <div key={`list-${n.id}`}>
            {n.label ?? n.id} {typeof n.exposure === "number" ? `- ${n.exposure.toFixed(1)}` : ""}
          </div>
        ))}
      </div>
    </div>
  );
}
