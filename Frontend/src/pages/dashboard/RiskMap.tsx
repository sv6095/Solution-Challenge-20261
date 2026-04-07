import { useEffect, useId, useState } from "react";
import { Loader2 } from "lucide-react";
import type MapLibreGL from "maplibre-gl";
import {
  Map,
  MapMarker,
  MarkerContent,
  MarkerPopup,
  MarkerLabel,
  MapControls,
  useMap,
  type MapViewport,
} from "@/components/ui/map";
import { useRiskEvents, useRiskSuppliers } from "@/hooks/use-dashboard";

// ─── Heatmap layer config ──────────────────────────────────────────────────

const RISK_HEATMAP_COLORS = ["#fff7bc", "#fee391", "#fec44f", "#fe9929", "#d7301f"];
const HEATMAP_COLOR_STOPS: [number, string][] = [
  [0.15, RISK_HEATMAP_COLORS[0]],
  [0.35, RISK_HEATMAP_COLORS[1]],
  [0.55, RISK_HEATMAP_COLORS[2]],
  [0.75, RISK_HEATMAP_COLORS[3]],
  [1,    RISK_HEATMAP_COLORS[4]],
];

const TIER_OPTIONS     = ["All", "Tier 1", "Tier 2", "Tier 3"];
const SEVERITY_OPTIONS = ["All", "CRITICAL", "HIGH", "MEDIUM", "LOW"];

// ─── Heatmap layer (risk-event GeoJSON) ────────────────────────────────────

interface RiskEvent {
  id: string;
  lat: number;
  lng: number;
  severity: string;
  title: string;
  region: string;
  description: string;
}

function RiskHeatmapLayers({ events }: { events: RiskEvent[] }) {
  const { map, isLoaded } = useMap();
  const id = useId();
  const sourceId    = `risk-heatmap-source-${id}`;
  const heatLayerId = `risk-heatmap-layer-${id}`;
  const pointLayerId = `risk-heatmap-point-${id}`;

  useEffect(() => {
    if (!map || !isLoaded) return;

    const geojson: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: events.map((ev) => ({
        type: "Feature",
        properties: { severity: ev.severity },
        geometry: { type: "Point", coordinates: [ev.lng, ev.lat] },
      })),
    };

    if (!map.getSource(sourceId)) {
      map.addSource(sourceId, { type: "geojson", data: geojson });
    } else {
      (map.getSource(sourceId) as maplibregl.GeoJSONSource).setData(geojson);
    }

    if (!map.getLayer(heatLayerId)) {
      map.addLayer({
        id: heatLayerId,
        type: "heatmap",
        source: sourceId,
        maxzoom: 7,
        paint: {
          "heatmap-weight":     ["interpolate", ["linear"], ["zoom"], 0, 0.4, 6, 1],
          "heatmap-intensity":  ["interpolate", ["linear"], ["zoom"], 0, 0.6, 6, 1.4],
          "heatmap-color": [
            "interpolate", ["linear"], ["heatmap-density"],
            0, "rgba(220,38,38,0)",
            ...HEATMAP_COLOR_STOPS.flat(),
          ],
          "heatmap-radius":   ["interpolate", ["linear"], ["zoom"], 0, 18, 6, 42],
          "heatmap-opacity":  ["interpolate", ["linear"], ["zoom"], 4, 0.8, 7, 0.1],
        },
      });
    }

    if (!map.getLayer(pointLayerId)) {
      map.addLayer({
        id: pointLayerId,
        type: "circle",
        source: sourceId,
        minzoom: 4,
        paint: {
          "circle-radius":       ["interpolate", ["linear"], ["get", "severity"], 1, 4, 6, 12],
          "circle-color":        "#dc2626",
          "circle-stroke-width": 1.5,
          "circle-stroke-color": "rgba(255,255,255,0.8)",
          "circle-opacity":      ["interpolate", ["linear"], ["zoom"], 4, 0, 7, 0.9],
        },
      });
    }

    return () => {
      try {
        if (map.getLayer(pointLayerId)) map.removeLayer(pointLayerId);
        if (map.getLayer(heatLayerId))  map.removeLayer(heatLayerId);
        if (map.getSource(sourceId))    map.removeSource(sourceId);
      } catch { /* ignore */ }
    };
  }, [map, isLoaded, events, sourceId, heatLayerId, pointLayerId]);

  return null;
}

// ─── Main component ─────────────────────────────────────────────────────────

