import { Map, MapControls, MapRoute } from "@/components/ui/map";

type Route = {
  mode?: string;
  duration?: number;
  distance?: number;
  coordinates?: [number, number][];
};

type Props = {
  routes?: Route[];
  activeMode?: string;
};

export function DeliveryTracker({ routes = [], activeMode = "sea" }: Props) {
  const firstWithCoords = routes.find((r) => Array.isArray(r.coordinates) && r.coordinates.length > 0);
  const center: [number, number] =
    firstWithCoords?.coordinates?.[0] ?? [103.8198, 1.3521];

  return (
    <div className="relative h-full w-full rounded-md border border-border overflow-hidden">
      <div className="absolute left-3 top-3 z-10 rounded bg-background/85 px-2 py-1 text-xs text-secondary">
        Delivery Tracker | Active mode: {activeMode}
      </div>
      <Map center={center} zoom={2.2}>
        <MapControls showZoom />
        {routes.map((r, i) => {
          const coords = r.coordinates ?? [];
          if (coords.length < 2) return null;
          const isActive = String(r.mode ?? "").toLowerCase().includes(activeMode.toLowerCase());
          return (
            <MapRoute
              key={`route-${i}`}
              id={`route-${i}`}
              coordinates={coords}
              color={isActive ? "#ef4444" : "#60a5fa"}
              width={isActive ? 4 : 2}
              opacity={isActive ? 0.95 : 0.65}
            />
          );
        })}
      </Map>
      <div className="absolute bottom-3 left-3 right-3 z-10 rounded bg-background/85 px-3 py-2 text-xs text-secondary max-h-24 overflow-auto">
        {routes.map((r, i) => (
          <div key={`meta-${i}`}>
            {String(r.mode ?? "route").toUpperCase()} - {Math.round((r.distance ?? 0) / 1000)} km - {Math.round((r.duration ?? 0) / 3600)}h
          </div>
        ))}
      </div>
    </div>
  );
}
