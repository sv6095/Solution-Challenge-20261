"use client";

import { useEffect, useMemo, useState } from "react";
import { Clock3, Truck, UserRound } from "lucide-react";

import WorkflowEngine from "@/pages/dashboard/WorkflowEngine";
import {
  Map,
  MapMarker,
  MapRoute,
  MarkerContent,
  MarkerTooltip,
} from "@/components/ui/map";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";

interface OsrmRouteData {
  coordinates: [number, number][];
  duration: number;
  distance: number;
}

type TransportMode = "sea" | "air" | "land" | "custom";

const DEFAULT_PICKUP = { lng: -122.466, lat: 37.716 };
const DEFAULT_DROPOFF = { lng: -122.399, lat: 37.683 };

const MODE_OPTIONS: Array<{
  id: TransportMode;
  label: string;
  icon: typeof Truck;
  speedFactor: number;
  progress: number;
  routeColor: string;
}> = [
  { id: "sea", label: "Sea", icon: Truck, speedFactor: 1.45, progress: 0.18, routeColor: "#0ea5e9" },
  { id: "air", label: "Air", icon: Truck, speedFactor: 0.62, progress: 0.48, routeColor: "#a855f7" },
  { id: "land", label: "Land", icon: Truck, speedFactor: 1, progress: 0.62, routeColor: "#ef4444" },
  { id: "custom", label: "Custom", icon: Truck, speedFactor: 1, progress: 0.55, routeColor: "#f59e0b" },
];

function formatDistance(meters?: number) {
  if (!meters) return "--";
  if (meters < 1000) return `${Math.round(meters)} m`;
  return `${(meters / 1000).toFixed(1)} km`;
}

function formatDuration(seconds?: number) {
  if (!seconds) return "--";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return `${hours}h ${remainingMinutes}m`;
}

function haversineMeters(a: { lat: number; lng: number }, b: { lat: number; lng: number }) {
  const R = 6371e3;
  const dLat = ((b.lat - a.lat) * Math.PI) / 180;
  const dLng = ((b.lng - a.lng) * Math.PI) / 180;
  const lat1 = (a.lat * Math.PI) / 180;
  const lat2 = (b.lat * Math.PI) / 180;
  const x =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.sin(dLng / 2) * Math.sin(dLng / 2) * Math.cos(lat1) * Math.cos(lat2);
  const c = 2 * Math.atan2(Math.sqrt(x), Math.sqrt(1 - x));
  return R * c;
}

