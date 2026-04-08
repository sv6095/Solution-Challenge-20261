import { useEffect, useId, useMemo } from "react";
import maplibregl from "maplibre-gl";
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
  criticalNodes?: Array<{
    lat?: number;
    lng?: number;
    score?: number;
  }>;
};

const HEATMAP_GRADIENT_COLORS = [
  "#fff7bc",
  "#fee391",
  "#fec44f",
  "#fe9929",
  "#d7301f",
];

function HeatmapLayers({
  data,
  criticalNodes,
}: {
  data: HeatPoint[];
  criticalNodes: Array<{ lat?: number; lng?: number; score?: number }>;
}) {
  const { map, isLoaded } = useMap();
  const id = useId();
  const sourceId = `risk-heat-source-${id}`;
  const heatLayerId = `risk-heat-layer-${id}`;
  const criticalSourceId = `risk-critical-source-${id}`;
  const criticalLayerId = `risk-critical-layer-${id}`;

  const riskGeojson = useMemo<GeoJSON.FeatureCollection<GeoJSON.Point>>(
    () => ({
      type: "FeatureCollection",
      features: data
        .filter((p) => typeof p.lat === "number" && typeof p.lng === "number")
        .map((p, idx) => ({
          type: "Feature",
          properties: {
            intensity: Number(p.severity_score) || 25,
            title: `Risk signal #${idx + 1}`,
            description: `Estimated disruption intensity ${(Number(p.severity_score) || 25).toFixed(1)} / 100`,
          },
          geometry: { type: "Point", coordinates: [Number(p.lng), Number(p.lat)] },
        })),
    }),
    [data],
  );

  const criticalGeojson = useMemo<GeoJSON.FeatureCollection<GeoJSON.Point>>(
    () => ({
      type: "FeatureCollection",
      features: criticalNodes
        .filter((p) => typeof p.lat === "number" && typeof p.lng === "number")
        .map((p, idx) => ({
          type: "Feature",
          properties: {
            score: Number(p.score) || 75,
            title: `Critical node #${idx + 1}`,
            description: `Supplier exposure score ${(Number(p.score) || 75).toFixed(1)} / 100`,
          },
          geometry: { type: "Point", coordinates: [Number(p.lng), Number(p.lat)] },
        })),
    }),
    [criticalNodes],
  );

  useEffect(() => {
    if (!map || !isLoaded) return;

    // Use gradient heatmap for critical nodes (dense set)
    if (!map.getSource(sourceId)) {
      map.addSource(sourceId, { type: "geojson", data: criticalGeojson });
    } else {
      const src = map.getSource(sourceId) as MapLibreGL.GeoJSONSource;
      src.setData(criticalGeojson);
    }

    if (!map.getLayer(heatLayerId)) {
      map.addLayer({
        id: heatLayerId,
        type: "heatmap",
        source: sourceId,
        maxzoom: 8,
        paint: {
          "heatmap-weight": ["interpolate", ["linear"], ["get", "score"], 0, 0.05, 100, 1],
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

    // Use marker circles for natural catastrophe/geopolitical risks (sparser set)
    if (!map.getSource(criticalSourceId)) {
      map.addSource(criticalSourceId, { type: "geojson", data: riskGeojson });
    } else {
      const criticalSrc = map.getSource(criticalSourceId) as MapLibreGL.GeoJSONSource;
      criticalSrc.setData(riskGeojson);
    }

    if (!map.getLayer(criticalLayerId)) {
      map.addLayer({
        id: criticalLayerId,
        type: "circle",
        source: criticalSourceId,
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["get", "intensity"], 20, 6, 100, 12],
          "circle-color": ["interpolate", ["linear"], ["get", "intensity"], 20, "#22c55e", 60, "#f59e0b", 100, "#ef4444"],
          "circle-stroke-color": "rgba(255,255,255,0.95)",
          "circle-stroke-width": 2,
          "circle-opacity": 0.95,
        },
      });
    }

    const infoPopup = new maplibregl.Popup({ closeButton: true, closeOnClick: true });
    const onCriticalClick = (e: MapLibreGL.MapMouseEvent & { features?: MapLibreGL.MapGeoJSONFeature[] }) => {
      const feature = e.features?.[0];
      if (!feature) return;
      const coords = (feature.geometry as GeoJSON.Point).coordinates as [number, number];
      const intensity = Number(feature.properties?.intensity || 0);
      infoPopup
        .setLngLat(coords)
        .setHTML(
          `<div style="font-size:12px;line-height:1.35">
            <div style="font-weight:700;margin-bottom:4px">${String(feature.properties?.title || "Risk signal")}</div>
            <div>${String(feature.properties?.description || "")}</div>
            <div style="margin-top:4px;color:#9ca3af">Severity score: ${intensity.toFixed(1)}</div>
          </div>`,
        )
        .addTo(map);
    };
    const onEnter = () => {
      map.getCanvas().style.cursor = "pointer";
    };
    const onLeave = () => {
      map.getCanvas().style.cursor = "";
    };
    map.on("click", criticalLayerId, onCriticalClick);
    map.on("mouseenter", criticalLayerId, onEnter);
    map.on("mouseleave", criticalLayerId, onLeave);

    return () => {
      try {
        map.off("click", criticalLayerId, onCriticalClick);
        map.off("mouseenter", criticalLayerId, onEnter);
        map.off("mouseleave", criticalLayerId, onLeave);
        infoPopup.remove();
        if (map.getLayer(criticalLayerId)) map.removeLayer(criticalLayerId);
        if (map.getLayer(heatLayerId)) map.removeLayer(heatLayerId);
        if (map.getSource(criticalSourceId)) map.removeSource(criticalSourceId);
        if (map.getSource(sourceId)) map.removeSource(sourceId);
      } catch {
        // ignore
      }
    };
  }, [criticalGeojson, criticalLayerId, criticalSourceId, heatLayerId, isLoaded, map, riskGeojson, sourceId]);

  return null;
}

export function Heatmap({ data = [], intensity = "severity_score", criticalNodes = [] }: Props) {
  const validPoints = data.filter((p) => p.lat !== undefined && p.lng !== undefined);
  const avg = validPoints.length > 0 ? validPoints.reduce((acc, p) => acc + (Number(p.severity_score) || 0), 0) / validPoints.length : 0;
  const fallback = criticalNodes.find((n) => n.lat !== undefined && n.lng !== undefined);
  const center: [number, number] = validPoints.length > 0
    ? [Number(validPoints[0].lng), Number(validPoints[0].lat)]
    : fallback
      ? [Number(fallback.lng), Number(fallback.lat)]
      : [103.8198, 1.3521];

  return (
    <div className="relative h-full w-full rounded-md border border-border overflow-hidden">
      <div className="absolute left-3 top-3 z-10 rounded bg-background/85 px-2 py-1 text-xs text-secondary">
        Risk Heatmap | Risks: {validPoints.length} | Critical Nodes: {criticalNodes.length} | Intensity: {intensity} | Avg: {avg.toFixed(1)}
      </div>
      <Map center={center} zoom={3.2} projection={{ type: "globe" }}>
        <MapControls showZoom />
        <HeatmapLayers data={validPoints} criticalNodes={criticalNodes} />
      </Map>
    </div>
  );
}
