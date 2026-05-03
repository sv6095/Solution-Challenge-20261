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
    <div className="border-border bg-black/90 absolute top-4 left-4 z-20 flex items-center gap-3 rounded-sm border px-3 py-2">
      <div className="flex items-center gap-4 text-[10px] uppercase font-bold tracking-wider">
        <div className="flex items-center gap-1.5">
          <span
            className="h-1.5 w-3 shrink-0"
            ref={(el) => { if (el) el.style.backgroundColor = modeConfig.air.color; }}
          />
          <span className="text-secondary">{modeConfig.air.label}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span
            className="h-1.5 w-3 shrink-0"
            ref={(el) => { if (el) el.style.backgroundColor = modeConfig.ground.color; }}
          />
          <span className="text-secondary">{modeConfig.ground.label}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span
            className="h-1.5 w-3 shrink-0"
            ref={(el) => { if (el) el.style.backgroundColor = statusConfig.delayed.color; }}
          />
          <span className="text-secondary">{statusConfig.delayed.label}</span>
        </div>
        <div className="bg-border h-3 w-px mx-1" />
        <div className="flex items-center gap-1.5">
          <div className="size-2 shrink-0 border border-black bg-white" />
          <span className="text-white">Hub</span>
        </div>
      </div>
    </div>
  );
}

export function NetworkMap({ hubs, routes }: NetworkMapProps) {
  return (
    <div className="relative h-full bg-black">
      <MapControlsCard />

      <Map center={[-98, 39]} zoom={4} projection={{ type: "globe" }} theme="light">
        <MapControls />
        <MapArcs hubs={hubs} routes={routes} />

        {hubs.map((hub) => (
          <MapMarker key={hub.id} longitude={hub.lng} latitude={hub.lat}>
            <MarkerContent>
              <div className="size-2 bg-white border border-black" />
            </MarkerContent>
            <MarkerTooltip
              offset={12}
              className="bg-black text-white border border-border p-2 rounded-none"
            >
              <p className="text-xs font-bold uppercase tracking-wider">{hub.city}</p>
              <p className="text-[10px] text-secondary mt-1 uppercase">
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