const RouteIntelligence = () => {
  const [routes, setRoutes] = useState<OsrmRouteData[]>([]);
  const [selectedRouteIdx, setSelectedRouteIdx] = useState(0);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState<TransportMode>("land");
  const [originQuery, setOriginQuery] = useState("Daly City, California");
  const [destinationQuery, setDestinationQuery] = useState("San Francisco, California");
  const [originPoint, setOriginPoint] = useState(DEFAULT_PICKUP);
  const [destinationPoint, setDestinationPoint] = useState(DEFAULT_DROPOFF);
  const [mapCenter, setMapCenter] = useState<[number, number]>([DEFAULT_PICKUP.lng, DEFAULT_PICKUP.lat]);
  const [mapZoom, setMapZoom] = useState(12);
  const [routeError, setRouteError] = useState<string | null>(null);
  const [autoDetectedModes, setAutoDetectedModes] = useState<Array<"sea" | "air" | "land">>([]);

  const getViewportForCoordinates = (coordinates: [number, number][]) => {
    if (!coordinates.length) return { center: [destinationPoint.lng, destinationPoint.lat] as [number, number], zoom: 8 };
    const lons = coordinates.map(([lon]) => lon);
    const lats = coordinates.map(([, lat]) => lat);
    const minLon = Math.min(...lons);
    const maxLon = Math.max(...lons);
    const minLat = Math.min(...lats);
    const maxLat = Math.max(...lats);
    const center: [number, number] = [(minLon + maxLon) / 2, (minLat + maxLat) / 2];
    const span = Math.max(maxLon - minLon, maxLat - minLat);
    const zoom = span > 20 ? 3 : span > 10 ? 4 : span > 5 ? 5 : span > 2 ? 6 : span > 1 ? 7 : 8;
    return { center, zoom };
  };

  const geocodePlace = async (query: string) => {
    const runQuery = async (q: string) => {
      const response = await fetch(
        `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(q)}&format=json&limit=1`,
      );
      const data = (await response.json()) as Array<{ lat: string; lon: string }>;
      if (!data?.length) return null;
      return { lng: Number(data[0].lon), lat: Number(data[0].lat) };
    };

    const primary = await runQuery(query);
    if (primary) return primary;

    // Fallback for common short city queries like "mangalore", "kannur"
    return runQuery(`${query}, India`);
  };

  const fetchRoute = async (from = originPoint, to = destinationPoint) => {
    // STRICT: OSRM driving logic is for land only (and "custom" if land is one of the detected modes).
    const allowLandLogic = mode === "land" || (mode === "custom" && autoDetectedModes.includes("land"));
    if (!allowLandLogic) {
      setRoutes([]);
      setSelectedRouteIdx(0);
      setLoading(false);
      return;
    }
    setLoading(true);
    setRouteError(null);
    try {
      const baseUrl = `https://router.project-osrm.org/route/v1/driving/${from.lng},${from.lat};${to.lng},${to.lat}?overview=full&geometries=geojson&steps=false`;
      // Public OSRM demo server is strict; use alternatives=true (it may still return >2 on some corridors).
      let response = await fetch(`${baseUrl}&alternatives=true`);
      if (!response.ok) {
        // Fallback: no alternatives, just the best route
        response = await fetch(baseUrl);
      }
      const data = await response.json();
      const rawRoutes = (data?.routes ?? []) as Array<{
        geometry?: { coordinates?: [number, number][] };
        duration?: number;
        distance?: number;
      }>;
      const parsedRoutes = rawRoutes
        .filter((r) => r?.geometry?.coordinates?.length)
        .map((r) => ({
          coordinates: r.geometry!.coordinates!,
          duration: Number(r.duration ?? 0),
          distance: Number(r.distance ?? 0),
        }));
      if (!parsedRoutes.length) {
        setRouteError("No route found for selected places.");
        setRoutes([]);
        return;
      }

      setRoutes(parsedRoutes);
      setSelectedRouteIdx(0);
      const viewport = getViewportForCoordinates(parsedRoutes[0].coordinates);
      setMapCenter(viewport.center);
      setMapZoom(viewport.zoom);
    } catch (error) {
      console.error("Failed to fetch route:", error);
      setRouteError("Failed to fetch route. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const rerouteWithSelectedPlaces = async () => {
    setLoading(true);
    setRouteError(null);
    try {
      let originText = originQuery.trim();
      let destinationText = destinationQuery.trim();
      if (!destinationText && / to /i.test(originText)) {
        const parts = originText.split(/ to /i).map((p) => p.trim()).filter(Boolean);
        if (parts.length >= 2) {
          originText = parts[0];
          destinationText = parts.slice(1).join(" ");
          setOriginQuery(originText);
          setDestinationQuery(destinationText);
        }
      }

      const [originGeo, destinationGeo] = await Promise.all([
        geocodePlace(originText),
        geocodePlace(destinationText),
      ]);
      if (!originGeo || !destinationGeo) {
        setRouteError("Could not locate one or both places. Try adding state/country.");
        setLoading(false);
        return;
      }
      setOriginPoint(originGeo);
      setDestinationPoint(destinationGeo);
      // Always relocate map to the new corridor immediately (even if OSRM is disabled for the selected mode).
      setMapCenter([(originGeo.lng + destinationGeo.lng) / 2, (originGeo.lat + destinationGeo.lat) / 2]);
      setMapZoom(6);
      await fetchRoute(originGeo, destinationGeo);
    } catch (error) {
      console.error("Failed to geocode selected places:", error);
      setRouteError("Location search failed. Please try again.");
      setLoading(false);
    }
  };

  useEffect(() => {
    // Pull detected modes from the workflow report (written by WorkflowEngine).
    // This powers "Custom (2-3 auto detected)" without duplicating detection logic here.
    api.workflows
      .reportJson("demo-workflow-001")
      .then((r) => {
        const comparison = (r as any)?.decide?.route_comparison;
        const modes = Array.isArray(comparison)
          ? (comparison.map((x: any) => String(x?.mode || "").toLowerCase()).filter(Boolean) as string[])
          : [];
        const uniq = Array.from(new Set(modes)).filter((m) => m === "sea" || m === "air" || m === "land") as Array<
          "sea" | "air" | "land"
        >;
        setAutoDetectedModes(uniq);
      })
      .catch(() => setAutoDetectedModes([]))
      .finally(() => {
        fetchRoute();
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const allowLandLogic = mode === "land" || (mode === "custom" && autoDetectedModes.includes("land"));

  const displayedRoutes: OsrmRouteData[] = useMemo(() => {
    if (allowLandLogic) return routes;
    // For SEA/AIR (and Custom without land), show a simple corridor line so the map still explains the mode.
    const distance = haversineMeters(originPoint, destinationPoint);
    // Rough demo durations (seconds) — the workflow engine is the source of truth for real mode times/costs.
    const avgSpeedMps = mode === "air" ? 800_000 / 3600 : 26_000 / 3600; // 800 km/h or 26 km/h
    const duration = Math.max(1, Math.round(distance / Math.max(1, avgSpeedMps)));
    return [
      {
        coordinates: [
          [originPoint.lng, originPoint.lat],
          [destinationPoint.lng, destinationPoint.lat],
        ],
        duration,
        distance,
      },
    ];
  }, [allowLandLogic, destinationPoint.lat, destinationPoint.lng, mode, originPoint.lat, originPoint.lng, routes]);

  const progressCoordinates = useMemo(() => {
    const activeMode = MODE_OPTIONS.find((m) => m.id === mode) ?? MODE_OPTIONS[0];
    const activeRoute = displayedRoutes[selectedRouteIdx];
    const progressCount = Math.max(
      2,
      Math.floor(
        (activeRoute?.coordinates?.length ?? 0) * (activeRoute ? activeMode.progress : 0.66),
      ),
    );
    return activeRoute?.coordinates?.slice(0, progressCount) ?? [];
  }, [displayedRoutes, mode, selectedRouteIdx]);

  const courierPosition = progressCoordinates[progressCoordinates.length - 1];
  const activeMode = MODE_OPTIONS.find((m) => m.id === mode) ?? MODE_OPTIONS[0];
  const activeRoute = displayedRoutes[selectedRouteIdx];
  const adjustedDuration = activeRoute ? activeRoute.duration * activeMode.speedFactor : undefined;

  return (
    <div>
      {/* Merged OODA stepper header + pipeline */}
      <WorkflowEngine />

      <div className="mt-10">
        <h1 className="font-headline text-3xl font-bold tracking-tight-sentinel mb-2">Route Intelligence</h1>
        <p className="text-body-md text-secondary mb-8">
          Decision surface for disruption response: route comparison, execution, and audit.
        </p>
      </div>
      <div className="surface-container-high mx-auto grid max-w-7xl items-stretch overflow-hidden rounded-lg border border-surface-highest md:h-[620px] md:grid-cols-[0.9fr_1.3fr]">
        <div className="flex min-h-full h-full flex-col bg-surface-highest p-5 md:p-6 border-r border-surface-highest overflow-y-auto">
          <div className="space-y-1">
            <h3 className="text-2xl font-semibold tracking-tight">
              Optimized Route
            </h3>
            <p className="text-muted-foreground text-sm">
              {new Date().toLocaleString(undefined, {
                weekday: "short",
                year: "numeric",
                month: "short",
                day: "2-digit",
                hour: "2-digit",
                minute: "2-digit",
              })}
            </p>
          </div>

          <Card className="mt-4 bg-surface-highest border-surface-highest">
            <CardHeader>
              <CardTitle className="font-medium">Route selection</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <p className="text-muted-foreground mb-1 text-xs">Origin</p>
                <Input
                  value={originQuery}
                  onChange={(e) => setOriginQuery(e.target.value)}
                  placeholder="Enter origin"
                  onKeyDown={(e) => e.key === "Enter" && rerouteWithSelectedPlaces()}
                />
              </div>
              <div>
                <p className="text-muted-foreground mb-1 text-xs">Destination</p>
                <Input
                  value={destinationQuery}
                  onChange={(e) => setDestinationQuery(e.target.value)}
                  placeholder="Enter destination"
                  onKeyDown={(e) => e.key === "Enter" && rerouteWithSelectedPlaces()}
                />
              </div>
              <Button
                size="sm"
                className="w-full bg-sentinel text-background hover:opacity-90"
                onClick={rerouteWithSelectedPlaces}
                disabled={loading}
              >
                Update route
              </Button>
              {routeError && <p className="text-xs text-sentinel">{routeError}</p>}
              {mode !== "land" && !(mode === "custom" && autoDetectedModes.includes("land")) ? (
                <p className="text-xs text-secondary">
                  Land routing logic is disabled for this mode. Select <span className="text-sentinel">Land</span> or{" "}
                  <span className="text-sentinel">Custom</span> (when land is auto-detected) to compute OSRM route options.
                </p>
              ) : null}

              {/* Merge route alternatives into this left panel card */}
              {!!routes.length && allowLandLogic ? (
                <div className="pt-2">
                  <div className="flex items-center justify-between">
                    <p className="text-label-sm text-secondary uppercase tracking-widest">
                      Route options
                    </p>
                    <p className="text-xs text-secondary">
                      {routes.length} found
                    </p>
                  </div>
                  <div className="mt-2 rounded-md border border-border bg-surface-highest/40 max-h-[140px] overflow-auto">
                    <div className="p-2 space-y-2">
                      {routes.map((r, idx) => (
                        <button
                          key={`route-option-${idx}`}
                          type="button"
                          onClick={() => setSelectedRouteIdx(idx)}
                          className={`w-full rounded-md border px-3 py-2 text-left text-sm transition-colors ${
                            idx === selectedRouteIdx ? "border-sentinel bg-sentinel/10" : "border-border hover:bg-muted"
                          }`}
                        >
                          Option {idx + 1} - {formatDistance(r.distance)} - {formatDuration(r.duration)}
                        </button>
                      ))}
                    </div>
                  </div>
                  <p className="mt-2 text-xs text-secondary">
                    Showing all {routes.length} alternatives (scroll if needed).
                  </p>
                </div>
              ) : null}
            </CardContent>
          </Card>

          <Card className="mt-4 bg-surface-highest border-surface-highest">
            <CardHeader>
              <CardTitle className="font-medium">Transport mode</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {MODE_OPTIONS.map((opt) => {
                const Icon = opt.icon;
                const selected = mode === opt.id;
                const disabled =
                  opt.id === "custom" ? autoDetectedModes.length < 2 : false;
                return (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => setMode(opt.id)}
                    disabled={disabled}
                    className={`flex items-center justify-center gap-1.5 rounded-md border px-2 py-2 text-xs transition-colors ${
                      disabled
                        ? "opacity-40 cursor-not-allowed"
                        : selected
                          ? "border-sentinel bg-sentinel/10 text-sentinel"
                          : "hover:bg-muted"
                    }`}
                  >
                    <Icon className="size-3.5" />
                    {opt.id === "custom" && autoDetectedModes.length >= 2
                      ? `Custom (${autoDetectedModes.length} auto)`
                      : opt.label}
                  </button>
                );
              })}
            </CardContent>
          </Card>

          <div className="mt-5 flex flex-wrap items-center gap-2">
            <Button size="sm" className="gap-1.5 bg-sentinel text-background hover:opacity-90">
              <Clock3 className="size-4" />
              View timeline
            </Button>
            <Button variant="outline" size="sm" className="gap-1.5">
              <UserRound className="size-4" />
              Contact courier
            </Button>
          </div>

          {/* Route options are merged into Route selection card above */}
        </div>

        <div className="relative h-[420px] overflow-hidden rounded-xl shadow-sm md:h-full">
          <Map
            loading={loading}
            viewport={{ center: mapCenter, zoom: Math.min(mapZoom, 8) }}
            onViewportChange={(next) => {
              setMapCenter(next.center);
              setMapZoom(next.zoom);
            }}
            minZoom={3}
            maxZoom={16}
            styles={{
              light: "https://tiles.openfreemap.org/styles/bright",
              dark: "https://tiles.openfreemap.org/styles/dark",
            }}
          >
            {/* Legend */}
            <div className="absolute right-3 top-3 z-10 rounded-md border border-border bg-background/80 px-2 py-1 text-[10px] leading-tight text-secondary">
              <div className="text-[10px] text-secondary uppercase tracking-widest mb-1">Legend</div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="inline-flex items-center gap-1">
                  <span className="inline-block h-2 w-3 rounded-sm" style={{ background: "#ef4444" }} />
                  LAND
                </span>
                <span className="inline-flex items-center gap-1">
                  <span className="inline-block h-2 w-3 rounded-sm" style={{ background: "#0ea5e9" }} />
                  SEA
                </span>
                <span className="inline-flex items-center gap-1">
                  <span className="inline-block h-2 w-3 rounded-sm" style={{ background: "#a855f7" }} />
                  AIR
                </span>
                <span className="inline-flex items-center gap-1">
                  <span className="inline-block h-2 w-3 rounded-sm" style={{ background: "#f59e0b" }} />
                  CUSTOM
                </span>
                <span className="inline-flex items-center gap-1">
                  <span className="inline-block h-2 w-3 rounded-sm" style={{ background: "#22c55e" }} />
                  ALT
                </span>
              </div>
            </div>

            <MapRoute
              id="delivery-full-route"
              coordinates={activeRoute?.coordinates ?? []}
              color="#5b6572"
              width={5.2}
              opacity={0.3}
              interactive={false}
            />
            {displayedRoutes.map((r, idx) => {
              const selected = idx === selectedRouteIdx;
              const modeColor = activeMode.routeColor;
              const altColor = "#22c55e";
              return (
                <MapRoute
                  key={`alt-route-${idx}`}
                  id={`alt-route-${idx}`}
                  coordinates={r.coordinates}
                  color={selected ? modeColor : altColor}
                  width={selected ? 6 : 3}
                  opacity={selected ? 0.95 : 0.55}
                  interactive={false}
                />
              );
            })}
            <MapRoute
              id="delivery-progress-route"
              coordinates={progressCoordinates}
              color={activeMode.routeColor}
              width={6}
              opacity={0.95}
              interactive={false}
            />

            {courierPosition && (
              <MapMarker
                longitude={courierPosition[0]}
                latitude={courierPosition[1]}
                offset={[0, 10]}
              >
                <MarkerContent>
                  <div className="relative grid size-9 place-items-center rounded-full bg-emerald-500 dark:bg-emerald-600">
                    <Truck className="size-4 text-white" />
                  </div>
                </MarkerContent>
                <MarkerTooltip>
                  <div className="space-y-0.5 text-xs">
                    <p className="font-medium">
                      {activeMode.label} | ETA {formatDuration(adjustedDuration)}
                    </p>
                    <p className="text-background/70">
                      Route {formatDistance(activeRoute?.distance)}
                    </p>
                  </div>
                </MarkerTooltip>
              </MapMarker>
            )}

            <MapMarker longitude={originPoint.lng} latitude={originPoint.lat}>
              <MarkerContent>
                <div className="size-4 rounded-full border-2 border-white bg-emerald-500 shadow-sm" />
              </MarkerContent>
              <MarkerTooltip>Origin</MarkerTooltip>
            </MapMarker>

            <MapMarker longitude={destinationPoint.lng} latitude={destinationPoint.lat}>
              <MarkerContent>
                <div className="size-4 rounded-full border-2 border-white bg-rose-500 shadow-sm" />
              </MarkerContent>
              <MarkerTooltip>Destination</MarkerTooltip>
            </MapMarker>
          </Map>
        </div>
      </div>
    </div>
  );
};

export default RouteIntelligence;
