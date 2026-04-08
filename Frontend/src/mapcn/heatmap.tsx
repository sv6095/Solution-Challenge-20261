import { useEffect, useId, useMemo } from "react";
import type MapLibreGL from "maplibre-gl";
import { Map, MapControls, useMap } from "@/components/ui/map";

type HeatPoint = {
  lat?: number;
  lng?: number;
  severity_score?: number;
};

type Props = {
  data?: HeatPoint[];
  intensity?: string;
};

const HEATMAP_GRADIENT_COLORS = [
  "#fff7bc",
  "#fee391",
  "#fec44f",
  "#fe9929",
  "#d7301f",
];

function HeatmapLayers({ data }: { data: HeatPoint[] }) {
  const { map, isLoaded } = useMap();
  const id = useId();
  const sourceId = `risk-heat-source-${id}`;
  const heatLayerId = `risk-heat-layer-${id}`;
  const pointLayerId = `risk-point-layer-${id}`;

  const geojson = useMemo<GeoJSON.FeatureCollection<GeoJSON.Point>>(
    () => ({
      type: "FeatureCollection",
      features: data
        .filter((p) => typeof p.lat === "number" && typeof p.lng === "number")
        .map((p) => ({
          type: "Feature",
          properties: { intensity: Number(p.severity_score) || 25 },
          geometry: { type: "Point", coordinates: [Number(p.lng), Number(p.lat)] },
        })),
    }),
    [data],
  );

  useEffect(() => {
    if (!map || !isLoaded) return;

    if (!map.getSource(sourceId)) {
      map.addSource(sourceId, { type: "geojson", data: geojson });
    } else {
      const src = map.getSource(sourceId) as MapLibreGL.GeoJSONSource;
      src.setData(geojson);
    }

    if (!map.getLayer(heatLayerId)) {
      map.addLayer({
        id: heatLayerId,
        type: "heatmap",
        source: sourceId,
        maxzoom: 8,
        paint: {
          "heatmap-weight": ["interpolate", ["linear"], ["get", "intensity"], 0, 0.05, 100, 1],
          "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 2, 0.6, 8, 1.4],
          "heatmap-color": [
            "interpolate",
            ["linear"],
            ["heatmap-density"],
            0,
            "rgba(255,255,255,0)",
            0.18,
            HEATMAP_GRADIENT_COLORS[0],
            0.38,
            HEATMAP_GRADIENT_COLORS[1],
            0.58,
            HEATMAP_GRADIENT_COLORS[2],
            0.78,
            HEATMAP_GRADIENT_COLORS[3],
            1,
            HEATMAP_GRADIENT_COLORS[4],
          ],
          "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 2, 12, 8, 40],
          "heatmap-opacity": ["interpolate", ["linear"], ["zoom"], 2, 0.95, 8, 0.25],
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
          "circle-radius": ["interpolate", ["linear"], ["get", "intensity"], 20, 4, 100, 11],
          "circle-color": [
            "interpolate",
            ["linear"],
            ["get", "intensity"],
            20,
            HEATMAP_GRADIENT_COLORS[1],
            60,
            HEATMAP_GRADIENT_COLORS[3],
            100,
            HEATMAP_GRADIENT_COLORS[4],
          ],
          "circle-stroke-color": "rgba(255,255,255,0.8)",
          "circle-stroke-width": 1,
          "circle-opacity": ["interpolate", ["linear"], ["zoom"], 4, 0, 8, 0.8],
        },
      });
    }

    return () => {
      try {
        if (map.getLayer(pointLayerId)) map.removeLayer(pointLayerId);
        if (map.getLayer(heatLayerId)) map.removeLayer(heatLayerId);
        if (map.getSource(sourceId)) map.removeSource(sourceId);
      } catch {
        // ignore
      }
    };
  }, [geojson, heatLayerId, isLoaded, map, pointLayerId, sourceId]);

  return null;
}

export function Heatmap({ data = [], intensity = "severity_score" }: Props) {
  const validPoints = data.filter((p) => p.lat !== undefined && p.lng !== undefined);
  const avg = validPoints.length > 0 ? validPoints.reduce((acc, p) => acc + (Number(p.severity_score) || 0), 0) / validPoints.length : 0;
  const center: [number, number] = validPoints.length > 0 ? [Number(validPoints[0].lng), Number(validPoints[0].lat)] : [103.8198, 1.3521];

  return (
    <div className="relative h-full w-full rounded-md border border-border overflow-hidden">
      <div className="absolute left-3 top-3 z-10 rounded bg-background/85 px-2 py-1 text-xs text-secondary">
        Risk Heatmap | Points: {validPoints.length} | Intensity: {intensity} | Avg: {avg.toFixed(1)}
      </div>
      <Map center={center} zoom={3.2} projection={{ type: "globe" }}>
        <MapControls showZoom />
        <HeatmapLayers data={validPoints} />
      </Map>
    </div>
  );
}
