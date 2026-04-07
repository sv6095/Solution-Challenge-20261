import { useEffect, useMemo, useState } from "react";
import { Clock3, Loader2, Route as RouteIcon, Ship, Plane, Truck, UserRound } from "lucide-react";
import {
  Map,
  MapMarker,
  MapRoute,
  MarkerContent,
  MarkerTooltip,
  MapControls,
} from "@/components/ui/map";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";

// ─── Types ──────────────────────────────────────────────────────────────────

interface OsrmRoute {
  coordinates: [number, number][];
  duration: number;
  distance: number;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmt(seconds: number) {
  const m = Math.round(seconds / 60);
  if (m < 60) return `${m} min`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

function fmtDist(m: number) {
  return m < 1000 ? `${Math.round(m)} m` : `${(m / 1000).toFixed(1)} km`;
}

function formatDistance(meters?: number) {
  if (!meters) return "--";
  return fmtDist(meters);
}

function formatDuration(seconds?: number) {
  if (!seconds) return "--";
  return fmt(seconds);
}

const MODES = [
  { id: "Sea",   icon: Ship  },
  { id: "Land",  icon: Truck },
  { id: "Air",   icon: Plane },
  { id: "Multi", icon: RouteIcon },
];

// ─── Sample cargo manifest ────────────────────────────────────────────────────

const CARGO_MANIFEST = [
  { name: "Industrial Bearings (SKF)", qty: 4800, unit: "units", value: "$142,000" },
  { name: "Semiconductor Wafers",      qty: 120,  unit: "lots",  value: "$890,000" },
  { name: "Rare-Earth Magnets",        qty: 2.4,  unit: "MT",    value: "$58,000"  },
];

// ─── Geocoding ────────────────────────────────────────────────────────────────

const geocode = async (query: string): Promise<[number, number] | null> => {
  try {
    const res  = await fetch(`https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(query)}&format=json&limit=1`);
    const data = await res.json();
    if (data[0]) return [parseFloat(data[0].lon), parseFloat(data[0].lat)];
  } catch { /* ignore */ }
  return null;
};

// ─── Component ────────────────────────────────────────────────────────────────

const RouteIntelligence = () => {
  const [origin,      setOrigin]      = useState("Shenzhen, China");
  const [destination, setDestination] = useState("Rotterdam, Netherlands");
  const [originCoords, setOriginCoords] = useState<[number, number] | null>(null);
  const [destCoords,   setDestCoords]   = useState<[number, number] | null>(null);
  const [mode,         setMode]         = useState("Sea");
  const [avoidZones,   setAvoidZones]   = useState<string[]>([]);
  const [avoidInput,   setAvoidInput]   = useState("");
  const [routes,       setRoutes]       = useState<OsrmRoute[]>([]);
  const [selectedIdx,  setSelectedIdx]  = useState(0);
  const [fetching,     setFetching]     = useState(false);
  const [error,        setError]        = useState<string | null>(null);

  const findRoutes = async () => {
    if (!origin || !destination) return;
    setFetching(true);
    setError(null);
    setRoutes([]);

    const [oCoords, dCoords] = await Promise.all([geocode(origin), geocode(destination)]);
    if (!oCoords || !dCoords) {
      setError("Could not geocode one or both locations. Try a more specific place name.");
      setFetching(false);
      return;
    }

    setOriginCoords(oCoords);
    setDestCoords(dCoords);

    try {
      const data = await api.routes.osrm(oCoords, dCoords);
      if (data.routes?.length) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        setRoutes(data.routes.map((r: any) => ({
          coordinates: r.geometry.coordinates,
          duration:    r.duration,
          distance:    r.distance,
        })));
        setSelectedIdx(0);
      } else {
        setError("No routes found between these locations.");
      }
    } catch {
      setError("Failed to fetch routes. Please try again.");
    } finally {
      setFetching(false);
    }
  };

  // Auto-fetch on first render with default route
  useEffect(() => { findRoutes(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const sortedRoutes = routes
    .map((r, i) => ({ r, i }))
    .sort((a, b) => (a.i === selectedIdx ? 1 : b.i === selectedIdx ? -1 : 0));

  const activeRoute = routes[selectedIdx];

  // Courier progress (62% along the selected route)
  const progressCoordinates = useMemo(() => {
    const coords = activeRoute?.coordinates ?? [];
    const count  = Math.max(2, Math.floor(coords.length * 0.62));
    return coords.slice(0, count);
  }, [activeRoute]);

  const courierPosition = progressCoordinates[progressCoordinates.length - 1];

  const mapCenter: [number, number] =
    originCoords && destCoords
      ? [(originCoords[0] + destCoords[0]) / 2, (originCoords[1] + destCoords[1]) / 2]
      : [30, 30];

  return (
    <div>
      <h1 className="font-headline text-3xl font-bold tracking-tight-sentinel mb-2">Route Intelligence</h1>
      <p className="text-body-md text-secondary mb-8">Dynamic corridor optimization with real-time routing via OSRM.</p>

      {/* Main delivery-tracker layout */}
      <div className="surface-container-high rounded-lg border border-surface-highest overflow-hidden grid lg:grid-cols-[1.05fr_1fr] min-h-[600px]">

        {/* ── Left: controls + manifest ── */}
        <div className="flex flex-col p-6 space-y-6 overflow-y-auto">

          {/* Route parameters */}
          <div className="space-y-4">
            <h3 className="font-headline font-bold text-sm uppercase tracking-widest">Route Parameters</h3>

            <div className="grid gap-3">
              <div>
                <label htmlFor="origin-input" className="text-label-sm text-secondary uppercase tracking-widest block mb-2">Origin Node</label>
                <input
                  id="origin-input"
                  placeholder="e.g. Shenzhen, China"
                  value={origin}
                  onChange={(e) => setOrigin(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && findRoutes()}
                  className="input-sentinel w-full px-4 py-3 rounded-sm"
                />
              </div>
              <div>
                <label htmlFor="destination-input" className="text-label-sm text-secondary uppercase tracking-widest block mb-2">Destination</label>
                <input
                  id="destination-input"
                  placeholder="e.g. Rotterdam, Netherlands"
                  value={destination}
                  onChange={(e) => setDestination(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && findRoutes()}
                  className="input-sentinel w-full px-4 py-3 rounded-sm"
                />
              </div>
            </div>

            {/* Mode selector */}
            <div>
              <p className="text-label-sm text-secondary uppercase tracking-widest mb-2">Transport Mode</p>
              <div className="flex gap-2">
                {MODES.map(({ id, icon: Icon }) => (
                  <button
                    key={id}
                    onClick={() => setMode(id)}
                    className={`flex-1 flex flex-col items-center gap-1 py-2 rounded-sm text-label-sm transition-colors ${id === mode ? "bg-sentinel text-background" : "glass-panel text-secondary hover:bg-white/10"}`}
                  >
                    <Icon size={14} />
                    {id}
                  </button>
                ))}
              </div>
            </div>

            {/* Avoid zones */}
            <div>
              <label htmlFor="avoid-input" className="text-label-sm text-secondary uppercase tracking-widest block mb-2">Avoid Risk Zones</label>
              <div className="glass-panel px-3 py-2 rounded-sm flex flex-wrap gap-1 mb-2 min-h-[36px]">
                {avoidZones.map((z) => (
                  <span
                    key={z}
                    className="bg-sentinel/20 text-sentinel px-2 py-0.5 rounded-sm text-label-sm cursor-pointer hover:bg-sentinel/30"
                    onClick={() => setAvoidZones((z2) => z2.filter((x) => x !== z))}
                  >
                    {z} ✕
                  </span>
                ))}
              </div>
              <input
                id="avoid-input"
                placeholder="Type zone and press Enter"
                value={avoidInput}
                onChange={(e) => setAvoidInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && avoidInput.trim()) {
                    setAvoidZones((z) => [...z, avoidInput.trim()]);
                    setAvoidInput("");
                  }
                }}
                className="input-sentinel w-full px-4 py-2 rounded-sm text-label-sm"
              />
            </div>

            <button
              onClick={findRoutes}
              disabled={!origin || !destination || fetching}
              className="w-full bg-foreground text-background py-3 rounded-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-40 flex items-center justify-center gap-2"
            >
              {fetching ? <><Loader2 size={16} className="animate-spin" /> Routing…</> : "Find Routes"}
            </button>
            {error && <p className="text-sentinel text-label-sm text-center">{error}</p>}
          </div>

          {/* Cargo manifest */}
          <Card className="bg-surface-highest border-surface-highest">
            <CardHeader>
              <CardTitle className="font-headline text-sm uppercase tracking-widest font-bold">
                Cargo Manifest ({CARGO_MANIFEST.length} items)
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {CARGO_MANIFEST.map((item) => (
                <div key={item.name} className="flex items-center gap-3">
                  <div className="glass-panel w-8 h-8 rounded-sm flex items-center justify-center shrink-0">
                    <Truck size={12} className="text-secondary" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium font-headline truncate">{item.name}</p>
                    <p className="text-label-sm text-secondary">{item.qty} {item.unit}</p>
                  </div>
                  <Badge variant="secondary" className="shrink-0">{item.value}</Badge>
                </div>
              ))}
              <div className="border-t border-surface pt-3 flex justify-between text-sm">
                <span className="text-secondary">Total Value</span>
                <span className="font-bold font-headline">$1,090,000</span>
              </div>
            </CardContent>
          </Card>

          {/* Route summary cards */}
          {activeRoute && (
            <div className="grid grid-cols-2 gap-3">
              <Card className="bg-surface-highest border-surface-highest">
                <CardContent className="pt-4 space-y-1">
                  <p className="text-label-sm text-secondary">ETA</p>
                  <p className="font-headline font-bold text-lg flex items-center gap-1.5">
                    <Clock3 size={14} className="text-secondary" />
                    {formatDuration(activeRoute.duration)}
                  </p>
                </CardContent>
              </Card>
              <Card className="bg-surface-highest border-surface-highest">
                <CardContent className="pt-4 space-y-1">
                  <p className="text-label-sm text-secondary">Distance</p>
                  <p className="font-headline font-bold text-lg flex items-center gap-1.5">
                    <RouteIcon size={14} className="text-secondary" />
                    {formatDistance(activeRoute.distance)}
                  </p>
                </CardContent>
              </Card>
            </div>
          )}

          {/* Actions */}
          <div className="flex flex-wrap gap-2 pt-1">
            <Button size="sm" className="gap-1.5 bg-sentinel text-background hover:opacity-90">
              <Clock3 className="size-4" /> View Timeline
            </Button>
            <Button variant="outline" size="sm" className="gap-1.5 glass-panel border-surface-highest">
              <UserRound className="size-4" /> Contact Agent
            </Button>
          </div>
        </div>

        {/* ── Right: map ── */}
        <div className="relative min-h-[400px] overflow-hidden">
          <Map
            loading={fetching}
            center={mapCenter}
            zoom={originCoords ? 3 : 2}
            className="absolute inset-0"
            styles={{
              light: "https://tiles.openfreemap.org/styles/bright",
              dark:  "https://tiles.openfreemap.org/styles/dark",
            }}
          >
            <MapControls position="top-right" showZoom showCompass />

            {/* Full route (ghost) */}
            {sortedRoutes.map(({ r, i }) => (
              <MapRoute
                key={i}
                coordinates={r.coordinates}
                color={i === selectedIdx ? "#4d7c8a" : "#94a3b8"}
                width={i === selectedIdx ? 5 : 3}
                opacity={i === selectedIdx ? 0.35 : 0.2}
                onClick={() => setSelectedIdx(i)}
              />
            ))}

            {/* Progress route (live) */}
            {progressCoordinates.length >= 2 && (
              <MapRoute
                id="route-progress"
                coordinates={progressCoordinates}
                color="#FF0000"
                width={5}
                opacity={0.95}
                interactive={false}
              />
            )}

            {/* Courier position */}
            {courierPosition && (
              <MapMarker longitude={courierPosition[0]} latitude={courierPosition[1]} offset={[0, 10]}>
                <MarkerContent>
                  <div className="relative grid size-9 place-items-center rounded-full bg-emerald-500 border-2 border-white shadow-lg">
                    <Ship className="size-4 text-white" />
                  </div>
                </MarkerContent>
                <MarkerTooltip>
                  <div className="space-y-0.5 text-xs">
                    <p className="font-medium">Order {formatDuration(activeRoute?.duration)} away</p>
                    <p className="opacity-70">Route {formatDistance(activeRoute?.distance)}</p>
                  </div>
                </MarkerTooltip>
              </MapMarker>
            )}

            {/* Origin marker */}
            {originCoords && (
              <MapMarker longitude={originCoords[0]} latitude={originCoords[1]}>
                <MarkerContent>
                  <div className="size-5 rounded-full bg-green-500 border-2 border-white shadow-lg" />
                </MarkerContent>
                <MarkerTooltip>{origin || "Origin"}</MarkerTooltip>
              </MapMarker>
            )}

            {/* Destination marker */}
            {destCoords && (
              <MapMarker longitude={destCoords[0]} latitude={destCoords[1]}>
                <MarkerContent>
                  <div className="size-5 rounded-full bg-sentinel border-2 border-white shadow-lg" />
                </MarkerContent>
                <MarkerTooltip>{destination || "Destination"}</MarkerTooltip>
              </MapMarker>
            )}
          </Map>
        </div>
      </div>

      {/* Route comparison cards */}
      {routes.length > 0 && (
        <div className="flex flex-col gap-2 mt-4">
          {routes.map((r, i) => (
            <button
              key={i}
              onClick={() => setSelectedIdx(i)}
              className={`surface-container-high rounded-lg p-5 flex items-center justify-between text-left transition-all ${i === selectedIdx ? "ring-1 ring-sentinel" : ""}`}
            >
              <div className="flex items-center gap-3">
                <span className={`font-headline text-lg font-bold ${i === selectedIdx ? "text-sentinel" : ""}`}>Route {i + 1}</span>
                {i === 0 && <span className="bg-green-500/20 text-green-400 px-2 py-0.5 rounded-sm text-label-sm">Fastest</span>}
                {i === selectedIdx && i !== 0 && <span className="bg-sentinel/20 text-sentinel px-2 py-0.5 rounded-sm text-label-sm">Selected</span>}
              </div>
              <div className="flex items-center gap-8 text-body-md">
                <div className="flex items-center gap-1.5">
                  <Clock3 size={14} className="text-secondary" />
                  <span className="font-bold">{fmt(r.duration)}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <RouteIcon size={14} className="text-secondary" />
                  <span className="font-bold">{fmtDist(r.distance)}</span>
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

export default RouteIntelligence;
