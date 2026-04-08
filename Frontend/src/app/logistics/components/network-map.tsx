"use client";

import {
  Map,
  MapControls,
  MapMarker,
  MarkerContent,
  MarkerTooltip,
} from "@/components/ui/map";
import {
  modeConfig,
  regionLabels,
  statusConfig,
  type Hub,
  type Route,
} from "../data";
import { MapArcs } from "./map-arcs";
import { Separator } from "@/components/ui/separator";

interface NetworkMapProps {
  hubs: Hub[];
  routes: Route[];
}

function MapControlsCard() {
  return (
    <div className="border-border/40 bg-background/70 absolute top-4 left-4 z-20 flex items-center gap-3 rounded-lg border px-2.5 py-1.5 backdrop-blur-sm">
      <div className="flex items-center gap-3 text-xs">
        <div className="flex items-center gap-1.5">
          <span
            className="h-0.5 w-4 shrink-0 rounded-full"
            ref={(el) => { if (el) el.style.backgroundColor = modeConfig.air.color; }}
          />
          <span>{modeConfig.air.label}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span
            className="h-0.5 w-4 shrink-0 rounded-full"
            ref={(el) => { if (el) el.style.backgroundColor = modeConfig.ground.color; }}
          />
          <span>{modeConfig.ground.label}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span
            className="h-0.5 w-4 shrink-0 rounded-full"
            ref={(el) => { if (el) el.style.backgroundColor = statusConfig.delayed.color; }}
          />
          <span>{statusConfig.delayed.label}</span>
        </div>
        <div className="bg-border h-4 w-px" />
        <div className="flex items-center gap-1.5">
          <div className="size-2.5 shrink-0 rounded-full border border-white bg-blue-500 shadow-sm" />
          <span>Hub</span>
        </div>
      </div>
    </div>
  );
}

export function NetworkMap({ hubs, routes }: NetworkMapProps) {
  return (
    <div className="relative h-full">
      <MapControlsCard />

      <Map center={[-98, 39]} zoom={4} projection={{ type: "globe" }}>
        <MapControls />
        <MapArcs hubs={hubs} routes={routes} />

        {hubs.map((hub) => (
          <MapMarker key={hub.id} longitude={hub.lng} latitude={hub.lat}>
            <MarkerContent>
              <div className="size-3 rounded-full border-2 border-white bg-blue-500 shadow-md" />
            </MarkerContent>
            <MarkerTooltip
              offset={16}
              className="bg-background text-foreground border px-2.5 py-1.5"
            >
              <p className="font-medium">{hub.city}</p>
              <p className="text-muted-foreground mt-1">
                {hub.shipments.toLocaleString()} shipments
                <span className="mx-1">•</span>
                {regionLabels[hub.region]}
              </p>
            </MarkerTooltip>
          </MapMarker>
        ))}
      </Map>
    </div>
  );
}