const RiskMap = () => {
  const [tierFilter,     setTierFilter]     = useState("All");
  const [severityFilter, setSeverityFilter] = useState("All");
  const [exposureRange,  setExposureRange]  = useState(100);
  const [activeLayers,   setActiveLayers]   = useState({ Suppliers: true, "Risk Events": true, "Logistics Routes": false });
  const [selectedSupplier, setSelectedSupplier] = useState<string | null>(null);

  const [viewport, setViewport] = useState<MapViewport>({
    center: [20, 20],
    zoom: 2,
    bearing: 0,
    pitch: 0,
  });

  const { data: events,    isLoading: eventsLoading } = useRiskEvents({
    severity: severityFilter !== "All" ? severityFilter : undefined,
  });
  const { data: suppliers, isLoading: suppLoading }   = useRiskSuppliers({
    tier: tierFilter !== "All" ? tierFilter : undefined,
    maxScore: exposureRange,
  });

  const selectedSupplierData = suppliers?.find((s) => s.id === selectedSupplier);
  const toggleLayer = (name: string) =>
    setActiveLayers((prev) => ({ ...prev, [name]: !prev[name as keyof typeof activeLayers] }));

  return (
    <div className="flex gap-4 h-[calc(100vh-8rem)]">
      {/* Map area */}
      <div className="flex-1 relative surface-container-high rounded-lg overflow-hidden">
        <Map
          viewport={viewport}
          onViewportChange={setViewport}
          className="absolute inset-0"
          projection={{ type: "globe" }}
          pitch={12}
          minZoom={1.2}
          maxZoom={10}
        >
          <MapControls position="bottom-right" showZoom showCompass />

          {/* Risk heatmap layer */}
          {activeLayers["Risk Events"] && events && (
            <RiskHeatmapLayers events={events} />
          )}

          {/* Supplier Markers */}
          {activeLayers["Suppliers"] &&
            suppliers?.map((s) => (
              <MapMarker
                key={s.id}
                longitude={s.lng}
                latitude={s.lat}
                onClick={() => setSelectedSupplier(s.id === selectedSupplier ? null : s.id)}
              >
                <MarkerContent>
                  <div className={`w-4 h-4 rounded-sm border-2 border-white shadow-lg cursor-pointer hover:scale-125 transition-transform ${
                    s.exposureScore > 70 ? "bg-sentinel" : s.exposureScore > 50 ? "bg-yellow-500" : "bg-green-500"
                  }`} />
                  <MarkerLabel position="bottom">{s.name}</MarkerLabel>
                </MarkerContent>
                <MarkerPopup>
                  <div className="space-y-1 min-w-[160px]">
                    <p className="font-headline font-bold text-sm">{s.name}</p>
                    <p className="text-label-sm text-secondary">{s.location}</p>
                    <span className="text-label-sm font-bold">Score: {s.exposureScore.toFixed(1)}</span>
                  </div>
                </MarkerPopup>
              </MapMarker>
            ))}
        </Map>

        {/* Layer Toggles */}
        <div className="absolute top-4 left-4 glass-panel rounded-lg p-4 w-52 z-10">
          <h3 className="font-headline font-bold text-sm uppercase tracking-widest mb-3">Layer Toggles</h3>
          {Object.entries(activeLayers).map(([layer, active]) => (
            <label key={layer} className="flex items-center justify-between py-2 text-body-md text-secondary cursor-pointer">
              {layer}
              <button
                type="button"
                data-state={active ? "checked" : "unchecked"}
                onClick={() => toggleLayer(layer)}
                className={`w-9 h-5 rounded-full relative transition-colors ${active ? "bg-sentinel" : "bg-surface-highest"}`}
              >
                <div className={`w-4 h-4 rounded-full bg-foreground absolute top-0.5 transition-all ${active ? "left-4" : "left-0.5"}`} />
              </button>
            </label>
          ))}
        </div>

        {/* Heatmap Legend */}
        <div className="absolute top-4 right-16 glass-panel rounded-lg p-3 z-10 w-44">
          <p className="text-label-sm uppercase tracking-widest mb-2 font-bold">Risk Density</p>
          <div className="flex gap-1 mb-1">
            {RISK_HEATMAP_COLORS.map((c) => (
              <span key={c} className="flex-1 h-2 rounded-full" ref={(el) => { if (el) el.style.backgroundColor = c; }} />
            ))}
          </div>
          <div className="flex justify-between text-label-sm text-secondary">
            <span>Low</span><span>High</span>
          </div>
        </div>

        {/* Filters */}
        <div className="absolute top-44 left-4 glass-panel rounded-lg p-4 w-52 z-10 space-y-4">
          <h3 className="font-headline font-bold text-sm uppercase tracking-widest">Filters</h3>

          <div>
            <p className="text-label-sm text-secondary uppercase tracking-widest mb-2">Severity</p>
            <select
              title="Filter by severity"
              aria-label="Filter by severity"
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value)}
              className="w-full glass-panel px-2 py-1.5 rounded-sm text-label-sm bg-transparent text-foreground"
            >
              {SEVERITY_OPTIONS.map((s) => <option key={s}>{s}</option>)}
            </select>
          </div>

          <div>
            <p className="text-label-sm text-secondary uppercase tracking-widest mb-2">Supplier Tier</p>
            <div className="flex flex-wrap gap-1">
              {TIER_OPTIONS.map((t) => (
                <button
                  key={t}
                  onClick={() => setTierFilter(t)}
                  className={`px-2 py-1 rounded-sm text-label-sm ${tierFilter === t ? "bg-sentinel text-background" : "glass-panel text-secondary"}`}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          <div>
            <p className="text-label-sm text-secondary uppercase tracking-widest mb-2">Max Exposure</p>
            <input
              type="range"
              title="Maximum Exposure Range"
              aria-label="Maximum Exposure Range"
              min="0" max="100"
              value={exposureRange}
              onChange={(e) => setExposureRange(Number(e.target.value))}
              className="w-full accent-sentinel-red"
            />
            <div className="flex justify-between text-label-sm text-secondary mt-1">
              <span>0</span><span className="text-sentinel font-bold">{exposureRange}</span>
            </div>
          </div>
        </div>

        {/* Viewport HUD */}
        <div className="absolute bottom-12 left-4 glass-panel rounded-sm px-3 py-1.5 font-mono text-xs z-10">
          <span>{viewport.center[1].toFixed(3)}°N, {viewport.center[0].toFixed(3)}°E</span>
          <span className="ml-3 text-secondary">z{viewport.zoom.toFixed(1)}</span>
        </div>

        {/* Status bar */}
        <div className="absolute bottom-0 left-0 right-0 px-4 py-2 glass-panel flex items-center justify-between z-10">
          <span className="text-label-sm text-sentinel uppercase tracking-widest flex items-center gap-2">
            {eventsLoading || suppLoading ? <Loader2 size={12} className="animate-spin" /> : <span className="w-2 h-2 bg-sentinel rounded-full animate-pulse-glow" />}
            {eventsLoading ? "Loading…" : `${events?.length ?? 0} Events · ${suppliers?.length ?? 0} Nodes`}
          </span>
          <div className="w-16 h-1 bg-sentinel rounded-full" />
        </div>
      </div>

      {/* Right detail panel */}
      <div className="w-80 space-y-4 overflow-y-auto">
        {selectedSupplierData ? (
          <>
            <div className="surface-container-high rounded-lg p-6">
              <h2 className="font-headline text-xl font-bold">{selectedSupplierData.name}</h2>
              <p className="text-body-md text-secondary">{selectedSupplierData.location} · Node ID: {selectedSupplierData.id}</p>
              <div className="surface-container rounded-lg p-4 mt-4">
                <p className="text-label-sm text-secondary uppercase tracking-widest">Exposure Score</p>
                <div className="flex items-baseline gap-2 mt-1">
                  <span className="font-headline text-4xl font-bold">{selectedSupplierData.exposureScore.toFixed(1)}</span>
                  <span className={`text-body-md ${selectedSupplierData.trend === "up" ? "text-sentinel" : selectedSupplierData.trend === "down" ? "text-green-500" : "text-secondary"}`}>
                    {selectedSupplierData.trend === "up" ? "↑" : selectedSupplierData.trend === "down" ? "↓" : "→"}
                  </span>
                </div>
                <div className="h-1 bg-sentinel rounded-full mt-2" ref={(el) => { if (el) el.style.width = `${selectedSupplierData.exposureScore}%`; }} />
              </div>
              <div className="mt-4 grid grid-cols-2 gap-2">
                <span className="glass-panel px-2 py-1 rounded-sm text-label-sm text-center">{selectedSupplierData.tier}</span>
                <span className="glass-panel px-2 py-1 rounded-sm text-label-sm text-center">{selectedSupplierData.category}</span>
              </div>
            </div>
            <button onClick={() => setSelectedSupplier(null)} className="w-full glass-panel py-3 rounded-sm font-medium hover:bg-white/10 transition-colors">
              Close Panel
            </button>
          </>
        ) : (
          <div className="surface-container-high rounded-lg p-6 text-center text-secondary text-body-md">
            <p>Click a supplier marker on the map to see details.</p>
          </div>
        )}

        {/* Events list */}
        <div className="surface-container-high rounded-lg p-6">
          <h3 className="font-headline font-bold text-sm uppercase tracking-widest mb-4">Active Events</h3>
          {eventsLoading ? (
            <div className="flex justify-center"><Loader2 className="animate-spin text-secondary" /></div>
          ) : (
            <div className="space-y-3 max-h-80 overflow-y-auto">
              {events?.slice(0, 5).map((ev) => (
                <button
                  key={ev.id}
                  onClick={() => setViewport((v) => ({ ...v, center: [ev.lng, ev.lat], zoom: 6 }))}
                  className="w-full text-left surface-container rounded-lg p-3 relative hover:bg-surface-highest/30 transition-colors"
                >
                  <div className={`absolute left-0 top-0 bottom-0 w-1 rounded-l ${ev.severity === "CRITICAL" ? "bg-sentinel" : "bg-yellow-500"}`} />
                  <p className="font-headline font-bold text-xs">{ev.title}</p>
                  <p className="text-label-sm text-secondary mt-0.5">{ev.region}</p>
                </button>
              ))}
            </div>
          )}
        </div>

        <button className="w-full glass-panel py-3 rounded-sm font-medium hover:bg-white/10 transition-colors">
          Generate Risk Report
        </button>
      </div>
    </div>
  );
};

export default RiskMap;
