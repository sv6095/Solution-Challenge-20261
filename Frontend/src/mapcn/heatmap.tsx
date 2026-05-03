import { useEffect, useId, useMemo } from "react";
import maplibregl from "maplibre-gl";
import type MapLibreGL from "maplibre-gl";
import { Map, MapControls, useMap } from "@/components/ui/map";

type HeatPoint = {
  lat?: number;
  lng?: number;
  severity_score?: number;
  id?: string;
  title?: string;
  description?: string;
  severity?: string;
};

type Props = {
  data?: HeatPoint[];
  intensity?: string;
  criticalNodes?: Array<{
    lat?: number;
    lng?: number;
    score?: number;
  }>;
  onSelectRisk?: (risk: HeatPoint) => void;
};

const HEATMAP_GRADIENT_COLORS = [
  "rgba(220, 38, 38, 0)",    /* Transparent */
  "rgba(220, 38, 38, 0.15)", /* Muted red */
  "rgba(220, 38, 38, 0.4)",  /* Semi-transparent red */
  "rgba(220, 38, 38, 0.7)",  /* Solid red */
  "#DC2626",                 /* Pure red accent */
];

function HeatmapLayers({
  data,
  criticalNodes,
  onSelectRisk,
}: {
  data: HeatPoint[];
  criticalNodes: Array<{ lat?: number; lng?: number; score?: number }>;
  onSelectRisk?: (risk: HeatPoint) => void;
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
            id: p.id || `risk_${idx + 1}`,
            title: p.title || `Risk signal #${idx + 1}`,
            description: p.description || `Estimated disruption intensity ${(Number(p.severity_score) || 25).toFixed(1)} / 100`,
            severity: p.severity || "",
            lat: Number(p.lat),
            lng: Number(p.lng),
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
          "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 2, 0.5, 8, 1.2],
          "heatmap-color": [
            "interpolate",
            ["linear"],
            ["heatmap-density"],
            0,
            "rgba(220, 38, 38, 0)",
            0.2,
            HEATMAP_GRADIENT_COLORS[1],
            0.4,
            HEATMAP_GRADIENT_COLORS[2],
            0.7,
            HEATMAP_GRADIENT_COLORS[3],
            1,
            HEATMAP_GRADIENT_COLORS[4],
          ],
          "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 2, 8, 8, 32],
          "heatmap-opacity": ["interpolate", ["linear"], ["zoom"], 2, 0.8, 8, 0.15],
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
          "circle-radius": ["interpolate", ["linear"], ["get", "intensity"], 20, 5, 100, 10],
          "circle-color": ["interpolate", ["linear"], ["get", "intensity"], 20, "#555555", 60, "#FFFFFF", 100, "#DC2626"],
          "circle-stroke-color": "#000000",
          "circle-stroke-width": 1,
          "circle-opacity": 0.9,
        },
      });
    }

    const infoPopup = new maplibregl.Popup({ closeButton: false, closeOnClick: true });
    const onCriticalClick = (e: MapLibreGL.MapMouseEvent & { features?: MapLibreGL.MapGeoJSONFeature[] }) => {
      const feature = e.features?.[0];
      if (!feature) return;
      const coords = (feature.geometry as GeoJSON.Point).coordinates as [number, number];
      const intensity = Number(feature.properties?.intensity || 0);
      if (onSelectRisk) {
        onSelectRisk({
          id: String(feature.properties?.id || ""),
          title: String(feature.properties?.title || ""),
          description: String(feature.properties?.description || ""),
          severity: String(feature.properties?.severity || ""),
          lat: Number(feature.properties?.lat),
          lng: Number(feature.properties?.lng),
          severity_score: intensity,
        });
      }
      infoPopup
        .setLngLat(coords)
        .setHTML(
          `<div style="font-family:monospace;font-size:11px;line-height:1.5;color:#FFFFFF;background:#080808;border:1px solid #DC2626;padding:12px;max-width:240px;box-shadow:0 0 20px rgba(220,38,38,0.2)">
            <div style="font-weight:700;margin-bottom:8px;text-transform:uppercase;letter-spacing:0.1em;color:#DC2626;border-bottom:1px solid #333;padding-bottom:4px">
              [ANALYSIS_ID: ${String(feature.properties?.id || "N/A").toUpperCase()}]
            </div>
            <div style="font-weight:600;margin-bottom:6px;color:#FFF;text-transform:uppercase">${String(feature.properties?.title || "RISK SIGNAL")}</div>
            <div style="color:#cbd5e1;margin-bottom:10px">${String(feature.properties?.description || "")}</div>
            <div style="display:flex;justify-content:space-between;align-items:center;background:#111;padding:4px 8px;border:1px solid #222">
              <span style="color:#94a3b8">INTENSITY</span>
              <span style="color:#DC2626;font-weight:bold">${intensity.toFixed(1)} / 100</span>
            </div>
            <div style="margin-top:8px;text-align:right">
              <span style="color:#DC2626;font-size:9px;animate:flicker 0.3s infinite opacity">● ACTIVE_MONITOR</span>
            </div>
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
  }, [criticalGeojson, criticalLayerId, criticalSourceId, heatLayerId, isLoaded, map, onSelectRisk, riskGeojson, sourceId]);

  return null;
}

export function Heatmap({ data = [], intensity = "severity_score", criticalNodes = [], onSelectRisk }: Props) {
  const validPoints = data.filter((p) => p.lat !== undefined && p.lng !== undefined);
  const effectiveCriticalNodes = criticalNodes.length
    ? criticalNodes
    : validPoints.map((point) => ({
        lat: point.lat,
        lng: point.lng,
        score: Number(point[intensity as keyof HeatPoint] ?? point.severity_score ?? 50),
      }));
  const fallback = criticalNodes.find((n) => n.lat !== undefined && n.lng !== undefined);
  const center: [number, number] = validPoints.length > 0
    ? [Number(validPoints[0].lng), Number(validPoints[0].lat)]
    : fallback
      ? [Number(fallback.lng), Number(fallback.lat)]
      : [103.8198, 1.3521];

  return (
    <div className="relative h-full w-full border border-border overflow-hidden">
      <Map center={center} zoom={3.2} projection={{ type: "globe" }}>
        <MapControls showZoom />
        <HeatmapLayers data={validPoints} criticalNodes={effectiveCriticalNodes} onSelectRisk={onSelectRisk} />
      </Map>
    </div>
  );
}

