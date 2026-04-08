"use client";

import { useEffect, useMemo, useState } from "react";
import { Clock3, Truck, UserRound } from "lucide-react";

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

interface OsrmRouteData {
  coordinates: [number, number][];
  duration: number;
  distance: number;
}

type TransportMode = "sea" | "land" | "air" | "multi";

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
  { id: "land", label: "Land", icon: Truck, speedFactor: 1, progress: 0.62, routeColor: "#3b82f6" },
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

const RouteIntelligence = () => {
  const [routes, setRoutes] = useState<OsrmRouteData[]>([]);
  const [selectedRouteIdx, setSelectedRouteIdx] = useState(0);
  const [loading, setLoading] = useState(true);
  const [mode] = useState<TransportMode>("land");
  const [originQuery, setOriginQuery] = useState("Daly City, California");
  const [destinationQuery, setDestinationQuery] = useState("San Francisco, California");
  const [originPoint, setOriginPoint] = useState(DEFAULT_PICKUP);
  const [destinationPoint, setDestinationPoint] = useState(DEFAULT_DROPOFF);
  const [mapCenter, setMapCenter] = useState<[number, number]>([DEFAULT_PICKUP.lng, DEFAULT_PICKUP.lat]);
  const [mapZoom, setMapZoom] = useState(12);
  const [routeError, setRouteError] = useState<string | null>(null);

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
    setLoading(true);
    setRouteError(null);
    try {
      const response = await fetch(
        `https://router.project-osrm.org/route/v1/driving/${from.lng},${from.lat};${to.lng},${to.lat}?overview=full&geometries=geojson&alternatives=true&steps=false`,
      );
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
      await fetchRoute(originGeo, destinationGeo);
    } catch (error) {
      console.error("Failed to geocode selected places:", error);
      setRouteError("Location search failed. Please try again.");
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRoute();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const progressCoordinates = useMemo(() => {
    const activeMode = MODE_OPTIONS.find((m) => m.id === mode) ?? MODE_OPTIONS[0];
    const activeRoute = routes[selectedRouteIdx];
    const progressCount = Math.max(
      2,
      Math.floor(
        (activeRoute?.coordinates?.length ?? 0) * (activeRoute ? activeMode.progress : 0.66),
      ),
    );
    return activeRoute?.coordinates?.slice(0, progressCount) ?? [];
  }, [mode, routes, selectedRouteIdx]);

  const courierPosition = progressCoordinates[progressCoordinates.length - 1];
  const activeMode = MODE_OPTIONS.find((m) => m.id === mode) ?? MODE_OPTIONS[0];
  const activeRoute = routes[selectedRouteIdx];
  const adjustedDuration = activeRoute ? activeRoute.duration * activeMode.speedFactor : undefined;

  return (
    <div>
      <h1 className="font-headline text-3xl font-bold tracking-tight-sentinel mb-2">Route Intelligence</h1>
      <p className="text-body-md text-secondary mb-8">Dynamic land corridor optimization with live map updates.</p>
      <div className="surface-container-high mx-auto grid max-w-7xl rounded-lg border border-surface-highest md:h-[600px] md:grid-cols-[1.05fr_1fr]">
        <div className="flex flex-col p-5 md:p-6">
          <div className="space-y-1">
            <h3 className="text-2xl font-semibold tracking-tight">
              Track Delivery
            </h3>
            <p className="text-muted-foreground text-sm">Mon Feb 10 - 2-3 PM</p>
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
                className="w-full"
                onClick={rerouteWithSelectedPlaces}
                disabled={loading}
              >
                Update route
              </Button>
              {routeError && <p className="text-xs text-sentinel">{routeError}</p>}
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
                return (
                  <button
                    key={opt.id}
                    className={`flex items-center justify-center gap-1.5 rounded-md border px-2 py-2 text-xs transition-colors ${
                      selected ? "border-primary bg-primary/10 text-primary" : "hover:bg-muted"
                    }`}
                  >
                    <Icon className="size-3.5" />
                    {opt.label}
                  </button>
                );
              })}
            </CardContent>
          </Card>

          <div className="mt-6 flex flex-wrap items-center gap-2">
            <Button size="sm" className="gap-1.5">
              <Clock3 className="size-4" />
              View timeline
            </Button>
            <Button variant="outline" size="sm" className="gap-1.5">
              <UserRound className="size-4" />
              Contact courier
            </Button>
          </div>

          {!!routes.length && (
            <Card className="mt-4 bg-surface-highest border-surface-highest">
              <CardHeader>
                <CardTitle className="font-medium">Route options ({routes.length})</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {routes.map((r, idx) => (
                  <button
                    key={`route-option-${idx}`}
                    onClick={() => setSelectedRouteIdx(idx)}
                    className={`w-full rounded-md border px-3 py-2 text-left text-sm transition-colors ${
                      idx === selectedRouteIdx ? "border-primary bg-primary/10" : "hover:bg-muted"
                    }`}
                  >
                    Option {idx + 1} - {formatDistance(r.distance)} - {formatDuration(r.duration)}
                  </button>
                ))}
              </CardContent>
            </Card>
          )}
        </div>

        <div className="relative h-[400px] overflow-hidden rounded-xl shadow-sm md:h-full">
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
            <MapRoute
              id="delivery-full-route"
              coordinates={activeRoute?.coordinates ?? []}
              color="#5b6572"
              width={5.2}
              opacity={0.3}
              interactive={false}
            />
            {routes.map((r, idx) => (
              <MapRoute
                key={`alt-route-${idx}`}
                id={`alt-route-${idx}`}
                coordinates={r.coordinates}
                color={idx === selectedRouteIdx ? activeMode.routeColor : "#64748b"}
                width={idx === selectedRouteIdx ? 6 : 3}
                opacity={idx === selectedRouteIdx ? 0.95 : 0.4}
                interactive={false}
              />
            ))}
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
