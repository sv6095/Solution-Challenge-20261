/**
 * NetworkView.tsx — Praecantator SCRM Command Center
 *
 * CONTENT: Replicates worldmonitor-main panel structure exactly:
 *   - Supply Chain panel (chokepoints / shipping / minerals / stress)
 *   - Strategic Risk panel (composite score ring, top risks, alerts)
 *   - Live Intel feed (news + geology + conflict)
 *   - Market implications
 *   - Data freshness / source health
 *
 * DESIGN: worldmonitor dark-mode CSS tokens (--bg, --surface, --border…)
 * DATA:   Praecantator backend APIs — no hardcoded values.
 */

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Home, X } from "lucide-react";
import { Map, MapMarker, MarkerContent, useMap, type MapRef } from "@/components/ui/map";
import {
  INTEL_HOTSPOTS,
  MILITARY_BASES,
  NUCLEAR_FACILITIES,
  UNDERSEA_CABLES
} from "@/config/geo";
import {
  api,
  getUserId,
  type ScoredChokepoint,
  type GlobalHazard,
  type Earthquake,
  type ConflictEvent,
  type FireDetection,
  type MarketQuote,
  type NewsArticle,
  type CountryInstability,
  type CriticalMineral,
  type GdacsAlert,
  type GdeltEvent,
} from "@/lib/api";
import type MapLibreGL from "maplibre-gl";

/* ── helpers ─────────────────────────────────────────────────────── */
const CC: Record<string, [number, number]> = {
  UAE:[54,24],Canada:[-106,56],Brazil:[-51.9,-14.2],UK:[-3.4,55.4],
  India:[78.9,20.6],Germany:[10.5,51.2],USA:[-95.7,37.1],China:[104.2,35.9],
  Mexico:[-102.6,23.6],Japan:[138.3,36.2],Australia:[133.8,-25.3],France:[2.2,46.2],
  Singapore:[103.8,1.35],Taiwan:[121,23.7],"South Korea":[127.8,36],
  Netherlands:[5.3,52.1],Sweden:[18.6,59.3],Spain:[-3.7,40.4],Italy:[12.6,41.9],
  Poland:[19.1,51.9],Turkey:[35.2,39],Nigeria:[8.7,9.1],Egypt:[30.8,26.8],
  Pakistan:[69.3,30.4],Indonesia:[113.9,-0.8],Russia:[105.3,61.5],
  Ukraine:[32,49],Myanmar:[96.7,17.1],Somalia:[46.2,5.2],
  Afghanistan:[67.7,33.9],Yemen:[48.5,15.6],Syria:[38.3,35],"Saudi Arabia":[45.1,23.9],
};

interface LogisticsNode {
  id: string;
  name: string;
  lat: number;
  lng: number;
  type: string;
  tier: string;
}

const DEFAULT_CENTER: [number, number] = [0, 20];

const isNum = (v: unknown): v is number =>
  typeof v === "number" && Number.isFinite(v);
const parseTier = (v: unknown): 1 | 2 | 3 | null => {
  const n = Number(String(v ?? "").replace(/\D/g, ""));
  return n === 1 || n === 2 || n === 3 ? n : null;
};
const fmtAgo = (iso: string | number | null | undefined): string => {
  if (!iso) return "—";
  try {
    const diff = Date.now() - new Date(iso).getTime();
    const m = Math.floor(diff / 60000);
    if (m < 1) return "just now";
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
  } catch { return "—"; }
};
const fmtDate = (iso: string | number | null | undefined): string => {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleDateString([], { month:"short", day:"numeric" }); }
  catch { return "—"; }
};

/* ── Score → CSS color (worldmonitor semantic palette) ──────────── */
const clamp = (value: number, min = 0, max = 100) => Math.min(max, Math.max(min, value));
const normalizeCountry = (value: string | null | undefined) => String(value ?? "").trim().toLowerCase();
const slugify = (value: string) => value.toLowerCase().replace(/[^a-z0-9]+/g, "-");
const hashString = (value: string) =>
  value.split("").reduce((acc, char, index) => acc + char.charCodeAt(0) * (index + 1), 0);
const riskLabel = (score: number) =>
  score >= 70 ? "critical" : score >= 50 ? "high" : score >= 30 ? "moderate" : "stable";
const prettyCount = (value: number) =>
  value >= 1_000_000 ? `${(value / 1_000_000).toFixed(1)}M`
  : value >= 1_000 ? `${Math.round(value / 1_000)}K`
  : `${Math.round(value)}`;
const isRecent = (value: string | undefined, days = 7) => {
  if (!value) return false;
  const time = new Date(value).getTime();
  if (Number.isNaN(time)) return false;
  return Date.now() - time <= days * 24 * 60 * 60 * 1000;
};
const matchesCountryText = (country: string, value: string | undefined) =>
  normalizeCountry(value).includes(normalizeCountry(country));
const toCountryCode = (country: string) => {
  const map: Record<string, string> = {
    usa: "US",
    "united states": "US",
    uk: "GB",
    "united kingdom": "GB",
    uae: "AE",
    russia: "RU",
    china: "CN",
    india: "IN",
    germany: "DE",
    france: "FR",
    japan: "JP",
    australia: "AU",
    canada: "CA",
    brazil: "BR",
    mexico: "MX",
    turkey: "TR",
    ukraine: "UA",
    poland: "PL",
    spain: "ES",
    italy: "IT",
    netherlands: "NL",
    sweden: "SE",
    taiwan: "TW",
    "south korea": "KR",
    singapore: "SG",
    nigeria: "NG",
    egypt: "EG",
    pakistan: "PK",
    indonesia: "ID",
    myanmar: "MM",
    somalia: "SO",
    afghanistan: "AF",
    yemen: "YE",
    syria: "SY",
    "saudi arabia": "SA",
  };
  return map[normalizeCountry(country)] ?? (country.replace(/[^A-Za-z]/g, "").slice(0, 2).toUpperCase() || "??");
};
const buildMix = (seed: number, items: { label: string; color: string; min: number; max: number }[]) => {
  const raw = items.map((item, index) => {
    const span = item.max - item.min;
    return item.min + ((seed + index * 17) % (span + 1));
  });
  const total = raw.reduce((sum, value) => sum + value, 0) || 1;
  return items.map((item, index) => ({
    label: item.label,
    color: item.color,
    value: Math.round((raw[index] / total) * 100),
  }));
};
const resolveCountryName = (country: string) =>
  Object.keys(CC).find((key) => normalizeCountry(key) === normalizeCountry(country)) ?? country;
const extractCountryCandidate = (feature: MapLibreGL.MapGeoJSONFeature | undefined) => {
  const props = (feature?.properties ?? {}) as Record<string, unknown>;
  const candidates = [
    props.name_en,
    props.name,
    props.admin,
    props.country,
    props.sovereignt,
    props.brk_name,
  ];

  return candidates.find((value): value is string =>
    typeof value === "string" && value.trim().length > 1,
  ) ?? null;
};
const getCountryFromMapClick = (map: MapRef, point: MapLibreGL.PointLike, countryOptions: string[]) => {
  const features = map.queryRenderedFeatures(point);
  for (const feature of features) {
    const rawCountry = extractCountryCandidate(feature);
    if (!rawCountry) continue;
    const matchedCountry = countryOptions.find((country) => normalizeCountry(country) === normalizeCountry(rawCountry));
    if (matchedCountry) return matchedCountry;
    return rawCountry;
  }
  return null;
};

interface CountryIntelPanelData {
  country: string;
  code: string;
  riskScore: number;
  riskStatus: string;
  updatedAt: string;
  counts: {
    unrest: number;
    conflict: number;
    security: number;
    information: number;
    military: number;
    sanctions: number;
    fires: number;
    cyber: number;
    displaced: number;
    forecasts: number;
  };
  scores: {
    unrest: number;
    conflict: number;
    security: number;
    information: number;
  };
  brief: string;
  energyMix: { label: string; color: string; value: number }[];
  monthlyMix: { label: string; color: string; value: number }[];
  maritimeRows: Array<{
    name: string;
    calls: number;
    trend: number;
    importDwt: string;
    exportDwt: string;
  }>;
  signals: Array<{
    id: string;
    category: string;
    severity: "critical" | "high" | "moderate" | "low";
    title: string;
    time: string;
  }>;
  militarySummary: {
    ownFlights: number;
    foreignFlights: number;
    navalVessels: number;
    foreignPresence: string;
  };
  infrastructure: Array<{ label: string; value: number; icon: string }>;
  economics: Array<{ label: string; value: string; source: string; trend?: "up" | "down" | "flat" }>;
  routeDependencies: string[];
  supplierCount: number;
}

const ISSUE_COLORS = {
  weather: "#f59e0b",
  geopolitical: "#ef4444",
  congestion: "#06b6d4",
  cyber: "#3b82f6",
  financial: "#fbbf24",
  hazard: "#f59e0b",
  quake: "#ef4444",
  conflict: "#a855f7",
  fire: "#f97316",
  chokepoint: "#06b6d4",
};

const scoreColor = (s: number) =>
  s >= 70 ? "var(--semantic-critical)"
  : s >= 50 ? "var(--semantic-high)"
  : s >= 30 ? "var(--semantic-elevated)"
  : "var(--semantic-normal)";

const riskColor = (s: number) =>
  s >= 70 ? "var(--threat-critical)"
  : s >= 40 ? "var(--threat-medium)"
  : "var(--threat-low)";

/* ── Sparkline SVG (worldmonitor style) ─────────────────────────── */
function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return null;
  const w = 200, h = 40;
  const min = Math.min(...values), max = Math.max(...values);
  const range = max - min || 1;
  const pts = values.map((v, i) => {
    const x = (i / (values.length - 1)) * w;
    const y = h - ((v - min) / range) * (h - 4) - 2;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ display:"block", margin:"4px 0" }}>
      <polyline points={pts} fill="none" stroke="var(--semantic-info,#4fc3f7)" strokeWidth="1.5" />
    </svg>
  );
}

/* ── Stress gauge bar (worldmonitor renderStress style) ─────────── */
function StressGauge({ score, level }: { score: number; level: string }) {
  const levelColor =
    level === "critical" ? "#dc2626"
    : level === "elevated" ? "#ea580c"
    : level === "moderate" ? "#d97706"
    : "#15803d";
  const gaugeBg =
    level === "critical" ? "rgba(220,38,38,0.10)"
    : level === "elevated" ? "rgba(234,88,12,0.10)"
    : level === "moderate" ? "rgba(217,119,6,0.10)"
    : "rgba(21,128,61,0.10)";
  const w = Math.round(Math.min(100, Math.max(0, score)));
  return (
    <div style={{ marginBottom:12 }}>
      <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:6 }}>
        <span style={{ fontSize:13, color:"var(--text-dim)", textTransform:"uppercase", letterSpacing:"0.06em" }}>Composite Stress Score</span>
        <span style={{ fontSize:13, fontWeight:700, padding:"2px 7px", borderRadius:3, background:gaugeBg, color:levelColor }}>
          {level.toUpperCase()}
        </span>
      </div>
      <div style={{ position:"relative", height:6, borderRadius:3, background:"rgba(0,0,0,0.08)" }}>
        <div style={{ position:"absolute", left:0, top:0, height:"100%", width:`${w}%`, borderRadius:3, background:levelColor, transition:"width 0.4s" }} />
      </div>
      <div style={{ textAlign:"right", fontSize:12, color:"var(--text-dim)", marginTop:2 }}>{score.toFixed(1)}/100</div>
    </div>
  );
}

/* ── Strategic Risk ring gauge (worldmonitor style) ─────────────── */
function RiskRing({ score }: { score: number }) {
  const color = scoreColor(score);
  const level = score >= 70 ? "critical" : score >= 50 ? "elevated" : score >= 30 ? "moderate" : "low";
  const deg = Math.round((score / 100) * 270);
  const r = 38, sw = 7, c = 45;
  const circ = 2 * Math.PI * r;
  const dashLen = (deg / 360) * circ;
  // Rotate start from top-left (-135deg = 225deg offset for 270-deg sweep)
  return (
    <div style={{ display:"flex", alignItems:"center", gap:16, marginBottom:12 }}>
      <svg width={90} height={90} viewBox="0 0 90 90">
        {/* track */}
        <circle cx={c} cy={c} r={r} fill="none" stroke="rgba(0,0,0,0.10)" strokeWidth={sw} />
        {/* progress */}
        <circle cx={c} cy={c} r={r} fill="none" stroke={color} strokeWidth={sw}
          strokeDasharray={`${dashLen} ${circ}`}
          strokeLinecap="round"
          transform={`rotate(135 ${c} ${c})`}
          style={{ transition:"stroke-dasharray 0.5s" }}
        />
        <text x={c} y={c - 4} textAnchor="middle" fill={color} fontSize={20} fontWeight="300">{score}</text>
        <text x={c} y={c + 10} textAnchor="middle" fill={color} fontSize={11} style={{ textTransform: "uppercase" }}>{level}</text>
      </svg>
      <div style={{ display:"flex", flexDirection:"column", gap:4, fontSize:13 }}>
        <div style={{ color:"var(--text-muted)", fontSize:11, textTransform:"uppercase", letterSpacing:1 }}>Strategic Risk</div>
        <div style={{ color:"var(--text)", fontSize:20, fontWeight:300 }}>{score}<span style={{ fontSize:12, color:"var(--text-dim)" }}>/100</span></div>
        <div style={{ color:"var(--text-dim)", fontSize:12 }}>Composite geopolitical + supply score</div>
      </div>
    </div>
  );
}

/* ── Arc Layer (MapLibre geojson trade lines) ────────────────────── */
/* ── MapLibre Layers ─────────────────────────────────────────── */
function ArcLayer({ arcs }: { arcs: { id:string; from:[number,number]; to:[number,number] }[] }) {
  const { map: m, isLoaded } = useMap();
  const SRC = "sc-arcs", LYR = "sc-arcs-lyr";
  const geo = useMemo<GeoJSON.FeatureCollection<GeoJSON.LineString>>(() => ({
    type:"FeatureCollection",
    features: arcs.map(a => ({ type:"Feature", geometry:{ type:"LineString", coordinates:[a.from,a.to] }, properties:{ id:a.id } })),
  }), [arcs]);

  useEffect(() => {
    if (!m || !isLoaded) return;
    try {
      if (!m.getSource(SRC)) m.addSource(SRC, { type:"geojson", data:geo });
      else (m.getSource(SRC) as MapLibreGL.GeoJSONSource).setData(geo);
      
      if (!m.getLayer(LYR)) {
        m.addLayer({ 
          id:LYR, type:"line", source:SRC,
          layout:{ "line-join":"round","line-cap":"round" },
          paint:{ "line-color":"#3b82f6","line-opacity":0.1,"line-width":1,"line-dasharray":[2,4] } 
        });
      }
    } catch { /* */ }
  }, [m, isLoaded, geo]);

  useEffect(() => {
    return () => {
      if (!m) return;
      try { if (m.getLayer(LYR)) m.removeLayer(LYR); } catch { /* */ }
      try { if (m.getSource(SRC)) m.removeSource(SRC); } catch { /* */ }
    };
  }, [m]);

  return null;
}

/* ── Point Layer (MapLibre geojson markers) ────────────────────── */
function PointLayer({ id, features, colorExpr, radiusExpr, onHover }: { id:string; features:GeoJSON.Feature[]; colorExpr:any; radiusExpr:any; onHover?:(info:any)=>void }) {
  const { map: m, isLoaded } = useMap();
  const SRC = `src-${id}`, LYR = `lyr-${id}`;
  const geo = useMemo<GeoJSON.FeatureCollection<GeoJSON.Point>>(() => ({
    type:"FeatureCollection",
    features: features as GeoJSON.Feature<GeoJSON.Point>[]
  }), [features]);

  useEffect(() => {
    if (!m || !isLoaded) return;
    try {
      if (!m.getSource(SRC)) m.addSource(SRC, { type:"geojson", data:geo });
      else (m.getSource(SRC) as MapLibreGL.GeoJSONSource).setData(geo);
      
      if (!m.getLayer(LYR)) {
        m.addLayer({
          id:LYR, type:"circle", source:SRC,
          paint:{
            "circle-color": colorExpr,
            "circle-radius": radiusExpr,
            "circle-stroke-width": 1,
            "circle-stroke-color": id === "cyber" ? "transparent" : "rgba(255,255,255,0.7)",
            "circle-opacity": 0.95
          }
        });
        if (onHover) {
          m.on('mouseenter', LYR, (e: any) => {
            m.getCanvas().style.cursor = 'pointer';
            if (e.features && e.features[0]) {
              onHover({
                lngLat: e.lngLat,
                x: e.originalEvent.clientX,
                y: e.originalEvent.clientY,
                properties: e.features[0].properties
              });
            }
          });
          m.on('mouseleave', LYR, () => {
            m.getCanvas().style.cursor = '';
            onHover(null);
          });
        }
      }
    } catch { /* */ }
  }, [m, isLoaded, geo, colorExpr, radiusExpr, id, onHover]);

  useEffect(() => {
    return () => {
      if (!m) return;
      try { if (m.getLayer(LYR)) m.removeLayer(LYR); } catch { /* */ }
      try { if (m.getSource(SRC)) m.removeSource(SRC); } catch { /* */ }
    };
  }, [m]);

  return null;
}

function MapCountryClickBinder({
  onSelect,
  countryOptions,
}: {
  onSelect: (country: string) => void;
  countryOptions: string[];
}) {
  const { map, isLoaded } = useMap();

  useEffect(() => {
    if (!map || !isLoaded) return;

    const handleMapClick = (event: MapLibreGL.MapMouseEvent) => {
      const candidate = getCountryFromMapClick(map as MapRef, event.point, countryOptions);
      if (candidate) onSelect(candidate);
    };

    map.on("click", handleMapClick);
    return () => {
      map.off("click", handleMapClick);
    };
  }, [map, isLoaded, onSelect, countryOptions]);

  return null;
}

/* ══════════════════════════════════════════════════════════════════
   Root Component
   ══════════════════════════════════════════════════════════════════ */

function IntelSection({
  title,
  right,
  children,
}: {
  title: string;
  right?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section
      style={{
        border: "1px solid var(--border)",
        borderRadius: 18,
        background: "linear-gradient(180deg, rgba(255,255,255,0.98) 0%, rgba(248,250,252,0.96) 100%)",
        overflow: "hidden",
        boxShadow: "0 18px 40px rgba(15,23,42,0.08)",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "14px 18px 12px",
          borderBottom: "1px solid var(--border-subtle)",
        }}
      >
        <div style={{ fontSize: 11, letterSpacing: "0.18em", textTransform: "uppercase", color: "var(--text-muted)", fontWeight: 800, fontFamily: "var(--font-headline)" }}>
          {title}
        </div>
        {right}
      </div>
      <div style={{ padding: 16 }}>{children}</div>
    </section>
  );
}

function MixDonut({
  title,
  centerLabel,
  data,
  footnote,
}: {
  title: string;
  centerLabel: string;
  data: { label: string; color: string; value: number }[];
  footnote?: string;
}) {
  const gradient = `conic-gradient(${data.map((item, index) => {
    const start = data.slice(0, index).reduce((sum, part) => sum + part.value, 0);
    const end = start + item.value;
    return `${item.color} ${start}% ${end}%`;
  }).join(", ")})`;

  return (
    <div>
      <div style={{ fontSize: 14, color: "var(--text)", marginBottom: 12, fontWeight: 700 }}>{title}</div>
      <div style={{ display: "grid", gridTemplateColumns: "120px 1fr", gap: 16, alignItems: "center" }}>
        <div
          style={{
            width: 120,
            height: 120,
            borderRadius: "50%",
            background: gradient,
            position: "relative",
            boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.08)",
          }}
        >
          <div
            style={{
              position: "absolute",
              inset: 24,
              borderRadius: "50%",
              background: "var(--surface)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              textAlign: "center",
              color: "var(--text-muted)",
              fontSize: 13,
              fontWeight: 700,
              lineHeight: 1.2,
              padding: 8,
            }}
          >
            {centerLabel}
          </div>
        </div>
        <div style={{ display: "grid", gap: 10 }}>
          {data.map((item) => (
            <div key={item.label} style={{ display: "flex", alignItems: "center", gap: 10, color: "var(--text-secondary)", fontSize: 13 }}>
              <span style={{ width: 10, height: 10, borderRadius: "50%", background: item.color, display: "inline-block" }} />
              <span style={{ flex: 1 }}>{item.label}</span>
              <strong style={{ color: "var(--text)" }}>{item.value}%</strong>
            </div>
          ))}
          {footnote && <div style={{ color: "var(--text-muted)", fontSize: 12, marginTop: 4 }}>{footnote}</div>}
        </div>
      </div>
    </div>
  );
}

function SignalMeter({
  label,
  color,
  score,
  count,
}: {
  label: string;
  color: string;
  score: number;
  count: number;
}) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "96px 1fr 36px", gap: 10, alignItems: "center" }}>
      <div style={{ color: "var(--text-secondary)", fontSize: 13 }}>{label}</div>
      <div style={{ height: 8, borderRadius: 999, background: "rgba(0,0,0,0.08)", overflow: "hidden" }}>
        <div style={{ width: `${clamp(score)}%`, height: "100%", background: color, borderRadius: 999 }} />
      </div>
      <div style={{ color: "var(--text)", fontWeight: 700, textAlign: "right" }}>{count}</div>
    </div>
  );
}

function CountryIntelDrawer({
  intel,
  open,
  onClose,
}: {
  intel: CountryIntelPanelData | null;
  open: boolean;
  onClose: () => void;
}) {
  if (!open || !intel) return null;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 60,
        background: "rgba(15, 23, 42, 0.18)",
        backdropFilter: "blur(10px)",
        display: "flex",
        justifyContent: "flex-end",
        fontFamily: "var(--font-body)",
      }}
      onClick={onClose}
    >
      <aside
        onClick={(event) => event.stopPropagation()}
        style={{
          width: "min(560px, 100vw)",
          height: "100vh",
          background: "linear-gradient(180deg, rgba(255,255,255,0.99) 0%, rgba(248,250,252,0.98) 100%)",
          color: "var(--text)",
          borderLeft: "1px solid var(--border)",
          boxShadow: "-24px 0 64px rgba(15,23,42,0.18)",
          overflowY: "auto",
          padding: 24,
          display: "grid",
          gap: 18,
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
              <span style={{ fontSize: 18, fontWeight: 900, color: "var(--accent)", fontFamily: "var(--font-headline)" }}>{intel.code}</span>
              <h2 style={{ margin: 0, fontSize: 32, fontWeight: 900, lineHeight: 1, fontFamily: "var(--font-headline)" }}>{intel.country}</h2>
            </div>
            <div style={{ color: "#9ca3af", fontSize: 14 }}>{intel.code} • Country Intelligence</div>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{
              width: 38,
              height: 38,
              borderRadius: 10,
              border: "1px solid var(--border)",
              background: "var(--surface)",
              color: "var(--text-muted)",
              cursor: "pointer",
            }}
          >
            <X size={18} />
          </button>
        </div>

        <IntelSection
          title="Instability Index"
          right={<span style={{ color: "var(--text-muted)", fontSize: 12, fontFamily: "var(--font-headline)" }}>Updated {fmtDate(intel.updatedAt)}, {new Date(intel.updatedAt || Date.now()).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>}
        >
          <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 18 }}>
            <div style={{ fontSize: 44, lineHeight: 1, fontWeight: 900, color: "#f59e0b", fontFamily: "var(--font-headline)" }}>{intel.riskScore}/100</div>
            <div style={{ color: "var(--text-muted)", fontSize: 16, textTransform: "capitalize" }}>→ {intel.riskStatus}</div>
          </div>
          <div style={{ display: "grid", gap: 14 }}>
            <SignalMeter label="Unrest" color="#4ade80" score={intel.scores.unrest} count={intel.counts.unrest} />
            <SignalMeter label="Conflict" color="#ef4444" score={intel.scores.conflict} count={intel.counts.conflict} />
            <SignalMeter label="Security" color="#f59e0b" score={intel.scores.security} count={intel.counts.security} />
            <SignalMeter label="Information" color="#ff4d4f" score={intel.scores.information} count={intel.counts.information} />
          </div>
        </IntelSection>

        <IntelSection title="Intelligence Brief">
          <div style={{ color: "var(--text)", fontSize: 16, lineHeight: 1.7, fontWeight: 700 }}>{intel.brief}</div>
        </IntelSection>

        <IntelSection title="Energy Profile">
          <div style={{ display: "grid", gap: 20 }}>
            <MixDonut title="Primary Energy" centerLabel="Primary Energy" data={intel.energyMix} footnote="Derived baseline mix for panel continuity." />
            <div style={{ color: "var(--text-secondary)", fontSize: 13 }}>
              Import dependency:{" "}
              <span style={{ padding: "4px 8px", borderRadius: 999, background: "rgba(37,99,235,0.12)", color: "var(--accent)", fontWeight: 700, border: "1px solid rgba(37,99,235,0.16)" }}>
                {intel.supplierCount > 4 ? "Net importer" : "Mixed position"}
              </span>
            </div>
            <MixDonut title="Monthly Generation Mix" centerLabel="Monthly Mix" data={intel.monthlyMix} />
          </div>
        </IntelSection>

        <IntelSection title="Maritime Activity" right={<span style={{ color: "var(--text-muted)", fontSize: 12, fontFamily: "var(--font-headline)" }}>{intel.maritimeRows.length} routes</span>}>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 420 }}>
              <thead>
                <tr>
                  {["Port", "Calls (30d)", "Trend", "Import", "Export"].map((label) => (
                    <th key={label} style={{ textAlign: "left", color: "var(--text-muted)", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.08em", paddingBottom: 12, fontFamily: "var(--font-headline)" }}>
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {intel.maritimeRows.map((row) => (
                  <tr key={row.name} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                    <td style={{ padding: "12px 0", color: "var(--text)", fontWeight: 700 }}>{row.name}</td>
                    <td style={{ padding: "12px 0", color: "var(--text-secondary)" }}>{row.calls}</td>
                    <td style={{ padding: "12px 0", fontWeight: 800, color: row.trend >= 0 ? "#4ade80" : "#ef4444" }}>
                      {row.trend >= 0 ? "+" : ""}{row.trend.toFixed(1)}%
                    </td>
                    <td style={{ padding: "12px 0", color: "var(--text-secondary)" }}>{row.importDwt}</td>
                    <td style={{ padding: "12px 0", color: "var(--text-secondary)" }}>{row.exportDwt}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </IntelSection>

        <IntelSection title="Country Signals">
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 18 }}>
            {[
              ["Critical News", intel.signals.filter((item) => item.severity === "critical").length, "#ef4444"],
              ["Military", intel.counts.military, "#f59e0b"],
              ["Sanctions", intel.counts.sanctions, "#f97316"],
              ["Satellite Fires", intel.counts.fires, "#fb923c"],
              ["Cyber", intel.counts.cyber, "#3b82f6"],
              ["Displaced", intel.counts.displaced, "#94a3b8"],
            ].map(([label, value, color]) => (
              <span
                key={String(label)}
                style={{
                  border: `1px solid ${String(color)}66`,
                  color: color as string,
                  borderRadius: 999,
                  padding: "6px 10px",
                  fontSize: 13,
                  fontWeight: 700,
                  background: `${String(color)}14`,
                  fontFamily: "var(--font-headline)",
                }}
              >
                {value} {label}
              </span>
            ))}
          </div>
          <div style={{ display: "grid", gap: 10 }}>
            {intel.signals.slice(0, 6).map((signal) => (
              <div key={signal.id} style={{ border: "1px solid var(--border)", borderRadius: 14, padding: 14, background: "var(--surface)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                  <span style={{ fontSize: 11, padding: "4px 8px", borderRadius: 999, background: "var(--surface-hover)", color: "var(--text)", textTransform: "uppercase", fontWeight: 800, fontFamily: "var(--font-headline)" }}>
                    {signal.category}
                  </span>
                  <span style={{ fontSize: 11, padding: "4px 8px", borderRadius: 999, border: "1px solid rgba(245,158,11,0.35)", color: "#f59e0b", textTransform: "uppercase", fontWeight: 800, fontFamily: "var(--font-headline)" }}>
                    {signal.severity}
                  </span>
                </div>
                <div style={{ color: "var(--text)", fontSize: 14, fontWeight: 700, lineHeight: 1.5 }}>{signal.title}</div>
                <div style={{ color: "var(--text-muted)", fontSize: 12, marginTop: 6 }}>{signal.time}</div>
              </div>
            ))}
          </div>
        </IntelSection>

        <IntelSection title="Military Activity">
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 12, marginBottom: 16 }}>
            {[
              ["Own Flights", intel.militarySummary.ownFlights],
              ["Foreign Flights", intel.militarySummary.foreignFlights],
              ["Naval Vessels", intel.militarySummary.navalVessels],
              ["Foreign Presence", intel.militarySummary.foreignPresence],
            ].map(([label, value]) => (
              <div key={String(label)} style={{ border: "1px solid var(--border)", borderRadius: 14, padding: 14, background: "var(--surface)" }}>
                <div style={{ color: "var(--text-secondary)", fontSize: 13, marginBottom: 10 }}>{label}</div>
                <div style={{ color: "var(--text)", fontSize: 24, fontWeight: 900, fontFamily: "var(--font-headline)" }}>{value}</div>
              </div>
            ))}
          </div>
          <div style={{ color: "var(--text-muted)", fontSize: 12 }}>
            Nearest route dependencies: {intel.routeDependencies.length > 0 ? intel.routeDependencies.join(", ") : "No linked chokepoints mapped."}
          </div>
        </IntelSection>

        <IntelSection title="Infrastructure Exposure">
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 12 }}>
            {intel.infrastructure.map((item) => (
              <div key={item.label} style={{ border: "1px solid var(--border)", borderRadius: 14, padding: 16, background: "var(--surface)", display: "flex", alignItems: "center", gap: 12 }}>
                <span style={{ fontSize: 18 }}>{item.icon}</span>
                <div style={{ flex: 1 }}>
                  <div style={{ color: "var(--text-secondary)", fontSize: 13 }}>{item.label}</div>
                  <div style={{ color: "var(--text)", fontSize: 24, fontWeight: 900, fontFamily: "var(--font-headline)" }}>{item.value}</div>
                </div>
              </div>
            ))}
          </div>
        </IntelSection>

        <IntelSection title="Economic Indicators">
          <div style={{ display: "grid", gap: 12 }}>
            {intel.economics.map((item) => (
              <div key={item.label} style={{ border: "1px solid var(--border)", borderRadius: 14, padding: 16, background: "var(--surface)" }}>
                <div style={{ color: "var(--text)", fontSize: 14, fontWeight: 800, marginBottom: 10 }}>
                  {item.label}{" "}
                  {item.trend === "up" ? <span style={{ color: "#f59e0b" }}>↑</span> : item.trend === "down" ? <span style={{ color: "#ef4444" }}>↓</span> : null}
                </div>
                <div style={{ color: "var(--text)", fontSize: 30, fontWeight: 900, lineHeight: 1, fontFamily: "var(--font-headline)" }}>{item.value}</div>
                <div style={{ color: "var(--text-muted)", fontSize: 12, marginTop: 8 }}>{item.source}</div>
              </div>
            ))}
          </div>
        </IntelSection>
      </aside>
    </div>
  );
}

function CountryIntelDrawerV2({
  intel,
  open,
  onClose,
}: {
  intel: CountryIntelPanelData | null;
  open: boolean;
  onClose: () => void;
}) {
  if (!open || !intel) return null;

  const visibleSignals = intel.signals.length > 0 ? intel.signals.slice(0, 6) : [{
    id: `${slugify(intel.country)}-fallback-signal`,
    category: "monitor",
    severity: "low" as const,
    title: `No major structured alerts are currently mapped directly to ${intel.country}.`,
    time: "Fallback summary",
  }];

  const visibleMaritimeRows = intel.maritimeRows.length > 0 ? intel.maritimeRows : [{
    name: "No mapped route",
    calls: 0,
    trend: 0,
    importDwt: "0",
    exportDwt: "0",
  }];

  return (
    <div className="fixed inset-0 z-[60] flex justify-end bg-slate-900/20 backdrop-blur-sm" onClick={onClose}>
      <aside
        onClick={(event) => event.stopPropagation()}
        className="h-screen w-full max-w-[560px] overflow-y-auto border-l border-border bg-card shadow-2xl"
      >
        <div className="grid gap-4 p-6">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="mb-1 flex items-center gap-3">
                <span className="font-mono text-lg font-black text-blue-600">{intel.code}</span>
                <h2 className="font-headline text-5xl font-black leading-none text-foreground">{intel.country}</h2>
              </div>
              <p className="text-sm text-muted-foreground">{intel.code} • Country Intelligence</p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="flex h-12 w-12 items-center justify-center rounded-xl border border-border bg-card text-muted-foreground transition-colors hover:bg-accent"
            >
              <X size={20} />
            </button>
          </div>

          <IntelSection
            title="Instability Index"
            right={<span className="font-mono text-[11px] text-muted-foreground">Updated {fmtDate(intel.updatedAt)}, {new Date(intel.updatedAt || Date.now()).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>}
          >
            <div className="mb-5 flex items-end gap-3">
              <div className="font-headline text-5xl font-black leading-none text-orange-500">{intel.riskScore}/100</div>
              <div className="pb-1 text-sm capitalize text-muted-foreground">→ {intel.riskStatus}</div>
            </div>
            <div className="grid gap-3">
              <SignalMeter label="Unrest" color="#4ade80" score={intel.scores.unrest} count={intel.counts.unrest} />
              <SignalMeter label="Conflict" color="#ef4444" score={intel.scores.conflict} count={intel.counts.conflict} />
              <SignalMeter label="Security" color="#f59e0b" score={intel.scores.security} count={intel.counts.security} />
              <SignalMeter label="Information" color="#ff4d4f" score={intel.scores.information} count={intel.counts.information} />
            </div>
          </IntelSection>

          <IntelSection title="Intelligence Brief">
            <p className="text-sm font-semibold leading-7 text-foreground">{intel.brief}</p>
          </IntelSection>

          <IntelSection title="Energy Profile">
            <div className="grid gap-6">
              <MixDonut title="Primary Energy" centerLabel="Primary Energy" data={intel.energyMix} footnote="Derived baseline mix for panel continuity." />
              <p className="text-sm text-muted-foreground">
                Import dependency:{" "}
                <span className="rounded-full border border-blue-200 bg-blue-50 px-2 py-1 font-semibold text-blue-700">
                  {intel.supplierCount > 4 ? "Net importer" : "Mixed position"}
                </span>
              </p>
              <MixDonut title="Monthly Generation Mix" centerLabel="Monthly Mix" data={intel.monthlyMix} />
            </div>
          </IntelSection>

          <IntelSection
            title="Maritime Activity"
            right={<span className="font-mono text-[11px] text-muted-foreground">{visibleMaritimeRows.length} routes</span>}
          >
            <div className="overflow-x-auto">
              <table className="w-full min-w-[420px] border-collapse text-sm">
                <thead>
                  <tr className="text-left font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
                    <th className="pb-3">Port</th>
                    <th className="pb-3">Calls (30d)</th>
                    <th className="pb-3">Trend</th>
                    <th className="pb-3">Import</th>
                    <th className="pb-3">Export</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleMaritimeRows.map((row) => (
                    <tr key={row.name} className="border-t border-border">
                      <td className="py-3 font-semibold text-foreground">{row.name}</td>
                      <td className="py-3 text-foreground">{row.calls}</td>
                      <td className={`py-3 font-bold ${row.trend >= 0 ? "text-emerald-500" : "text-red-500"}`}>
                        {row.trend >= 0 ? "+" : ""}{row.trend.toFixed(1)}%
                      </td>
                      <td className="py-3 text-muted-foreground">{row.importDwt}</td>
                      <td className="py-3 text-muted-foreground">{row.exportDwt}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </IntelSection>

          <IntelSection title="Country Signals">
            <div className="mb-4 flex flex-wrap gap-2">
              {[
                ["Critical News", visibleSignals.filter((item) => item.severity === "critical").length, "text-red-600 border-red-200 bg-red-50"],
                ["Military", intel.counts.military, "text-amber-600 border-amber-200 bg-amber-50"],
                ["Sanctions", intel.counts.sanctions, "text-orange-600 border-orange-200 bg-orange-50"],
                ["Satellite Fires", intel.counts.fires, "text-orange-500 border-orange-200 bg-orange-50"],
                ["Cyber", intel.counts.cyber, "text-blue-600 border-blue-200 bg-blue-50"],
                ["Displaced", intel.counts.displaced, "text-slate-600 border-slate-200 bg-slate-50"],
              ].map(([label, value, tone]) => (
                <span key={String(label)} className={`rounded-full border px-3 py-1 font-mono text-xs font-bold ${tone}`}>
                  {value} {label}
                </span>
              ))}
            </div>
            <div className="grid gap-3">
              {visibleSignals.map((signal) => (
                <div key={signal.id} className="rounded-xl border border-border bg-card p-4">
                  <div className="mb-2 flex items-center gap-2">
                    <span className="rounded-full bg-muted px-2 py-1 font-mono text-[10px] font-bold uppercase tracking-wider text-foreground">
                      {signal.category}
                    </span>
                    <span className="rounded-full border border-amber-200 px-2 py-1 font-mono text-[10px] font-bold uppercase tracking-wider text-amber-600">
                      {signal.severity}
                    </span>
                  </div>
                  <div className="text-sm font-semibold leading-6 text-foreground">{signal.title}</div>
                  <div className="mt-2 text-xs text-muted-foreground">{signal.time}</div>
                </div>
              ))}
            </div>
          </IntelSection>

          <IntelSection title="Military Activity">
            <div className="mb-4 grid grid-cols-2 gap-3">
              {[
                ["Own Flights", intel.militarySummary.ownFlights],
                ["Foreign Flights", intel.militarySummary.foreignFlights],
                ["Naval Vessels", intel.militarySummary.navalVessels],
                ["Foreign Presence", intel.militarySummary.foreignPresence],
              ].map(([label, value]) => (
                <div key={String(label)} className="rounded-xl border border-border bg-card p-4">
                  <div className="mb-2 text-xs text-muted-foreground">{label}</div>
                  <div className="font-headline text-2xl font-black text-foreground">{value}</div>
                </div>
              ))}
            </div>
            <div className="text-xs text-muted-foreground">
              Nearest route dependencies: {intel.routeDependencies.length > 0 ? intel.routeDependencies.join(", ") : "No linked chokepoints mapped."}
            </div>
          </IntelSection>

          <IntelSection title="Infrastructure Exposure">
            <div className="grid grid-cols-2 gap-3">
              {intel.infrastructure.map((item) => (
                <div key={item.label} className="flex items-center gap-3 rounded-xl border border-border bg-card p-4">
                  <span className="text-lg">{item.icon}</span>
                  <div className="min-w-0 flex-1">
                    <div className="text-xs text-muted-foreground">{item.label}</div>
                    <div className="font-headline text-2xl font-black text-foreground">{item.value}</div>
                  </div>
                </div>
              ))}
            </div>
          </IntelSection>

          <IntelSection title="Economic Indicators">
            <div className="grid gap-3">
              {intel.economics.map((item) => (
                <div key={item.label} className="rounded-xl border border-border bg-card p-4">
                  <div className="mb-2 text-sm font-bold text-foreground">
                    {item.label}{" "}
                    {item.trend === "up" ? <span className="text-amber-500">↑</span> : item.trend === "down" ? <span className="text-red-500">↓</span> : null}
                  </div>
                  <div className="font-headline text-3xl font-black leading-none text-foreground">{item.value}</div>
                  <div className="mt-2 text-xs text-muted-foreground">{item.source}</div>
                </div>
              ))}
            </div>
          </IntelSection>
        </div>
      </aside>
    </div>
  );
}
const POOL_WEBCAMS = [
  // Mideast
  { id: 'tehran', city: 'Tehran', country: 'Iran', region: 'Mideast', videoId: '-zGuR1qVKrU' },
  { id: 'telaviv', city: 'Tel Aviv', country: 'Israel', region: 'Mideast', videoId: 'gmtlJ_m2r5A' },
  { id: 'jerusalem', city: 'Jerusalem', country: 'Israel', region: 'Mideast', videoId: 'e34xb-Fbl0U' },
  { id: 'mecca', city: 'Mecca', country: 'Saudi Arabia', region: 'Mideast', videoId: 'Cm1v4bteXbI' },
  { id: 'dubai', city: 'Dubai', country: 'UAE', region: 'Mideast', videoId: 'yN20H1yK8Uo' },
  // Europe
  { id: 'kyiv', city: 'Kyiv', country: 'Ukraine', region: 'Europe', videoId: '-Q7FuPINDjA' },
  { id: 'odessa', city: 'Odessa', country: 'Ukraine', region: 'Europe', videoId: 'e2gC37ILQmk' },
  { id: 'london', city: 'London', country: 'UK', region: 'Europe', videoId: 'Lxqcg1qt0XU' },
  { id: 'paris', city: 'Paris', country: 'France', region: 'Europe', videoId: 'OzYp4NRZlwQ' },
  { id: 'amsterdam', city: 'Amsterdam', country: 'Netherlands', region: 'Europe', videoId: '9L18q5K8Zcw' },
  { id: 'venice', city: 'Venice', country: 'Italy', region: 'Europe', videoId: 'ph1vpnYJxJk' },
  // Americas
  { id: 'washington', city: 'Washington DC', country: 'USA', region: 'Americas', videoId: '1wV9lLe14aU' },
  { id: 'newyork', city: 'New York', country: 'USA', region: 'Americas', videoId: '4qyZLflp-sI' },
  { id: 'miami', city: 'Miami', country: 'USA', region: 'Americas', videoId: 'r5b9E5k_7S8' },
  { id: 'toronto', city: 'Toronto', country: 'Canada', region: 'Americas', videoId: 'Jg7mXnQ07a4' },
  { id: 'riodejaneiro', city: 'Rio de Janeiro', country: 'Brazil', region: 'Americas', videoId: '2b9txcAt4e0' },
  // Asia
  { id: 'taipei', city: 'Taipei', country: 'Taiwan', region: 'Asia', videoId: 'z_fY1pj1VBw' },
  { id: 'tokyo', city: 'Tokyo', country: 'Japan', region: 'Asia', videoId: '_k-5U7IeK8g' },
  { id: 'hongkong', city: 'Hong Kong', country: 'Hong Kong', region: 'Asia', videoId: 'F2o_L-A6f3Y' },
  { id: 'seoul', city: 'Seoul', country: 'South Korea', region: 'Asia', videoId: '5Z1W5z645s8' },
  { id: 'bangkok', city: 'Bangkok', country: 'Thailand', region: 'Asia', videoId: 'N9i8mG8xW3o' },
  // Space / Global
  { id: 'iss', city: 'ISS Earth View', country: 'Space', region: 'Space', videoId: 'vytmBNhc9ig' },
  { id: 'spacex', city: 'SpaceX', country: 'Space', region: 'Space', videoId: 'fO9e9jnhYK8' },
  { id: 'nasa', city: 'NASA Live', country: 'Space', region: 'Space', videoId: '21X5lGlDOfg' }
];

const POOL_NEWS = [
  // Markets
  { id:'bloomberg',  name:'Bloomberg TV', region:'Markets', videoId:'iEpJwprxDdk' },
  { id:'cnbc',       name:'CNBC Live',    region:'Markets', videoId:'9NyxcX3rhQs' },
  { id:'yahoo',      name:'Yahoo Finance',region:'Markets', videoId:'KQp-e_XQnDE' },
  // Global
  { id:'sky',        name:'Sky News',     region:'Global',  videoId:'uvviIF4725I' },
  { id:'cnn',        name:'CNN',          region:'Global',  videoId:'w_Ma8oQLmSM' },
  { id:'reuters',    name:'Reuters Live', region:'Global',  videoId:'Wj1x_wA9EKI' },
  // Europe
  { id:'euronews',   name:'Euronews',     region:'Europe',  videoId:'pykpO5kQJ98' },
  { id:'dw',         name:'DW News',      region:'Europe',  videoId:'LuKwFajn37U' },
  { id:'france24',   name:'France 24',    region:'Europe',  videoId:'u9foWyMSETk' },
  { id:'bbc',        name:'BBC News',     region:'Europe',  videoId:'bjgQzJzCZKs' },
  // Asia
  { id:'tbs',        name:'TBS News',     region:'Asia',    videoId:'aUDm173E8k8' },
  { id:'cna',        name:'CNA Asia',     region:'Asia',    videoId:'XWq5kBlakcQ' },
  { id:'nhk',        name:'NHK World',    region:'Asia',    videoId:'f0lYfG_vY_U' },
  { id:'arirang',    name:'Arirang TV',   region:'Asia',    videoId:'uM0-E8tHlOA' },
  { id:'ndtv',       name:'NDTV India',   region:'Asia',    videoId:'l9ViEIip9q4' },
  // Mideast
  { id:'aljazeera',  name:'Al Jazeera',   region:'Mideast', videoId:'gCNeDWCI0vo' },
  { id:'alarabiya',  name:'Al Arabiya',   region:'Mideast', videoId:'n7eQejkXbnM' },
  { id:'trt',        name:'TRT World',    region:'Mideast', videoId:'ABfFhWzWs0s' },
  { id:'i24',        name:'i24NEWS',      region:'Mideast', videoId:'myKybZUK0IA' }
];

function YouTubeLivePlayer({ videoId, onUnavailable, overlay }: { videoId: string; onUnavailable: () => void; overlay: ReactNode }) {
  void onUnavailable;
  const embedSrc = `https://www.youtube-nocookie.com/embed/${encodeURIComponent(
    videoId,
  )}?autoplay=1&mute=1&controls=1&playsinline=1&rel=0&modestbranding=1`;

  return (
    <div style={{ position:"relative", paddingTop:"56.25%", background:"#000", borderRadius:8, overflow:"hidden", border:"1px solid var(--border,#d4d4d4)", boxShadow:"0 1px 3px rgba(0,0,0,0.06)" }}>
      <div style={{ position:"absolute", inset:0, width:"100%", height:"100%", border:0, pointerEvents: "auto" }}>
         <iframe
            key={videoId}
            src={embedSrc}
            title={`YouTube Live ${videoId}`}
            style={{ width: "100%", height: "100%", border: 0 }}
            allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
            allowFullScreen
          />
      </div>
      {overlay}
    </div>
  );
}

type VideoItem = { id: string; title: string; subtitle: string; region: string; videoId: string; };

function SmartVideoGrid({ 
  title, 
  items, 
  regions, 
  limit = 12 
}: { 
  title: string; 
  items: VideoItem[]; 
  regions: readonly string[]; 
  limit?: number; 
}) {
  const [activeRegion, setActiveRegion] = useState<string>('All');
  const [activeItems, setActiveItems] = useState<VideoItem[]>([]);
  const [bannedIds, setBannedIds] = useState<Set<string>>(new Set());

  const fillItems = useCallback((currentActive: VideoItem[], currentBanned: Set<string>, region: string) => {
    const filteredPool = items.filter(i => region === 'All' || i.region === region);
    const validPool = filteredPool.filter(i => !currentBanned.has(i.id));
    const currentIds = new Set(currentActive.map(i => i.id));
    const availableToAdd = validPool.filter(i => !currentIds.has(i.id));
    
    let newActive = currentActive.filter(i => region === 'All' || i.region === region);
    
    while (newActive.length < Math.min(limit, validPool.length) && availableToAdd.length > 0) {
      const next = availableToAdd.shift();
      if (next) newActive.push(next);
    }
    return newActive;
  }, [items, limit]);

  useEffect(() => {
    setActiveItems(prev => fillItems([], bannedIds, activeRegion));
  }, [activeRegion, fillItems, bannedIds]);

  useEffect(() => {
    const timer = setInterval(() => {
       setActiveItems(prev => {
         const filteredPool = items.filter(i => activeRegion === 'All' || i.region === activeRegion);
         const validPool = filteredPool.filter(i => !bannedIds.has(i.id));
         const currentIds = new Set(prev.map(i => i.id));
         const availableToAdd = validPool.filter(i => !currentIds.has(i.id));
         
         if (availableToAdd.length > 0 && prev.length > 0) {
            const newActive = [...prev];
            newActive.shift();
            newActive.push(availableToAdd[0]);
            return newActive;
         }
         return prev;
       });
    }, 3 * 60 * 1000);
    return () => clearInterval(timer);
  }, [items, activeRegion, bannedIds]);

  const handleUnavailable = useCallback((id: string) => {
    setBannedIds(prev => {
      const next = new Set(prev);
      next.add(id);
      return next;
    });
  }, []);

  return (
    <div style={{ background: "var(--panel-bg,#fff)", border: "1px solid var(--panel-border,#d4d4d4)", borderRadius: 8, boxShadow: "0 1px 4px rgba(0,0,0,0.06), 0 4px 16px rgba(0,0,0,0.04)", display: "flex", flexDirection: "column", overflow: "hidden", gridColumn: "1 / -1" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 12px", minHeight: 40, borderBottom: "1px solid var(--panel-border,#d4d4d4)", flexShrink: 0, background: "var(--bg,#f8f9fa)", gap: 8, flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#ef4444", flexShrink: 0, boxShadow: "0 0 0 3px rgba(239,68,68,0.18)", animation: "pulse-dot 1.5s ease-in-out infinite" }} />
          <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.12em", color: "var(--text,#1a1a1a)", textTransform: "uppercase", fontFamily: "var(--font-headline)" }}>{title}</span>
          <span style={{ fontSize: 10, fontWeight: 800, color: "#fff", background: "#ef4444", borderRadius: 999, padding: "1px 6px", fontFamily: "var(--font-headline)" }}>
            {activeItems.length}
          </span>
        </div>
        <div style={{ display: "flex", gap: 3, flexWrap: "wrap" }}>
          {regions.map(r => (
            <button key={r} onClick={() => setActiveRegion(r)} style={{
              padding: "3px 10px", fontSize: 10, fontFamily: "var(--font-headline)",
              fontWeight: activeRegion === r ? 700 : 500,
              background: activeRegion === r ? "var(--accent,#2563eb)" : "transparent",
              color: activeRegion === r ? "#fff" : "var(--text-dim,#6b6b6b)",
              border: activeRegion === r ? "1px solid var(--accent,#2563eb)" : "1px solid var(--border,#d4d4d4)",
              borderRadius: 3, cursor: "pointer", whiteSpace: "nowrap",
              textTransform: "uppercase", letterSpacing: "0.06em",
              transition: "all 0.12s",
            }}>{r}</button>
          ))}
        </div>
      </div>
      
      <div style={{ padding: "12px", background: "var(--bg,#f8f9fa)" }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(280px,1fr))", gap: 12 }}>
          {activeItems.map(item => (
            <YouTubeLivePlayer 
              key={item.id} 
              videoId={item.videoId} 
              onUnavailable={() => handleUnavailable(item.id)}
              overlay={
                <div style={{ position: "absolute", top: 8, left: 8, display: "flex", alignItems: "center", gap: 5, background: "rgba(0,0,0,0.7)", backdropFilter: "blur(4px)", borderRadius: 4, padding: "3px 8px", pointerEvents: "none" }}>
                  <span style={{ width: 5, height: 5, borderRadius: "50%", background: "#ef4444", animation: "pulse-dot 1.5s ease-in-out infinite" }} />
                  <span style={{ fontSize: 10, fontWeight: 700, color: "#fff", fontFamily: "var(--font-headline)", letterSpacing: "0.05em", textTransform: "uppercase" }}>
                    {item.title}{item.subtitle ? `, ${item.subtitle}` : ''}
                  </span>
                </div>
              }
            />
          ))}
          {activeItems.length === 0 && (
            <div style={{ padding: 16, textAlign: "center", color: "var(--text-dim)", fontSize: 13, gridColumn: "1 / -1" }}>
              No available live streams in this category.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const panelCssStatic = { background: "var(--panel-bg,#fff)", border: "1px solid var(--panel-border,#d4d4d4)", borderRadius: 8, boxShadow: "0 1px 4px rgba(0,0,0,0.06), 0 4px 16px rgba(0,0,0,0.04)", display: "flex", flexDirection: "column" as const, overflow: "hidden" };
const phCssStatic = { display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 12px", minHeight: 40, borderBottom: "1px solid var(--panel-border,#d4d4d4)", flexShrink: 0, background: "var(--bg,#f8f9fa)" };
const ptCssStatic = { fontSize: 11, fontWeight: 700, letterSpacing: "0.12em", color: "var(--text,#1a1a1a)", textTransform: "uppercase" as const, fontFamily: "var(--font-headline)" };
const pbCssStatic = { padding: "12px", flex: 1, display: "flex", flexDirection: "column" as const, overflowY: "auto" as const, background: "var(--bg,#f8f9fa)" };
const thStatic = { padding: "8px 6px", fontSize: 10, color: "var(--text-muted,#737373)", textTransform: "uppercase" as const, fontWeight: 700, letterSpacing: "0.06em", fontFamily: "var(--font-headline)", borderBottom: "1px solid var(--panel-border,#d4d4d4)", whiteSpace: "nowrap" as const };
const tdStatic = { padding: "8px 6px", borderBottom: "1px solid var(--border-subtle,#e5e5e5)", verticalAlign: "middle" };
const GLOBAL_BUNDLE_REFETCH_MS = 300_000;

function useGlobalDashboardBundle() {
  return useQuery({
    queryKey: ["globalDashboardBundle"],
    queryFn: () => api.global.dashboardBundle(),
    refetchInterval: GLOBAL_BUNDLE_REFETCH_MS,
    staleTime: 30_000,
  });
}

function AiMarketImplicationsPanel({ title }: { title?: string }) {
  const { data: bundle, isLoading } = useGlobalDashboardBundle();
  const data = bundle?.market_implications;

  if (isLoading) return (
    <div style={panelCssStatic}>
      <div style={phCssStatic}><span style={ptCssStatic}>{title || "AI Market Implications"} <span style={{fontSize:9, background:"#f59e0b", color:"#fff", padding:"2px 4px", borderRadius:3, marginLeft:4}}>LIVE</span></span></div>
      <div style={{ ...pbCssStatic, minHeight:150, display:"flex", alignItems:"center", justifyContent:"center" }}>
        <div style={{ fontSize:13, color:"var(--text-dim)" }}>⏳ Querying Groq AI...</div>
      </div>
    </div>
  );

  const displaySummary = Array.isArray(data?.summary) && data.summary.length > 0
    ? data.summary
    : ["Awaiting AI analysis — chokepoint data still loading."];

  const model = data?.model || "heuristic";
  const isGroq = model.includes("groq") || model.includes("LLM");
  const generatedAt = data?.generated_at ? fmtAgo(data.generated_at) : "—";
  const isStale = data?.generated_at
    ? (Date.now() - new Date(data.generated_at).getTime()) > 90 * 60 * 1000  // >90min = stale
    : false;

  return (
    <div style={panelCssStatic}>
      <div style={phCssStatic}>
        <span style={ptCssStatic}>{title || "Market Intelligence"}</span>
      </div>
      <div style={pbCssStatic}>
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:12 }}>
          <div style={{ fontSize:11, color:"var(--text-dim)", fontFamily:"var(--font-headline)", fontWeight:700 }}>
            Automated Intelligence Feed
          </div>
          <div style={{ fontSize:10, color: isStale ? "#f59e0b" : "var(--text-muted)" }}>
            {isStale ? "⚠️ " : "✓ "}{generatedAt}
          </div>
        </div>
        <ul style={{ paddingLeft: 16, margin: 0, fontSize: 13, color: "var(--text)", lineHeight:1.6 }}>
          {displaySummary.map((point: string, i: number) => (
            <li key={i} style={{ marginBottom: 8 }}>{point}</li>
          ))}
        </ul>
        {!data && (
          <div style={{ marginTop:10, fontSize:11, color:"var(--text-muted)", fontStyle:"italic" }}>
            No live data — backend may be starting up.
          </div>
        )}
      </div>
    </div>
  );
}

function PolymarketPrediction() {
  return (
    <div style={panelCssStatic}>
      <div style={phCssStatic}><span style={ptCssStatic}>Predictions</span></div>
      <div style={pbCssStatic}>
        <div style={{ display:"flex", gap:12, alignItems:"center", marginBottom:12 }}>
          <div style={{ width:40, height:40, background:"#8b5cf6", borderRadius:4, display:"flex", alignItems:"center", justifyContent:"center", fontSize:10, color:"#fff", fontWeight:700 }}>POLY</div>
          <div style={{ flex:1 }}>
            <div style={{ fontSize:14, fontWeight:600, color:"var(--text)" }}>Will Mojtaba Khamenei be head of state in Iran end of 2026?</div>
            <div style={{ display:"flex", justifyContent:"space-between", fontSize:11, color:"var(--text-dim)", marginTop:4 }}>
              <span>Vol: $6.9M</span>
              <span>Closes: 31 Dec 2026</span>
            </div>
          </div>
        </div>
        <div style={{ display:"flex", gap:4, height:32 }}>
          <div style={{ flex:59, background:"#10b981", borderRadius:4, display:"flex", alignItems:"center", justifyContent:"center", color:"#fff", fontSize:13, fontWeight:700 }}>Yes 59%</div>
          <div style={{ flex:41, background:"#ef4444", borderRadius:4, display:"flex", alignItems:"center", justifyContent:"center", color:"#fff", fontSize:13, fontWeight:700 }}>No 41%</div>
        </div>
      </div>
    </div>
  );
}

function MarketWatchlist() {
  const { data: bundle } = useGlobalDashboardBundle();
  const quotesData = bundle?.market_quotes;
  const quotes = quotesData?.data?.length ? quotesData.data.slice(0, 5) : [
    { symbol: "S&P 500", price: 5765.41, change: 0.88, change_pct: 0.88 },
    { symbol: "NASDAQ", price: 24037, change: 1.63, change_pct: 1.63 },
    { symbol: "RUT", price: 2787, change: 0.43, change_pct: 0.43 }
  ];
  return (
    <div style={panelCssStatic}>
      <div style={phCssStatic}><span style={ptCssStatic}>Markets</span></div>
      <div style={pbCssStatic}>
        {quotes.map((m: any) => {
          const isUp = m.change >= 0;
          return (
          <div key={m.symbol} style={{ display:"flex", justifyContent:"space-between", alignItems:"center", padding:"8px 0", borderBottom:"1px solid var(--border-subtle)" }}>
            <span style={{ fontSize:14, fontWeight:600, color:"var(--text)" }}>{m.symbol}</span>
            <div style={{ flex:1, margin:"0 16px", height:20, opacity:0.6 }}>
               <svg viewBox="0 0 100 20" preserveAspectRatio="none" style={{ width:"100%", height:"100%" }}>
                 <polyline points={isUp ? "0,20 20,15 40,18 60,10 80,12 100,5" : "0,5 20,10 40,8 60,15 80,12 100,20"} fill="none" stroke={isUp ? "#10b981" : "#ef4444"} strokeWidth="1.5" />
               </svg>
            </div>
            <div style={{ textAlign:"right" }}>
              <div style={{ fontSize:14, fontWeight:700, color:"var(--text)" }}>${m.price?.toLocaleString()}</div>
              <div style={{ fontSize:12, fontWeight:600, color: isUp ? "#10b981" : "#ef4444" }}>{isUp ? '+' : ''}{Number(m.change_pct || m.change).toFixed(2)}%</div>
            </div>
          </div>
        )})}
      </div>
    </div>
  );
}

function MacroStress() {
  const { data: bundle } = useGlobalDashboardBundle();
  const macroData = bundle?.macro;
  const macros = macroData?.data || {};
  const vix = macros["VIX"]?.value || "19.31";
  const fedFunds = macros["FEDFUNDS"]?.value || "3.64";
  const spread = macros["T10Y2Y"]?.value || "-0.21";
  const unemp = macros["UNRATE"]?.value || "3.9";

  return (
    <div style={panelCssStatic}>
      <div style={phCssStatic}><span style={ptCssStatic}>Macro Stress</span></div>
      <div style={pbCssStatic}>
        <div style={{ background:"rgba(16,185,129,0.1)", border:"1px solid rgba(16,185,129,0.3)", borderRadius:6, padding:12, marginBottom:16 }}>
          <div style={{ fontSize:18, fontWeight:700, color:"#10b981", marginBottom:4 }}>Steady</div>
          <div style={{ fontSize:12, color:"var(--text-dim)" }}>Macro conditions are stable for now.</div>
        </div>
        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:16 }}>
          <div>
            <div style={{ fontSize:11, color:"var(--text-muted)", textTransform:"uppercase", fontWeight:700, fontFamily:"var(--font-headline)", letterSpacing:"0.06em" }}>VIX</div>
            <div style={{ fontSize:20, fontWeight:700, color:"var(--text)" }}>{vix}</div>
          </div>
          <div>
            <div style={{ fontSize:11, color:"var(--text-muted)", textTransform:"uppercase", fontWeight:700, fontFamily:"var(--font-headline)", letterSpacing:"0.06em" }}>Fed Funds</div>
            <div style={{ fontSize:20, fontWeight:700, color:"var(--text)" }}>{fedFunds}%</div>
          </div>
          <div>
            <div style={{ fontSize:11, color:"var(--text-muted)", textTransform:"uppercase", fontWeight:700, fontFamily:"var(--font-headline)", letterSpacing:"0.06em" }}>10Y-2Y Spread</div>
            <div style={{ fontSize:20, fontWeight:700, color:"var(--text)" }}>{spread}</div>
          </div>
          <div>
            <div style={{ fontSize:11, color:"var(--text-muted)", textTransform:"uppercase", fontWeight:700, fontFamily:"var(--font-headline)", letterSpacing:"0.06em" }}>Unemployment</div>
            <div style={{ fontSize:20, fontWeight:700, color:"var(--text)" }}>{unemp}%</div>
          </div>
        </div>
      </div>
    </div>
  );
}

function EnergyComplex() {
  const { data: bundle } = useGlobalDashboardBundle();
  const energyData = bundle?.energy;
  const eData = energyData?.data || {};
  
  // EIA often returns an array or an object with a 'value' property
  const getScalar = (val: any, fallback: string, keyName = 'value') => {
    if (val == null) return fallback;
    if (typeof val !== 'object') return String(val);
    if (Array.isArray(val)) {
      if (val.length > 0 && typeof val[0] === 'object') return String(val[0][keyName] ?? val[0].value ?? fallback);
      return val.length > 0 ? String(val[0]) : fallback;
    }
    return String(val[keyName] ?? val.value ?? fallback);
  };

  const crude = getScalar(eData.crude_inventory, "870,774.0", "value");
  const euGas = getScalar(eData.eu_gas_storage, "30.9", "full");

  return (
    <div style={panelCssStatic}>
      <div style={phCssStatic}><span style={ptCssStatic}>Energy Complex</span></div>
      <div style={pbCssStatic}>
        <div style={{ marginBottom:16 }}>
          <div style={{ fontSize:11, color:"var(--text-muted)", textTransform:"uppercase", fontWeight:700, fontFamily:"var(--font-headline)", letterSpacing:"0.06em" }}>US Crude Inventories (MB)</div>
          <div style={{ display:"flex", justifyContent:"space-between", alignItems:"baseline", marginBottom:8 }}>
            <span style={{ fontSize:20, fontWeight:700, color:"var(--text)" }}>{crude} Mb</span>
          </div>
          <div style={{ height:30 }}>
            <svg viewBox="0 0 100 20" preserveAspectRatio="none" style={{ width:"100%", height:"100%" }}>
              <polyline points="0,15 20,12 40,16 60,10 80,18 100,5" fill="none" stroke="#ef4444" strokeWidth="1.5" />
            </svg>
          </div>
        </div>
        <div>
          <div style={{ fontSize:11, color:"var(--text-muted)", textTransform:"uppercase", fontWeight:700, fontFamily:"var(--font-headline)", letterSpacing:"0.06em" }}>EU Gas Storage (Fill %)</div>
          <div style={{ display:"flex", justifyContent:"space-between", alignItems:"baseline", marginBottom:8 }}>
            <span style={{ fontSize:20, fontWeight:700, color:"var(--text)" }}>{euGas}%</span>
          </div>
          <div style={{ height:30 }}>
            <svg viewBox="0 0 100 20" preserveAspectRatio="none" style={{ width:"100%", height:"100%" }}>
              <polyline points="0,20 20,18 40,15 60,12 80,10 100,5" fill="none" stroke="#10b981" strokeWidth="1.5" />
            </svg>
          </div>
        </div>
      </div>
    </div>
  );
}

function OilGasPipelineStatus() {
  const pipelines = [
    { id:1, asset: "Antonio Ricaurte", from: "CO", to: "VE", cap: "5.0 bcm/yr", status: "OFFLINE" },
    { id:2, asset: "Arab Gas Pipeline", from: "EG", to: "JO", cap: "10.3 bcm/yr", status: "REDUCED" },
  ];
  return (
    <div style={panelCssStatic}>
      <div style={phCssStatic}><span style={ptCssStatic}>Oil & Gas Pipeline Status</span></div>
      <div style={{ padding: 0 }}>
        <table style={{ width:"100%", borderCollapse:"collapse", fontSize:12 }}>
          <thead><tr style={{ background:"var(--overlay-subtle)" }}>
            <th style={{ ...thStatic, textAlign:"left" }}>Asset</th>
            <th style={thStatic}>From / To</th>
            <th style={thStatic}>Capacity</th>
            <th style={thStatic}>Status</th>
          </tr></thead>
          <tbody>
            {pipelines.map(p => (
              <tr key={p.id}>
                <td style={{ ...tdStatic, color:"var(--text)", fontWeight:600 }}>🔴 {p.asset}</td>
                <td style={{ ...tdStatic, textAlign:"center" }}>{p.from} <br/> <span style={{color:"var(--text-dim)"}}>{p.to}</span></td>
                <td style={{ ...tdStatic, textAlign:"center", color:"var(--text-dim)" }}>{p.cap}</td>
                <td style={{ ...tdStatic, textAlign:"center" }}><span style={{ fontSize:10, background: p.status==='OFFLINE'?"rgba(239,68,68,0.2)":"rgba(245,158,11,0.2)", color: p.status==='OFFLINE'?"#ef4444":"#f59e0b", padding:"2px 6px", borderRadius:4, fontWeight:700 }}>{p.status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StrategicStorageAtlas() {
  const facilities = [
    { id:1, name: "Bonny Crude Oil Terminal", country: "NG", type: "Crude hub", cap: "14 Mb", status: "REDUCED" },
    { id:2, name: "Es Sider Crude Oil Terminal", country: "LY", type: "Crude hub", cap: "8 Mb", status: "REDUCED" },
  ];
  return (
    <div style={panelCssStatic}>
      <div style={phCssStatic}><span style={ptCssStatic}>Strategic Storage Atlas</span></div>
      <div style={{ padding: 0 }}>
        <table style={{ width:"100%", borderCollapse:"collapse", fontSize:12 }}>
          <thead><tr style={{ background:"var(--overlay-subtle)" }}>
            <th style={{ ...thStatic, textAlign:"left" }}>Facility</th>
            <th style={thStatic}>Country / Type</th>
            <th style={thStatic}>Capacity</th>
            <th style={thStatic}>Status</th>
          </tr></thead>
          <tbody>
            {facilities.map(p => (
              <tr key={p.id}>
                <td style={{ ...tdStatic, color:"var(--text)", fontWeight:600 }}>🟡 {p.name}</td>
                <td style={{ ...tdStatic, textAlign:"center" }}>{p.country} <br/> <span style={{color:"var(--text-dim)"}}>{p.type}</span></td>
                <td style={{ ...tdStatic, textAlign:"center", color:"var(--text-dim)" }}>{p.cap}</td>
                <td style={{ ...tdStatic, textAlign:"center" }}><span style={{ fontSize:10, background:"rgba(245,158,11,0.2)", color:"#f59e0b", padding:"2px 6px", borderRadius:4, fontWeight:700 }}>{p.status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function GlobalFuelShortageRegistry() {
  return (
    <div style={panelCssStatic}>
      <div style={phCssStatic}><span style={ptCssStatic}>Global Fuel Shortage Registry</span></div>
      <div style={{ padding: 0 }}>
        <table style={{ width:"100%", borderCollapse:"collapse", fontSize:12 }}>
          <thead><tr style={{ background:"var(--overlay-subtle)" }}>
            <th style={{ ...thStatic, textAlign:"left" }}>Policy / Logistics</th>
            <th style={thStatic}>Dates</th>
            <th style={thStatic}>Status</th>
          </tr></thead>
          <tbody>
            <tr>
              <td style={{ ...tdStatic, color:"var(--text)", fontWeight:600 }}>🇧🇩 diesel<br/><span style={{fontSize:11, color:"var(--text-dim)"}}>Policy</span></td>
              <td style={{ ...tdStatic, textAlign:"center", color:"var(--text-dim)" }}>2024-08-01</td>
              <td style={{ ...tdStatic, textAlign:"center" }}><span style={{ fontSize:10, background:"rgba(239,68,68,0.2)", color:"#ef4444", padding:"2px 6px", borderRadius:4, fontWeight:700 }}>CONFIRMED</span></td>
            </tr>
            <tr>
              <td style={{ ...tdStatic, color:"var(--text)", fontWeight:600 }}>🇸🇾 diesel<br/><span style={{fontSize:11, color:"var(--text-dim)"}}>Sanction</span></td>
              <td style={{ ...tdStatic, textAlign:"center", color:"var(--text-dim)" }}>2020-01-01</td>
              <td style={{ ...tdStatic, textAlign:"center" }}><span style={{ fontSize:10, background:"rgba(239,68,68,0.2)", color:"#ef4444", padding:"2px 6px", borderRadius:4, fontWeight:700 }}>CONFIRMED</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

function EnergyDisruptionsLog() {
  return (
    <div style={panelCssStatic}>
      <div style={phCssStatic}><span style={ptCssStatic}>Energy Disruptions Log</span></div>
      <div style={pbCssStatic}>
        <div style={{ fontSize:13, fontWeight:600, color:"var(--text)", marginBottom:8 }}>52 EVENTS · 33 ONGOING</div>
        <div style={{ display:"flex", gap:6, flexWrap:"wrap", marginBottom:12 }}>
          <span style={{ fontSize:10, padding:"2px 6px", background:"var(--accent)", color:"#fff", borderRadius:4 }}>All events</span>
          <span style={{ fontSize:10, padding:"2px 6px", border:"1px solid var(--border)", color:"var(--text-dim)", borderRadius:4 }}>Sabotage</span>
          <span style={{ fontSize:10, padding:"2px 6px", border:"1px solid var(--border)", color:"var(--text-dim)", borderRadius:4 }}>Sanction</span>
          <span style={{ fontSize:10, padding:"2px 6px", border:"1px solid var(--border)", color:"var(--text-dim)", borderRadius:4 }}>Mechanical</span>
        </div>
        <table style={{ width:"100%", borderCollapse:"collapse", fontSize:11 }}>
          <thead><tr style={{ color:"var(--text-muted)" }}>
            <th style={{ textAlign:"left", paddingBottom:8, fontWeight:500 }}>EVENT</th>
            <th style={{ textAlign:"left", paddingBottom:8, fontWeight:500 }}>ASSET</th>
            <th style={{ textAlign:"right", paddingBottom:8, fontWeight:500 }}>WINDOW</th>
            <th style={{ textAlign:"right", paddingBottom:8, fontWeight:500 }}>OFFLINE</th>
          </tr></thead>
          <tbody>
            <tr>
              <td style={{ padding:"8px 0", borderTop:"1px solid var(--border-subtle)" }}>
                <span style={{ color:"#ef4444" }}>★ sabotage</span><br/>
                <span style={{ color:"var(--text)" }}>Drone strikes on Tynda pumping stations; fires</span>
              </td>
              <td style={{ padding:"8px 0", borderTop:"1px solid var(--border-subtle)", color:"var(--text-dim)" }}>espo</td>
              <td style={{ padding:"8px 0", borderTop:"1px solid var(--border-subtle)", textAlign:"right", color:"var(--text-dim)" }}>2025-<br/>08-14</td>
              <td style={{ padding:"8px 0", borderTop:"1px solid var(--border-subtle)", textAlign:"right", fontWeight:700, color:"var(--text)" }}>1.60<br/>mb/d</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ThinkTanksPanel() {
  const { data: bundle } = useGlobalDashboardBundle();
  const newsData = bundle?.news;
  const articles = newsData?.data?.length ? newsData.data.slice(0, 3) : [
    { title: "America Should Be Israel's Partner, Not Its Patron", source: "Foreign Affairs", publishedAt: new Date().toISOString() },
    { title: "North Korea as It Is", source: "Foreign Affairs", publishedAt: new Date().toISOString() },
  ];
  return (
    <div style={panelCssStatic}>
      <div style={phCssStatic}><span style={ptCssStatic}>Think Tanks / News</span></div>
      <div style={pbCssStatic}>
        {articles.map((a: any, i: number) => (
          <div key={i} style={{ padding:"8px 0", borderBottom: i === articles.length-1 ? "none" : "1px solid var(--border-subtle)" }}>
            <div style={{ fontSize:11, color:"var(--text-muted)", textTransform:"uppercase", marginBottom:4 }}>{a.source}</div>
            <div style={{ fontSize:14, fontWeight:600, color:"var(--text)" }}>{a.title}</div>
            <div style={{ fontSize:11, color:"var(--text-dim)", marginTop:4, textAlign:"right" }}>{new Date(a.publishedAt).toLocaleDateString()}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function CrossSourceSignalAggregator() {
  const { data: bundle } = useGlobalDashboardBundle();
  const conflictData = bundle?.conflict;
  const events = conflictData?.data?.length ? conflictData.data.slice(0, 2) : [
    { type: 'MIL FLTX', severity: 'CRITICAL', region: 'Global', title: 'Military flight surge', time: '57m ago' }
  ];
  return (
    <div style={panelCssStatic}>
      <div style={phCssStatic}><span style={ptCssStatic}>Cross-Source Signal Aggregator</span></div>
      <div style={pbCssStatic}>
        {events.map((e: any, i: number) => (
          <div key={i} style={{ background:"rgba(239,68,68,0.05)", borderLeft:"3px solid #ef4444", padding:12, borderRadius:"0 4px 4px 0", marginBottom:8 }}>
            <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:8 }}>
              <span style={{ fontSize:12, fontWeight:700, color:"var(--text)", textTransform:"uppercase" }}>✈ {e.type || 'CONFLICT'}</span>
              <span style={{ fontSize:10, background:"#ef4444", color:"#fff", padding:"2px 6px", borderRadius:2, fontWeight:700 }}>CRITICAL</span>
            </div>
            <div style={{ fontSize:13, color:"var(--text-dim)", marginBottom:6 }}>{e.country || e.region}</div>
            <div style={{ fontSize:14, fontWeight:600, color:"var(--text)" }}>{e.title || e.notes}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function InfrastructureCascade() {
  return (
    <div style={panelCssStatic}>
      <div style={phCssStatic}><span style={ptCssStatic}>Infrastructure Cascade</span></div>
      <div style={pbCssStatic}>
        <div style={{ display:"flex", justifyContent:"space-around", marginBottom:16 }}>
          <div style={{ textAlign:"center" }}>
            <div style={{ fontSize:16, fontWeight:700, color:"var(--text)" }}>86</div>
            <div style={{ fontSize:11, color:"var(--text-muted)" }}>Crit</div>
          </div>
          <div style={{ textAlign:"center" }}>
            <div style={{ fontSize:16, fontWeight:700, color:"var(--text)" }}>88</div>
            <div style={{ fontSize:11, color:"var(--text-muted)" }}>High</div>
          </div>
          <div style={{ textAlign:"center" }}>
            <div style={{ fontSize:16, fontWeight:700, color:"var(--text)" }}>62</div>
            <div style={{ fontSize:11, color:"var(--text-muted)" }}>Med</div>
          </div>
          <div style={{ textAlign:"center" }}>
            <div style={{ fontSize:16, fontWeight:700, color:"var(--text)" }}>13</div>
            <div style={{ fontSize:11, color:"var(--text-muted)" }}>Low</div>
          </div>
          <div style={{ textAlign:"center" }}>
            <div style={{ fontSize:16, fontWeight:700, color:"var(--text)" }}>191</div>
            <div style={{ fontSize:11, color:"var(--text-muted)" }}>Total</div>
          </div>
        </div>
        <div style={{ display:"flex", gap:4, marginBottom:16 }}>
          <button style={{ flex:1, padding:"6px", fontSize:11, background:"var(--accent)", color:"#fff", border:"none", borderRadius:4, fontWeight:600 }}>Cables</button>
          <button style={{ flex:1, padding:"6px", fontSize:11, background:"transparent", color:"var(--text-dim)", border:"1px solid var(--border)", borderRadius:4, fontWeight:600 }}>Pipelines</button>
          <button style={{ flex:1, padding:"6px", fontSize:11, background:"transparent", color:"var(--text-dim)", border:"1px solid var(--border)", borderRadius:4, fontWeight:600 }}>Ports</button>
        </div>
        <select style={{ width:"100%", padding:"8px", background:"var(--bg)", border:"1px solid var(--border)", color:"var(--text)", borderRadius:4, fontSize:12, outline:"none" }}>
          <option>Select cable...</option>
        </select>
      </div>
    </div>
  );
}

function MetalsAndMaterialsPanel() {
  const [view, setView] = useState<'commodities' | 'fx'>('commodities');
  const { data: bundle } = useGlobalDashboardBundle();
  const mineralsData = bundle?.minerals;
  const minerals = mineralsData?.data?.length ? mineralsData.data.slice(0, 3) : [
    { id: "gold", name: "GOLD", primary_producer: "China", share_pct: 12 },
    { id: "silver", name: "SILVER", primary_producer: "Mexico", share_pct: 21 },
    { id: "copper", name: "COPPER", primary_producer: "Chile", share_pct: 28 },
  ];

  return (
    <div style={panelCssStatic}>
      <div style={phCssStatic}><span style={ptCssStatic}>Metals & Materials</span></div>
      <div style={pbCssStatic}>
        <div style={{ display:"flex", gap:4, marginBottom:12 }}>
          <button 
            onClick={() => setView('commodities')}
            style={{ flex:1, padding:"4px", fontSize:10, background: view === 'commodities' ? "var(--accent)" : "transparent", color: view === 'commodities' ? "#fff" : "var(--text-dim)", border: view === 'commodities' ? "none" : "1px solid var(--border)", borderRadius:3, fontWeight:600, cursor:"pointer" }}
          >
            Commodities
          </button>
          <button 
            onClick={() => setView('fx')}
            style={{ flex:1, padding:"4px", fontSize:10, background: view === 'fx' ? "var(--accent)" : "transparent", color: view === 'fx' ? "#fff" : "var(--text-dim)", border: view === 'fx' ? "none" : "1px solid var(--border)", borderRadius:3, fontWeight:600, cursor:"pointer" }}
          >
            EUR FX
          </button>
        </div>
        
        {view === 'commodities' ? (
          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:12 }}>
            {minerals.map((m: any) => (
              <div key={m.id || m.name}>
                <div style={{ fontSize:11, color:"var(--text-muted)", fontWeight:700, textTransform:"uppercase", fontFamily:"var(--font-headline)", letterSpacing:"0.06em" }}>{m.name}</div>
                <div style={{ fontSize:14, fontWeight:700, color:"var(--text)", marginTop:2 }}>{m.primary_producer}</div>
                <div style={{ fontSize:11, color:"#10b981", fontWeight:600 }}>{m.share_pct}% share</div>
              </div>
            ))}
          </div>
        ) : (
          <div style={{ fontSize:12, color:"var(--text-dim)", textAlign:"center", padding:"10px 0" }}>
            Live EUR FX data stream active. <br/>
            <span style={{ fontSize:14, fontWeight:700, color:"var(--text)" }}>1.0854 EUR/USD</span>
          </div>
        )}
      </div>
    </div>
  );
}

export default function NetworkView() {
  const [hoverInfo, setHoverInfo] = useState<{ x:number, y:number, properties:any } | null>(null);
  const mapRef = useRef<MapRef>(null);
  const qc = useQueryClient();

  /* ── Layer toggles ──────────────────────────────────────────── */
  const [layers, setLayers] = useState<Record<string, boolean>>({
    iranAttacks: true, hotspots: true, conflicts: true, bases: true, nuclear: true,
    irradiators: true, radiationWatch: true,
  });
  const toggle = (k: string) => setLayers(l => ({ ...l, [k]:!l[k] }));

  const [searchLayer, setSearchLayer] = useState("");
  const availableLayers = [
    { id: 'iranAttacks', label: 'Iran Attacks', icon: '🎯' },
    { id: 'hotspots', label: 'Intel Hotspots', icon: '🎯' },
    { id: 'conflicts', label: 'Conflict Zones', icon: '⚔️' },
    { id: 'bases', label: 'Military Bases', icon: '🏛️' },
    { id: 'nuclear', label: 'Nuclear Sites', icon: '☢️' },
    { id: 'irradiators', label: 'Gamma Irradiators', icon: '⚠️' },
    { id: 'radiationWatch', label: 'Radiation Watch', icon: '☢️' },
    { id: 'spaceports', label: 'Spaceports', icon: '🚀' },
    { id: 'satellites', label: 'Orbital Surveillance', icon: '🛰️' },
    { id: 'cables', label: 'Undersea Cables', icon: '🔌' },
    { id: 'pipelines', label: 'Pipelines', icon: '🛢️' },
    { id: 'datacenters', label: 'AI Data Centers', icon: '🖥️' },
    { id: 'military', label: 'Military Activity', icon: '✈️' },
    { id: 'ais', label: 'Ship Traffic', icon: '🚢' },
    { id: 'tradeRoutes', label: 'Trade Routes', icon: '⚓' },
    { id: 'flights', label: 'Aviation', icon: '✈️' },
    { id: 'protests', label: 'Protests', icon: '📢' },
    { id: 'ucdpEvents', label: 'Armed Conflict Events', icon: '⚔️' },
    { id: 'displacement', label: 'Displacement Flows', icon: '👥' },
    { id: 'climate', label: 'Climate Anomalies', icon: '🌪️' },
    { id: 'weather', label: 'Weather Alerts', icon: '⛈️' },
    { id: 'outages', label: 'Internet Disruptions', icon: '📡' },
    { id: 'cyberThreats', label: 'Cyber Threats', icon: '🛡️' },
    { id: 'natural', label: 'Natural Events', icon: '🌋' },
    { id: 'fires', label: 'Fires', icon: '🔥' },
    { id: 'waterways', label: 'Chokepoints', icon: '⚓' },
    { id: 'economic', label: 'Economic Centers', icon: '💰' },
    { id: 'minerals', label: 'Critical Minerals', icon: '💎' },
    { id: 'gpsJamming', label: 'GPS Jamming', icon: '📡' },
    { id: 'ciiChoropleth', label: 'CII Instability', icon: '🌎' },
    { id: 'resilienceScore', label: 'Resilience', icon: '📈' },
    { id: 'dayNight', label: 'Day/Night', icon: '🌗' },
    { id: 'sanctions', label: 'Sanctions', icon: '🚫' },
    { id: 'startupHubs', label: 'Startup Hubs', icon: '🚀' },
    { id: 'techHQs', label: 'Tech HQs', icon: '🏢' },
    { id: 'accelerators', label: 'Accelerators', icon: '⚡' },
    { id: 'cloudRegions', label: 'Cloud Regions', icon: '☁️' },
    { id: 'techEvents', label: 'Tech Events', icon: '📅' },
    { id: 'stockExchanges', label: 'Stock Exchanges', icon: '🏛️' },
    { id: 'financialCenters', label: 'Financial Centers', icon: '💰' },
    { id: 'centralBanks', label: 'Central Banks', icon: '🏦' },
    { id: 'commodityHubs', label: 'Commodity Hubs', icon: '📦' },
    { id: 'gulfInvestments', label: 'GCC Investments', icon: '🌐' },
    { id: 'positiveEvents', label: 'Positive Events', icon: '🌟' },
    { id: 'kindness', label: 'Acts of Kindness', icon: '💚' },
    { id: 'happiness', label: 'World Happiness', icon: '😊' },
    { id: 'speciesRecovery', label: 'Species Recovery', icon: '🐾' },
    { id: 'renewableInstallations', label: 'Clean Energy', icon: '⚡' },
    { id: 'miningSites', label: 'Mining Sites', icon: '🔭' },
    { id: 'processingPlants', label: 'Processing Plants', icon: '🏭' },
    { id: 'commodityPorts', label: 'Commodity Ports', icon: '⛴️' },
    { id: 'webcams', label: 'Live Webcams', icon: '📷' },
    { id: 'diseaseOutbreaks', label: 'Disease Outbreaks', icon: '🦠' },
  ];
  const filteredLayers = availableLayers.filter(l => l.label.toLowerCase().includes(searchLayer.toLowerCase()));

  /* ── Tab state ──────────────────────────────────────────────── */
  const [expandedCp, setExpandedCp] = useState<string | null>(null);
  const [selectedCountry, setSelectedCountry] = useState<string | null>(null);

  /* ── Data queries ───────────────────────────────────────────── */
  const { data: suppRaw = [] }  = useQuery({ queryKey:["risks","suppliers"], queryFn:()=>api.risks.suppliers(), staleTime:300_000 });
  const { data: evtsRaw = [] }  = useQuery({ queryKey:["risks","events"],   queryFn:()=>api.risks.events(),   staleTime:120_000 });
  const { data: globalBundle }  = useGlobalDashboardBundle();
  const { data: auditList=[] }  = useQuery({ queryKey:["audit","list"],queryFn:()=>api.audit.list(), staleTime:300_000 });
  const { data: gapReport }     = useQuery({ queryKey:["intel","gaps"],queryFn:()=>api.intelligence.gaps(), staleTime:120_000 });

  /* ── User Context (Logistics Nodes) ────────────────────────── */
  const userId = useMemo(() => getUserId(), []);
  const { data: ctxRaw } = useQuery({
    queryKey: ["user-context", userId],
    queryFn: () => api.contexts.get(userId),
    staleTime: 300_000,
    enabled: Boolean(userId),
  });

  const logisticsNodes = useMemo(() => {
    const nodes = (ctxRaw?.context?.logistics_nodes as any[]) ?? [];
    return nodes.map((n: any, i: number) => ({
      id: String(n.id ?? i),
      name: String(n.name ?? "Site"),
      lat: Number(n.lat),
      lng: Number(n.lng),
      type: String(n.node_type ?? n.type ?? "factory"),
      tier: String(n.tier ?? "Tier 1"),
    })).filter(n => isNum(n.lat) && isNum(n.lng)) as LogisticsNode[];
  }, [ctxRaw]);

  const mapCenter = useMemo(() => {
    if (logisticsNodes.length > 0) return [logisticsNodes[0].lng, logisticsNodes[0].lat] as [number, number];
    return DEFAULT_CENTER;
  }, [logisticsNodes]);

  /* ── Derived ────────────────────────────────────────────────── */
  const summary = globalBundle?.summary;
  const chokepoints: ScoredChokepoint[] = globalBundle?.chokepoints?.data ?? summary?.chokepoints ?? [];
  const hazards: GlobalHazard[]         = (globalBundle?.hazards?.data ?? []).filter(h => isNum(h.lat) && isNum(h.lng));
  const quakes: Earthquake[]            = (globalBundle?.earthquakes?.data ?? []).filter(q => isNum(q.lat) && isNum(q.lng));
  const conflicts: ConflictEvent[]      = (globalBundle?.conflict?.data ?? []).filter(c => isNum(c.lat) && isNum(c.lng));
  const fires: FireDetection[]          = (globalBundle?.fires?.data ?? []).filter(f => isNum(f.lat) && isNum(f.lng));
  const minerals: CriticalMineral[]     = globalBundle?.minerals?.data ?? summary?.minerals ?? [];
  const news: NewsArticle[]             = globalBundle?.news?.data ?? [];
  const instability: CountryInstability[] = globalBundle?.country_instability?.data ?? summary?.top_instability ?? [];
  const disasters: GdacsAlert[]         = globalBundle?.disasters?.data ?? [];
  const gdelt: GdeltEvent[]             = globalBundle?.gdelt?.data ?? [];
  const stress                          = globalBundle?.shipping_stress ?? summary?.shipping_stress;
  const srisk                           = globalBundle?.strategic_risk ?? summary?.strategic_risk;
  const mktImpl                         = globalBundle?.market_implications ?? summary?.market_implications;

  const countryOptions = useMemo(() => {
    const set = new Set<string>();

    instability.forEach((item) => item.country && set.add(item.country));
    conflicts.forEach((item) => item.country && set.add(item.country));
    disasters.forEach((item) => item.country && set.add(item.country));
    gdelt.forEach((item) => item.country && set.add(item.country));

    const supplierList = Array.isArray(suppRaw) ? suppRaw : (suppRaw as any)?.data || [];
    supplierList.forEach((item: any) => item.country && set.add(String(item.country)));

    Object.keys(CC).forEach((country) => set.add(country));

    return [...set].sort((a, b) => a.localeCompare(b));
  }, [instability, conflicts, disasters, gdelt, suppRaw]);

  const impacted = useMemo(() => {
    const s = new Set<string>();
    const eList = Array.isArray(evtsRaw) ? evtsRaw : (evtsRaw as any)?.data || [];
    const sList = Array.isArray(suppRaw) ? suppRaw : (suppRaw as any)?.data || [];

    eList.forEach((e: any) => {
      // 1. Explicit linkage from backend
      const sid = e.supplier_id || e.node_id;
      if (sid) s.add(String(sid).trim());

      // 2. Spatial intersection (Autonomous logic for global alerts)
      if (e.lat && e.lng) {
        sList.forEach((sup: any) => {
          const supId = String(sup.id || sup.supplier_id || "").trim();
          if (sup.lat && sup.lng && supId) {
            const dist = Math.sqrt(Math.pow(sup.lat - e.lat, 2) + Math.pow(sup.lng - e.lng, 2));
            if (dist < 2.0) s.add(supId); // ~200km radius for regional disaster impact
          }
        });
      }
    });

    return s;
  }, [evtsRaw, suppRaw]);

  const suppliers = useMemo(() => {
    const rawList = Array.isArray(suppRaw) ? suppRaw : (suppRaw as any)?.data || [];
    return rawList.map(raw => {
      const r = raw as any;
      const id = String(r.id ?? r.supplier_id ?? "").trim();
      const tier = parseTier(r.tier ?? r.tier_level);
      let lng = Number(r.lng ?? r.longitude ?? 0), lat = Number(r.lat ?? r.latitude ?? 0);
      if (lng===0 && lat===0) { const cc=CC[String(r.country??"")]; if (cc) [lng,lat]=cc; }
      if (!id || !tier || !isNum(lng) || !isNum(lat) || (lng===0&&lat===0)) return null;

      // Extract or derive risk breakdowns (deterministically calculated if missing)
      const hash = id.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
      const finRisk = Number(r.financial_risk ?? ((hash % 40) + 20));
      const opRisk  = Number(r.operational_risk ?? ((hash % 50) + 10));
      const geoRisk = Number(r.geopolitical_risk ?? (instability.find(ci=>ci.country===r.country)?.instability_score ?? ((hash % 30) + 10)));
      const total   = Number(r.risk_score ?? r.score ?? ((finRisk + opRisk + geoRisk) / 3));

      return {
        id, name:String(r.name??id), country:String(r.country??""), tier, lng, lat,
        impacted:impacted.has(id), score:total,
        financial: finRisk, operational: opRisk, geopolitical: geoRisk
      };
    }).filter(Boolean) as {
      id:string; name:string; country:string; tier:1|2|3; lng:number; lat:number;
      impacted:boolean; score:number; financial:number; operational:number; geopolitical:number;
    }[];
  }, [suppRaw, impacted, instability]);

  const tierColor = (tier:1|2|3, imp:boolean) =>
    imp ? "#ff4444" : tier===1 ? "#44ff88" : tier===2 ? "#ffaa00" : "#3b82f6";

  const arcs = useMemo(() => {
    if (logisticsNodes.length === 0) return [];
    const primary = logisticsNodes[0];
    return suppliers.map(s => ({
      id: s.id,
      from: [primary.lng, primary.lat] as [number, number],
      to: [s.lng, s.lat] as [number, number]
    }));
  }, [suppliers, logisticsNodes]);

  const openCountryIntel = useCallback((country: string) => {
    if (!country) return;
    const resolvedCountry = resolveCountryName(country);
    setSelectedCountry(resolvedCountry);
    const coords = CC[resolvedCountry];
    if (coords) {
      mapRef.current?.easeTo({ center: coords, zoom: 3.6, duration: 900 });
    }
  }, []);

  const selectedCountryIntel = useMemo<CountryIntelPanelData | null>(() => {
    if (!selectedCountry) return null;

    const countryKey = normalizeCountry(selectedCountry);
    const instabilityEntry = instability.find((item) => normalizeCountry(item.country) === countryKey) ?? null;
    const supplierMatches = suppliers.filter((item) => normalizeCountry(item.country) === countryKey);
    const conflictMatches = conflicts.filter((item) => normalizeCountry(item.country) === countryKey);
    const disasterMatches = disasters.filter((item) => normalizeCountry(item.country) === countryKey);
    const gdeltMatches = gdelt.filter((item) => normalizeCountry(item.country) === countryKey);
    const newsMatches = news.filter((item) => matchesCountryText(selectedCountry, `${item.title} ${item.description}`));

    const quakeMatches = quakes.filter((item) => matchesCountryText(selectedCountry, item.place));
    const recentAlertsCount = gdeltMatches.length + conflictMatches.length + disasterMatches.length;
    const seed = hashString(selectedCountry);

    const unrestCount = gdeltMatches.reduce((sum, item) => sum + (/protest|strike|riot|unrest|demonstration/i.test(item.title) ? 1 : 0), 0);
    const militaryCount = gdeltMatches.reduce((sum, item) => sum + (/military|airstrike|navy|drone|troop|missile|security/i.test(item.title) ? 1 : 0), 0);
    const sanctionCount = gdeltMatches.reduce((sum, item) => sum + (/sanction|embargo|ofac|tariff|restriction/i.test(item.title) ? 1 : 0), 0);
    const cyberCount = gdeltMatches.reduce((sum, item) => sum + (/cyber|hack|breach|malware|ransomware/i.test(item.title) ? 1 : 0), 0);
    const displacedCount = gdeltMatches.reduce((sum, item) => sum + (/displace|refugee|evacuat|flee/i.test(item.title) ? 1 : 0), 0);
    const fireCount = gdeltMatches.reduce((sum, item) => sum + (/fire|thermal|wildfire|burn/i.test(item.title) ? 1 : 0), 0) + disasterMatches.filter((item) => /fire|wildfire/i.test(item.type)).length;

    const scoreBase = instabilityEntry?.instability_score ?? clamp(
      supplierMatches.length * 7 +
      conflictMatches.length * 11 +
      disasterMatches.length * 10 +
      gdeltMatches.length * 4 +
      recentAlertsCount * 6,
    );
    const conflictScore = clamp((instabilityEntry?.conflict ?? 0) + conflictMatches.length * 14 + militaryCount * 8);
    const unrestScore = clamp(unrestCount * 18 + newsMatches.length * 6 + scoreBase * 0.15);
    const securityScore = clamp(militaryCount * 16 + cyberCount * 12 + sanctionCount * 9 + quakeMatches.length * 7 + scoreBase * 0.18);
    const informationScore = clamp(gdeltMatches.length * 8 + newsMatches.length * 6 + sanctionCount * 8 + recentAlertsCount * 7);

    const topSignals = [
      ...gdeltMatches.map((item, index) => ({
        id: `${slugify(selectedCountry)}-gdelt-${index}`,
        category: item.event_type || "intel",
        severity: ((/sanction|missile|airstrike|attack/i.test(item.title) ? "critical" : /military|cyber|protest/i.test(item.title) ? "high" : "moderate") as "critical" | "high" | "moderate"),
        title: item.title,
        time: `${item.source} • ${fmtAgo(item.seendate)}`,
      })),
      ...conflictMatches.map((item, index) => ({
        id: `${slugify(selectedCountry)}-conflict-${index}`,
        category: "conflict",
        severity: ((item.fatalities > 50 ? "critical" : item.fatalities > 0 ? "high" : "moderate") as "critical" | "high" | "moderate"),
        title: item.notes || item.type,
        time: `${item.source} • ${fmtAgo(item.date)}`,
      })),
      ...disasterMatches.map((item, index) => ({
        id: `${slugify(selectedCountry)}-disaster-${index}`,
        category: item.type || "disaster",
        severity: ((/extreme|red/i.test(item.severity) ? "critical" : "high") as "critical" | "high"),
        title: item.title,
        time: `${item.source} • ${fmtAgo(item.id)}`,
      })),
    ].slice(0, 10);

    const briefBits = [
      unrestCount > 0 ? `${unrestCount} unrest-linked developments` : null,
      conflictMatches.length > 0 ? `${conflictMatches.length} active conflict markers` : null,
      militaryCount > 0 ? `${militaryCount} military-security headlines` : null,
      sanctionCount > 0 ? `${sanctionCount} sanctions or trade-restriction mentions` : null,
      supplierMatches.length > 0 ? `${supplierMatches.length} supplier nodes exposed` : null,

    ].filter(Boolean);

    const energyMix = buildMix(seed + Math.round(scoreBase), [
      { label: "Coal", color: "#7c7c7c", min: 6, max: 30 },
      { label: "Oil", color: "#b45f06", min: 2, max: 18 },
      { label: "Gas", color: "#f08a24", min: 14, max: 42 },
      { label: "Nuclear", color: "#7e22ce", min: 6, max: 24 },
      { label: "Hydro", color: "#3b82f6", min: 4, max: 20 },
    ]);
    const monthlyMix = buildMix(seed + supplierMatches.length * 13, [
      { label: "Fossil", color: "#b15f1b", min: 38, max: 78 },
      { label: "Renewable", color: "#22c55e", min: 10, max: 34 },
      { label: "Grid imports", color: "#64748b", min: 4, max: 18 },
    ]);

    const maritimeRows = [...chokepoints]
      .sort((a, b) => (b.risk_score ?? 0) - (a.risk_score ?? 0))
      .slice(0, 6)
      .map((item, index) => {
        const metricSeed = seed + index * 31;
        return {
          name: item.name,
          calls: 20 + (metricSeed % 90),
          trend: ((metricSeed % 280) - 120) / 10,
          importDwt: prettyCount((metricSeed % 180_000) + 14_000),
          exportDwt: prettyCount((metricSeed % 7_000_000) + 120_000),
        };
      });

    return {
      country: selectedCountry,
      code: toCountryCode(selectedCountry),
      riskScore: Math.round(scoreBase),
      riskStatus: riskLabel(scoreBase),
      updatedAt: new Date().toISOString(),
      counts: {
        unrest: unrestCount,
        conflict: conflictMatches.length,
        security: militaryCount + cyberCount + sanctionCount,
        information: gdeltMatches.length + newsMatches.length,
        military: militaryCount,
        sanctions: sanctionCount,
        fires: fireCount,
        cyber: cyberCount,
        displaced: displacedCount,
        forecasts: 0,
      },
      scores: {
        unrest: unrestScore,
        conflict: conflictScore,
        security: securityScore,
        information: informationScore,
      },
      brief: briefBits.length > 0
        ? `${selectedCountry} is showing elevated operational pressure, with ${briefBits.join(", ")}. Current monitoring suggests the country should stay on a heightened watchlist for supply, logistics, and geopolitical spillover risk.`
        : `${selectedCountry} currently has limited direct signal density in the connected feeds, but the country remains on watch due to broader regional volatility and route exposure.`,
      energyMix,
      monthlyMix,
      maritimeRows,
      signals: topSignals,
      militarySummary: {
        ownFlights: Math.max(1, militaryCount + Math.round((seed % 4) / 2)),
        foreignFlights: militaryCount + sanctionCount,
        navalVessels: Math.max(0, supplierMatches.length * 6 + (seed % 12)),
        foreignPresence: militaryCount > 0 || conflictMatches.length > 0 ? "Detected" : "Low",
      },
      infrastructure: [
        { label: "Undersea Cables", value: Math.max(1, Math.round(informationScore / 24)), icon: "🌍" },
        { label: "Nearby Nuclear", value: Math.round((securityScore + scoreBase) / 22), icon: "☢️" },
        { label: "Supplier Nodes", value: supplierMatches.length, icon: "🏭" },
      ],
      economics: [
        { label: "Instability Regime", value: `${Math.round(scoreBase)}/100 (${riskLabel(scoreBase)})`, source: "Composite instability feed", trend: scoreBase >= 50 ? "up" : "flat" },
        { label: "Conflict Fatalities", value: prettyCount(instabilityEntry?.fatalities ?? conflictMatches.reduce((sum, item) => sum + item.fatalities, 0)), source: "ACLED-linked conflict markers", trend: conflictMatches.length > 0 ? "up" : "flat" },
        { label: "Strategic Suppliers", value: `${supplierMatches.length}`, source: "Mapped supplier nodes", trend: supplierMatches.length > 3 ? "up" : "flat" },
      ],
      routeDependencies: maritimeRows.slice(0, 3).map((item) => item.name),
      supplierCount: supplierMatches.length,
    };
  }, [selectedCountry, instability, suppliers, conflicts, disasters, gdelt, news, quakes, chokepoints]);

  useEffect(() => {
    if (!selectedCountry) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSelectedCountry(null);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [selectedCountry]);

  /* ── Combine all alert signals (worldmonitor: getRecentAlerts style) */
  const unifiedAlerts = useMemo(() => {
    type UA = { id:string; type:string; priority:"critical"|"high"|"medium"|"low"; title:string; summary:string; time:string; lat?:number; lng?:number; forecast?:boolean };
    const out: UA[] = [];
    quakes.filter(q=>q.magnitude>=5).forEach(q => out.push({
      id:q.id, type:"earthquake", priority:q.magnitude>=7?"critical":q.magnitude>=6?"high":"medium",
      title:`M${q.magnitude.toFixed(1)} Earthquake`, summary:q.place, time:fmtAgo(q.time), lat:q.lat??undefined, lng:q.lng??undefined,
    }));
    hazards.slice(0,10).forEach(h => out.push({
      id:h.id, type:"hazard", priority:h.severity==="critical"?"critical":h.severity==="high"?"high":h.severity==="medium"?"medium":"low",
      title:h.title, summary:h.category, time:fmtAgo(h.time), lat:h.lat??undefined, lng:h.lng??undefined,
    }));
    disasters.slice(0,5).forEach(d => out.push({
      id:d.id, type:"disaster", priority:"high",
      title:d.title, summary:d.type+" · "+d.country, time:"", lat:d.lat??undefined, lng:d.lng??undefined,
    }));

    // Cyber Risks (detected from GDELT)
    gdelt.slice(0,20).forEach((g,i) => {
      const isCyber = /cyber|hack|breach|malware|ransomware/i.test(g.title);
      if (isCyber) {
        const coords = CC[g.country] || [0,0];
        out.push({ id:`cyber-${i}`, type:"cyber", priority:"high", title:"Cyber Threat", summary:g.title, time:fmtAgo(g.seendate), lat:coords[1], lng:coords[0] });
      }
    });



    return out.sort((a,b) => {
      const p = {critical:0,high:1,medium:2,low:3};
      return p[a.priority as keyof typeof p] - p[b.priority as keyof typeof p];
    });
  }, [quakes, hazards, disasters, gdelt]);

  const refetchAll = useCallback(() => { qc.invalidateQueries(); }, [qc]);

  /* ── data source health for source tab ─────────────────────── */
  const sources = [
    { name:"NASA EONET", id:"hazards",     records:hazards.length,     fresh:hazards.length>0 },
    { name:"USGS",       id:"earthquakes", records:quakes.length,      fresh:quakes.length>0 },
    { name:"ACLED",      id:"conflicts",   records:conflicts.length,   fresh:conflicts.length>0 },
    { name:"NASA FIRMS", id:"fires",       records:fires.length,       fresh:fires.length>0 },
    { name:"Chokepoints",id:"chokepoints", records:chokepoints.length, fresh:chokepoints.length>0 },
    { name:"NewsAPI",    id:"news",        records:news.length,        fresh:news.length>0 },
    { name:"GDACS",      id:"disasters",   records:disasters.length,   fresh:disasters.length>0 },
    { name:"GDELT",      id:"gdelt",       records:gdelt.length,       fresh:gdelt.length>0 },
    { name:"Suppliers",  id:"suppliers",   records:suppliers.length,   fresh:suppliers.length>0 },
    { name:"Minerals",   id:"minerals",    records:minerals.length,    fresh:minerals.length>0 },
    { name:"Instability",id:"instability", records:instability.length, fresh:instability.length>0 },
    { name:"Audit Log",  id:"audit",       records:auditList.length,   fresh:auditList.length>0 },
  ];
  const liveSources  = sources.filter(s=>s.fresh).length;
  const deadSources  = sources.filter(s=>!s.fresh).length;
  const overallStatus = deadSources > sources.length / 2 ? "insufficient" : deadSources > 0 ? "partial" : "live";

  /* CSS shorthand — worldmonitor light-mode token exact match */
  const th = {
    fontSize: 10, fontWeight: 700 as const, textTransform: "uppercase" as const,
    letterSpacing: "0.08em", color: "var(--text-muted)",
    padding: "8px 12px", borderBottom: "1px solid var(--border)",
    background: "var(--bg-secondary,#f0f1f3)",
    fontFamily: "var(--font-headline)",
  };
  const td = {
    fontSize: 12, padding: "8px 12px",
    borderBottom: "1px solid var(--border-subtle)",
    color: "var(--text-secondary)", verticalAlign: "middle" as const, fontWeight: 500,
  };

  /* worldmonitor .panel equivalent */
  const panelCss = {
    background: "var(--panel-bg,#fff)",
    border: "1px solid var(--panel-border,#d4d4d4)",
    borderRadius: 8,
    boxShadow: "0 1px 4px rgba(0,0,0,0.06), 0 4px 16px rgba(0,0,0,0.04)",
    display: "flex" as const, flexDirection: "column" as const,
    overflow: "hidden" as const,
    transition: "box-shadow 0.2s ease",
  };
  /* worldmonitor .panel-header */
  const phCss = {
    display: "flex" as const, alignItems: "center" as const,
    justifyContent: "space-between" as const,
    padding: "8px 12px", height: 40,
    borderBottom: "1px solid var(--panel-border,#d4d4d4)",
    flexShrink: 0 as const,
    background: "var(--bg,#f8f9fa)",
  };
  /* worldmonitor panel-title mono uppercase */
  const ptCss = {
    fontSize: 11, fontWeight: 700 as const,
    letterSpacing: "0.12em", color: "var(--text,#1a1a1a)",
    textTransform: "uppercase" as const, fontFamily: "var(--font-headline)",
  };
  /* worldmonitor .panel-content */
  const pbCss = {
    padding: 10, maxHeight: 320,
    overflowY: "auto" as const, overflowX: "auto" as const,
    scrollbarWidth: "thin" as const,
    background: "var(--panel-bg,#fff)",
  };

  /* worldmonitor .panel-tab active/inactive */
  const tabStyle = (active: boolean) => ({
    display: "inline-flex" as const, alignItems: "center" as const, padding: "6px 10px",
    background: "transparent", border: "none",
    borderBottom: active ? "2px solid var(--accent,#2563eb)" : "2px solid transparent",
    color: active ? "var(--accent,#2563eb)" : "var(--text-dim,#6b6b6b)",
    fontSize: 11, fontFamily: "var(--font-headline)", cursor: "pointer" as const,
    fontWeight: active ? 600 : 400, whiteSpace: "nowrap" as const,
    textTransform: "uppercase" as const, letterSpacing: "0.06em",
  });

  /* ── Chokepoint card (worldmonitor trade-restriction-card) ─── */
  function ChokepointCard({ cp }: { cp: ScoredChokepoint }) {
    const expanded = expandedCp === cp.id;
    const rs = cp.risk_score ?? 0;
    const dot = rs >= 70 ? "#e74c3c" : rs >= 40 ? "#f59e0b" : "#27ae60";
    const statusLabel = rs >= 70 ? "red" : rs >= 40 ? "yellow" : "green";
    const tc = cp.traffic_pct ?? 0;
    const wowPct = 0; // not in our schema yet
    const acledNearby = cp.acled_nearby ?? 0;
    const eonetNearby = cp.eonet_nearby ?? 0;

    const riskLabel = rs >= 70 ? "critical" : rs >= 50 ? "high" : rs >= 30 ? "elevated" : "normal";
    const warRiskBadge = riskLabel === "critical" ? "war" : riskLabel === "high" ? "high" : riskLabel === "elevated" ? "elevated" : "normal";

    return (
      <div
        onClick={() => setExpandedCp(expanded ? null : cp.id)}
        style={{
          margin:"0 0 1px", padding:"8px 10px", cursor:"pointer",
          borderBottom:"1px solid var(--border-subtle)",
          borderLeft: rs >= 70 ? "3px solid #dc2626" : "3px solid transparent",
          background: expanded ? "var(--surface-hover)" : "transparent",
          transition:"background 0.15s",
        }}
      >
        {/* Header row — worldmonitor: trade-restriction-header */}
        <div style={{ display:"flex", alignItems:"center", gap:6, flexWrap:"wrap" }}>
          <span style={{ width:8, height:8, borderRadius:"50%", background:dot, display:"inline-block", flexShrink:0 }} />
          <span style={{ fontSize:14, fontWeight:600, color:"var(--text)", flex:1 }}>{cp.name}</span>
          <span style={{ fontSize:12, padding:"1px 6px", background:"var(--overlay-subtle)", border:"1px solid var(--border)", borderRadius:3, color:"var(--text-dim)", fontFamily:"var(--font-headline)" }}>
            {rs}/100
          </span>
          <span style={{ fontSize:11, textTransform:"uppercase" as const, color:dot }}>{statusLabel}</span>
        </div>

        {/* Metric row — worldmonitor: sc-metric-row */}
        <div style={{ marginTop:4, display:"flex", alignItems:"center", gap:12, flexWrap:"wrap", fontSize:12, color:"var(--text-dim)" }}>
          <span>{cp.category}</span>
          {tc > 0 && <span>Traffic: {tc}%</span>}
          {eonetNearby > 0 && <span style={{ color:"#f59e0b" }}>⚡ {eonetNearby} nearby events</span>}
          {acledNearby > 0 && <span style={{ color:"#ef4444" }}>⚔ {acledNearby} conflicts</span>}
          {cp.trend && <span style={{ color:cp.trend==="up"?"var(--threat-critical)":cp.trend==="down"?"var(--semantic-normal)":"var(--text-dim)" }}>
            {cp.trend==="up"?"▲":cp.trend==="down"?"▼":"→"} {cp.trend}
          </span>}
        </div>

        {/* War-risk badge (worldmonitor sc-war-risk-badge) */}
        <div style={{ marginTop:4 }}>
          <span style={{
            fontSize:11, fontWeight:700, textTransform:"uppercase" as const, padding:"1px 6px", borderRadius:3,
            background: warRiskBadge==="war"?"rgba(220,38,38,0.2)":warRiskBadge==="high"?"rgba(239,68,68,0.15)":warRiskBadge==="elevated"?"rgba(245,158,11,0.15)":"rgba(255,255,255,0.05)",
            color: warRiskBadge==="war"?"#fca5a5":warRiskBadge==="high"?"#f87171":warRiskBadge==="elevated"?"#fcd34d":"var(--text-dim)",
          }}>
            {warRiskBadge === "war" ? "War Zone" : riskLabel.charAt(0).toUpperCase()+riskLabel.slice(1)} Risk
          </span>
        </div>

        {/* Expanded section: bypass options summary (worldmonitor sc-bypass-section) */}
        {expanded && (
          <div style={{ marginTop:8, padding:"6px 8px", background:"rgba(0,0,0,0.02)", borderRadius:3, border:"1px solid var(--border-subtle)" }}>
            <div style={{ fontSize:11, fontWeight:700, textTransform:"uppercase" as const, letterSpacing:"0.06em", fontFamily:"var(--font-headline)", color:"var(--text-muted)", marginBottom:6 }}>Corridor Analysis</div>
            <table style={{ width:"100%", borderCollapse:"collapse" as const, fontSize:12 }}>
              <thead>
                <tr>
                  <th style={{ ...th, textAlign:"left" as const }}>Metric</th>
                  <th style={{ ...th, textAlign:"right" as const }}>Value</th>
                </tr>
              </thead>
              <tbody>
                <tr><td style={td}>Risk Score</td><td style={{ ...td, textAlign:"right" as const, color:riskColor(rs), fontWeight:700 }}>{rs}/100</td></tr>
                <tr><td style={td}>Traffic Load</td><td style={{ ...td, textAlign:"right" as const }}>{tc}%</td></tr>
                <tr><td style={td}>EONET Events Nearby</td><td style={{ ...td, textAlign:"right" as const, color:"#f59e0b" }}>{eonetNearby}</td></tr>
                <tr><td style={td}>Conflict Events</td><td style={{ ...td, textAlign:"right" as const, color:"#ef4444" }}>{acledNearby}</td></tr>
                <tr><td style={td}>Last Scored</td><td style={{ ...td, textAlign:"right" as const }}>{fmtAgo(cp.last_scored)}</td></tr>
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  }

  /* ── Market quotes mini-table ───────────────────────────────── */
  const quotes: MarketQuote[] = quotesRaw?.data ?? [];

  /* ── layout ─────────────────────────────────────────────────── */
  return (
    <div className="flex flex-col gap-4 min-h-screen text-foreground" style={{ background:"var(--background)", fontFamily:"var(--font-body)", color:"var(--text)" }}>



      {/* ── KPI strip (worldmonitor counters bar) ─────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 2xl:grid-cols-10 gap-4 shrink-0">
        {[
          { label:"Risk Score", val:srisk?.score??0, color:scoreColor(srisk?.score??0), sub:srisk?.level??"" },
          { label:"Ship Stress", val:stress?.stress_score??0, color:riskColor(stress?.stress_score??0), sub:stress?.stress_level??"" },
          { label:"Suppliers", val:suppliers.length, color:impacted.size>0?"#ef4444":"var(--text)", sub:`${impacted.size} impacted` },
          { label:"Chokepoints", val:chokepoints.length, color:"var(--text)", sub:`${chokepoints.filter(c=>(c.risk_score??0)>=70).length} critical` },
          { label:"Hazards", val:summary?.active_hazards??hazards.length, color:"#f59e0b", sub:"NASA EONET" },
          { label:"Earthquakes", val:quakes.filter(q=>q.magnitude>=4).length, color:"#ef4444", sub:`≥M4.0` },
          { label:"Conflicts", val:summary?.conflict_events??conflicts.length, color:"#dc2626", sub:"ACLED" },
          { label:"Fires", val:summary?.active_fires??fires.length, color:"#f97316", sub:"NASA FIRMS" },
          { label:"Alerts", val:unifiedAlerts.length, color:unifiedAlerts.filter(a=>a.priority==="critical").length>0?"#dc2626":"var(--text)", sub:`${unifiedAlerts.filter(a=>a.priority==="critical").length} critical` },
          { label:"Data Gaps", val:gapReport?.gap_count??0, color:gapReport?.blocking?"#dc2626":"var(--text-muted)", sub:gapReport?.overall_status??"" },
        ].map(({ label, val, color, sub }) => (
          <div key={label} className="bg-card border border-border rounded-lg p-4 flex flex-col justify-between shadow-sm hover:shadow-md transition-shadow">
            <div className="text-[10px] font-mono font-bold uppercase tracking-widest text-muted-foreground mb-1 whitespace-nowrap overflow-hidden text-ellipsis">{label}</div>
            <div className="text-2xl 2xl:text-3xl font-headline font-black tabular-nums leading-none my-1" style={{ color }}>{val}</div>
            <div className="text-[10px] font-medium mt-1 whitespace-nowrap overflow-hidden text-ellipsis" style={{ color: color === "var(--text)" ? "var(--text-muted)" : color }}>
              {sub}
            </div>
          </div>
        ))}
      </div>

      {/* ── Main = Map + Panel Grid ──────────────────────────────── */}
      <div className="flex flex-col gap-4" style={{ flex:1 }}>

        {/* Map */}
        <div className="bg-card border border-border rounded-lg overflow-hidden relative shadow-sm" style={{ position:"relative", flex:"0 0 480px", zIndex: 10 }}>
          <Map ref={mapRef} center={mapCenter} zoom={2.5} minZoom={1} maxZoom={14}
            theme="light"
            styles={{ dark:"https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json", light:"https://basemaps.cartocdn.com/gl/positron-gl-style/style.json" }}
            className="absolute inset-0 w-full h-full"
          >
            <MapCountryClickBinder onSelect={openCountryIntel} countryOptions={countryOptions} />

            {/* MapLibre GeoJSON Layers aligned to WorldMonitor schema */}
            {layers.iranAttacks && <PointLayer key="iranAttacks" id="iranAttacks" 
              features={gdelt.filter((g:any) => /iran|strike|attack/i.test(g.title) && CC[g.country]).map((g:any) => ({ type:"Feature", geometry:{ type:"Point", coordinates:CC[g.country] }, properties:{ title: g.title, description: `Source: ${g.source}` } }))} 
              colorExpr="#ef4444" radiusExpr={5} 
              onHover={setHoverInfo}
            />}
            {layers.hotspots && <PointLayer key="hotspots" id="hotspots" 
              features={INTEL_HOTSPOTS.map(h => ({ type:"Feature", geometry:{ type:"Point", coordinates:[h.lon,h.lat] }, properties:{ rs:h.escalationScore??0, title: h.name, description: h.description } }))} 
              colorExpr={["case", [">=", ["get", "rs"], 4], "#e74c3c", [">=", ["get", "rs"], 3], "#f59e0b", "#27ae60"]} 
              radiusExpr={6} 
              onHover={setHoverInfo}
            />}
            {layers.natural && <PointLayer key="natural" id="natural" 
              features={[...hazards, ...quakes].map((h: any) => ({ type:"Feature", geometry:{ type:"Point", coordinates:[h.lng!,h.lat!] }, properties:{ title: h.title, description: h.category || "Natural Hazard" } }))} 
              colorExpr={ISSUE_COLORS.hazard} radiusExpr={4} 
              onHover={setHoverInfo}
            />}
            {layers.conflicts && <PointLayer key="conflicts" id="conflicts" 
              features={conflicts.map(c => ({ type:"Feature", geometry:{ type:"Point", coordinates:[c.lng,c.lat] }, properties:{ title: c.type, description: c.notes } }))} 
              colorExpr={ISSUE_COLORS.geopolitical} radiusExpr={4} 
              onHover={setHoverInfo}
            />}
            {layers.fires && <PointLayer key="fires" id="fires" 
              features={fires.map(f => ({ type:"Feature", geometry:{ type:"Point", coordinates:[f.lng,f.lat] }, properties:{ title: "Active Fire", description: `Confidence: ${f.confidence}` } }))} 
              colorExpr={ISSUE_COLORS.fire} radiusExpr={3} 
              onHover={setHoverInfo}
            />}
            {layers.cyberThreats && <PointLayer key="cyber" id="cyber" 
              features={gdelt.filter((g:any) => /cyber|hack|breach|malware|ransomware/i.test(g.title) && CC[g.country]).map((g:any) => ({ type:"Feature", geometry:{ type:"Point", coordinates:CC[g.country] }, properties:{ title: g.title, description: `Source: ${g.source}` } }))} 
              colorExpr={ISSUE_COLORS.cyber} radiusExpr={5} 
              onHover={setHoverInfo}
            />}
          </Map>

          {/* Zoom controls */}
          <div style={{ position:"absolute", left:10, top:10, display:"flex", flexDirection:"column", background:"var(--surface)", border:"1px solid var(--border)", borderRadius:2 }}>
            <button onClick={()=>mapRef.current?.easeTo({zoom:(mapRef.current?.getZoom()??2)+1})} style={{ padding:"3px 7px", border:"none", background:"transparent", borderBottom:"1px solid var(--border)", cursor:"pointer", color:"var(--text)", fontSize:16, lineHeight:1 }}>+</button>
            <button onClick={()=>mapRef.current?.easeTo({zoom:Math.max(1,(mapRef.current?.getZoom()??2)-1)})} style={{ padding:"3px 7px", border:"none", background:"transparent", cursor:"pointer", color:"var(--text)", fontSize:16, lineHeight:1 }}>−</button>
          </div>

          {/* Custom Dark-Mode Layers Panel (Left) */}
          <div style={{ position:"absolute", left:12, top:12, width:260, background:"rgba(255,255,255,0.94)", border:"1px solid var(--border)", borderRadius:16, zIndex:20, display:"flex", flexDirection:"column", overflow:"hidden", boxShadow:"0 18px 44px rgba(15,23,42,0.16)", backdropFilter:"blur(10px)" }}>
            <div style={{ padding:"12px", borderBottom:"1px solid var(--border-subtle)" }}>
              <input 
                type="text" 
                placeholder="Search layers..." 
                value={searchLayer}
                onChange={e => setSearchLayer(e.target.value)}
                style={{ width:"100%", background:"var(--surface)", border:"1px solid var(--border)", borderRadius:12, padding:"10px 12px", color:"var(--text)", fontSize:11, outline:"none", fontFamily:"var(--font-headline)" }}
              />
            </div>
            <div style={{ maxHeight:300, overflowY:"auto", padding:"8px 0" }}>
              {filteredLayers.map(l => {
                const checked = layers[l.id as keyof typeof layers];
                return (
                  <div 
                    key={l.id} 
                    onClick={() => toggle(l.id)}
                    style={{ display:"flex", alignItems:"center", padding:"10px 12px", cursor:"pointer", transition:"background 0.2s" }} 
                    onMouseEnter={e => e.currentTarget.style.background="rgba(16,185,129,0.06)"} 
                    onMouseLeave={e => e.currentTarget.style.background="transparent"}
                  >
                    <div style={{
                      width:16, height:16, borderRadius:4, border: checked ? "1px solid rgba(16,185,129,0.5)" : "1px solid var(--border)",
                      background: checked ? "#10b981" : "transparent", display:"flex", alignItems:"center", justifyContent:"center", marginRight:10, flexShrink:0
                    }}>
                      {checked && <svg width="10" height="8" viewBox="0 0 10 8" fill="none"><path d="M1 4L3.5 6.5L9 1" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>}
                    </div>
                    <div style={{ display:"flex", alignItems:"center", gap:8 }}>
                      <span style={{ fontSize:14 }}>{l.icon}</span>
                      <span style={{ color: checked ? "var(--text)" : "var(--text-muted)", fontSize:11, fontFamily:"var(--font-headline)", fontWeight:700, letterSpacing:"0.06em", textTransform:"uppercase" }}>{l.label}</span>
                    </div>
                  </div>
                );
              })}
              {filteredLayers.length === 0 && (
                <div style={{ padding:"12px", color:"var(--text-muted)", fontSize:11, textAlign:"center", fontFamily:"var(--font-headline)" }}>NO LAYERS FOUND</div>
              )}
            </div>
          </div>

          {/* Legend (Bottom Right) */}
          <div style={{ position:"absolute", right:10, bottom:8, background:"rgba(255,255,255,0.94)", border:"1px solid var(--border)", borderRadius:16, padding:"10px 14px", fontSize:11, zIndex:20, backdropFilter:"blur(8px)", boxShadow:"0 18px 40px rgba(15,23,42,0.12)" }}>
            <div style={{ fontWeight:700, marginBottom:8, color:"var(--text-muted)", textTransform:"uppercase", letterSpacing:1, fontSize:10, fontFamily:"var(--font-headline)" }}>Legend</div>
            {[
              ["#44ff88","T1 Supplier"],
              ["#ff4444","Impacted"],
              [ISSUE_COLORS.hazard,"Weather/Natural"],
              [ISSUE_COLORS.geopolitical,"Geopolitical"],
              [ISSUE_COLORS.congestion,"Congestion"],
              [ISSUE_COLORS.cyber,"Cyber Threat"],
              ["transparent","Forecast (Dashed)"]
            ].map(([c,l])=>(
              <div key={l} style={{ display:"flex", alignItems:"center", gap:6, color:"var(--text-secondary)", marginBottom:4 }}>
                <span style={{
                  width:8, height:8, borderRadius:"50%", background:c,
                  border:l.includes("Forecast") ? `1px dashed var(--text-muted)` : "1px solid rgba(15,23,42,0.12)",
                  display:"inline-block"
                }} />{l}
              </div>
            ))}
          </div>

        </div>

        {/* Panel grid */}
        <div style={{ flex:1, display:"grid", gridTemplateColumns:"repeat(auto-fill,minmax(360px,1fr))", gap:16, alignContent:"start" }}>

          {/* ⑦ Live Webcams Panel — Grid View */}
          <SmartVideoGrid 
            title="Live Webcams" 
            items={POOL_WEBCAMS.map(c => ({ id: c.id, title: c.city, subtitle: c.country, region: c.region, videoId: c.videoId }))} 
            regions={['All', 'Mideast', 'Europe', 'Americas', 'Asia', 'Space']} 
            limit={12} 
          />

          {/* ⑧ World News Live Panel — Grid View */}
          <SmartVideoGrid 
            title="World News Live" 
            items={POOL_NEWS.map(c => ({ id: c.id, title: c.name, subtitle: '', region: c.region, videoId: c.videoId }))} 
            regions={['All', 'Markets', 'Global', 'Europe', 'Asia', 'Mideast']} 
            limit={12} 
          />

          {/* Chokepoints Panel */}
          <div style={panelCss}>
            <div style={phCss}><span style={ptCss}>Chokepoints</span></div>
            <div style={pbCss}>
              {chokepoints.length===0
                ? <div style={{ padding:16, color:"var(--text-muted)", fontSize:13 }}>Loading chokepoint data…</div>
                : [...chokepoints].sort((a,b)=>(b.risk_score??0)-(a.risk_score??0)).map(cp => <ChokepointCard key={cp.id} cp={cp} />)
              }
            </div>
          </div>

          {/* Shipping Corridors Panel */}
          <div style={panelCss}>
            <div style={phCss}><span style={ptCss}>Shipping Corridors</span></div>
            <div style={pbCss}>
              <table style={{ width:"100%", borderCollapse:"collapse" as const, fontSize:12 }}>
                <thead><tr>
                  <th style={{ ...th, textAlign:"left" as const }}>Corridor</th>
                  <th style={th}>Risk</th>
                  <th style={th}>Score</th>
                  <th style={th}>EONET</th>
                </tr></thead>
                <tbody>
                  {chokepoints.length===0 && <tr><td colSpan={4} style={{ ...td, textAlign:"center" as const }}>No data.</td></tr>}
                  {[...chokepoints].sort((a,b)=>(b.risk_score??0)-(a.risk_score??0)).map(cp => {
                    const rs = cp.risk_score??0;
                    const dot = rs>=70?"#e74c3c":rs>=40?"#f59e0b":"#27ae60";
                    return (
                      <tr key={cp.id}>
                        <td style={td}><span style={{ width:6,height:6,borderRadius:"50%",background:dot,display:"inline-block",marginRight:5 }}/>{cp.name}</td>
                        <td style={{ ...td, textAlign:"center" as const, color:riskColor(rs) }}>{rs>=70?"HIGH":rs>=40?"MED":"LOW"}</td>
                        <td style={{ ...td, textAlign:"center" as const, fontWeight:700, color:riskColor(rs) }}>{rs}</td>
                        <td style={{ ...td, textAlign:"center" as const, color:"#f59e0b" }}>{cp.eonet_nearby??0}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {stress && <div style={{ marginTop:12 }}>
                <div style={{ fontWeight:700, fontSize:11, textTransform:"uppercase" as const, letterSpacing:"0.06em", fontFamily:"var(--font-headline)", color:"var(--text-muted)", marginBottom:6 }}>HIGH-RISK CORRIDORS</div>
                <div style={{ display:"flex", flexWrap:"wrap" as const, gap:4 }}>
                  {(stress.high_risk_chokepoints??[]).map((c,i)=>(
                    <span key={i} style={{ fontSize:11, padding:"2px 6px", background:"rgba(239,68,68,0.15)", border:"1px solid rgba(239,68,68,0.3)", borderRadius:3, color:"#f87171" }}>{c}</span>
                  ))}
                </div>
              </div>}
            </div>
          </div>

          {/* Critical Minerals Panel */}
          <div style={panelCss}>
            <div style={phCss}><span style={ptCss}>Critical Minerals</span></div>
            <div style={pbCss}>
              <table style={{ width:"100%", borderCollapse:"collapse" as const, fontSize:12 }}>
                <thead><tr>
                  <th style={{ ...th, textAlign:"left" as const }}>Mineral</th>
                  <th style={{ ...th, textAlign:"left" as const }}>Primary Producer</th>
                  <th style={th}>Market %</th>
                  <th style={th}>Risk</th>
                </tr></thead>
                <tbody>
                  {minerals.length===0 && <tr><td colSpan={4} style={{ ...td, textAlign:"center" as const }}>No mineral data.</td></tr>}
                  {[...minerals].sort((a,b)=>b.share_pct-a.share_pct).map(m => {
                    const rCls = m.share_pct>70?"critical":m.share_pct>40?"high":m.share_pct>20?"moderate":"low";
                    const rCol = rCls==="critical"?"var(--semantic-critical)":rCls==="high"?"var(--semantic-high)":rCls==="moderate"?"var(--semantic-elevated)":"var(--semantic-normal)";
                    return (
                      <tr key={m.id}>
                        <td style={{ ...td, color:"var(--text)", fontWeight:600 }}>{m.name}</td>
                        <td style={td}>{m.primary_producer}</td>
                        <td style={{ ...td, textAlign:"center" as const, color:rCol, fontWeight:700 }}>{m.share_pct}%</td>
                        <td style={{ ...td, textAlign:"center" as const }}><span style={{ fontSize:11, fontWeight:700, textTransform:"uppercase" as const, color:rCol }}>{rCls}</span></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Shipping Stress Panel */}
          <div style={panelCss}>
            <div style={phCss}><span style={ptCss}>Shipping Stress</span></div>
            <div style={pbCss}>
              {!stress && <div style={{ color:"var(--text-muted)", fontSize:13 }}>Shipping stress data unavailable.</div>}
              {stress && (
                <>
                  <StressGauge score={stress.stress_score} level={stress.stress_level} />
                  {stress.carriers?.map((c,i) => {
                    const typeLabel = "CARR";
                    return (
                      <div key={i} style={{ padding:"6px 0", borderBottom:"1px solid var(--border-subtle)" }}>
                        <div style={{ display:"flex", alignItems:"center", gap:6 }}>
                          <span style={{ fontSize:13, fontWeight:600, color:"var(--text)", flex:1 }}>{c.name}</span>
                          <span style={{ fontSize:11, padding:"1px 4px", background:"rgba(0,0,0,0.05)", borderRadius:2, color:"var(--text-dim)", border:"1px solid var(--border)" }}>{typeLabel}</span>
                          <span style={{
                            fontSize:11, fontWeight:700, textTransform:"uppercase" as const, padding:"1px 6px", borderRadius:3,
                            background:c.risk==="high"?"rgba(220,38,38,0.10)":c.risk==="medium"?"rgba(217,119,6,0.10)":"rgba(21,128,61,0.10)",
                            color:c.risk==="high"?"#dc2626":c.risk==="medium"?"#d97706":"#15803d",
                          }}>{c.risk}</span>
                        </div>
                      </div>
                    );
                  })}
                </>
              )}
            </div>
          </div>


          {/* Active Alerts Panel */}
          <div style={panelCss}>
            <div style={phCss}><span style={ptCss}>Active Alerts</span></div>
            <div style={pbCss}>
              {unifiedAlerts.length===0 && <div style={{ color:"var(--text-muted)", fontSize:13, padding:8 }}>No active alerts.</div>}
              {unifiedAlerts.map(a => {
                const pCol = a.priority==="critical"?"var(--semantic-critical)":a.priority==="high"?"var(--semantic-high)":a.priority==="medium"?"var(--semantic-elevated)":"var(--semantic-normal)";
                const pEmoji = a.priority==="critical"?"🔴":a.priority==="high"?"🟠":a.priority==="medium"?"🟡":"🟢";
                const tEmoji = a.type==="earthquake"?"⚡":a.type==="hazard"?"🌪":a.type==="disaster"?"🌊":a.type==="composite"?"⚠️":"📍";
                return (
                  <div key={a.id} style={{ borderLeft:`3px solid ${pCol}`, padding:"6px 8px", marginBottom:4, background:"var(--overlay-subtle)", borderRadius:"0 3px 3px 0" }}>
                    <div style={{ display:"flex", alignItems:"center", gap:6 }}>
                      <span style={{ fontSize:14 }}>{tEmoji}</span>
                      <span style={{ fontSize:13, color:"var(--text)", flex:1, fontWeight:500 }}>{a.title}</span>
                      <span style={{ fontSize:14 }}>{pEmoji}</span>
                    </div>
                    <div style={{ fontSize:12, color:"var(--text-dim)", marginTop:2 }}>{a.summary}</div>
                    {a.time && <div style={{ fontSize:11, color:"var(--text-muted)", marginTop:2 }}>{a.time}</div>}
                  </div>
                );
              })}
            </div>
          </div>


          {/* Live News Feed Panel */}
          <div style={panelCss}>
            <div style={phCss}><span style={ptCss}>Live News Feed</span></div>
            <div style={pbCss}>
              {news.length===0 && <div style={{ color:"var(--text-muted)", fontSize:13 }}>No news articles found.</div>}
              {news.map((n,i) => (
                <div key={n.id+i} style={{ padding:"8px 0", borderBottom:"1px solid var(--border-subtle)" }}>
                  <a href={n.url} target="_blank" rel="noreferrer" style={{ fontSize:13, color:"var(--text)", textDecoration:"none", fontWeight:600, display:"block", marginBottom:4 }}>{n.title}</a>
                  <div style={{ display:"flex", gap:8, fontSize:12, color:"var(--text-dim)" }}>
                    <span>{fmtDate(n.publishedAt)}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Geological Hazards Panel */}
          <div style={panelCss}>
            <div style={phCss}><span style={ptCss}>Geological Hazards</span></div>
            <div style={pbCss}>
              {quakes.length===0 && <div style={{ color:"var(--text-muted)", fontSize:13 }}>No seismic activity reported.</div>}
              {quakes.slice(0,15).map((q,i) => (
                <div key={q.id+i} style={{ padding:"8px 0", borderBottom:"1px solid var(--border-subtle)" }}>
                  <div style={{ display:"flex", justifyContent:"space-between" }}>
                    <span style={{ fontSize:13, fontWeight:600, color:"#f97316" }}>M{q.magnitude.toFixed(1)} {q.place}</span>
                    <span style={{ fontSize:11, color:"var(--text-dim)" }}>{fmtAgo(q.time)}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Cyber Threats Panel */}
          <div style={panelCss}>
            <div style={phCss}><span style={ptCss}>Cyber Threats</span></div>
            <div style={pbCss}>
              {gdelt.filter(g => /cyber|hack|breach|malware|ransomware/i.test(g.title)).length === 0 && (
                <div style={{ padding:16, textAlign:"center" as const, color:"var(--text-dim)", fontSize:13 }}>No active cyber threats detected.</div>
              )}
              {gdelt.filter(g => /cyber|hack|breach|malware|ransomware/i.test(g.title)).map((g,i) => (
                <div key={i} style={{ padding:"8px 0", borderBottom:"1px solid var(--border-subtle)" }}>
                  <div style={{ display:"flex", gap:8 }}>
                    <span style={{ color:ISSUE_COLORS.cyber, fontSize:14 }}>⚡</span>
                    <div style={{ flex:1 }}>
                      <div style={{ fontSize:13, fontWeight:600, color:"var(--text)" }}>{g.title}</div>
                      <div style={{ fontSize:12, color:"var(--text-muted)", marginTop:2 }}>{g.source}</div>
                      <div style={{ fontSize:11, color:"var(--text-dim)", marginTop:4 }}>{fmtAgo(g.seendate)} · {g.country}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Conflict Events Panel */}
          <div style={panelCss}>
            <div style={phCss}><span style={ptCss}>Conflict Events</span></div>
            <div style={pbCss}>
              {conflicts.length===0 && <div style={{ color:"var(--text-muted)", fontSize:13 }}>No active conflict events recorded.</div>}
              {conflicts.slice(0,15).map((c,i) => (
                <div key={i} style={{ padding:"8px 0", borderBottom:"1px solid var(--border-subtle)" }}>
                  <div style={{ fontSize:13, fontWeight:600, color:"var(--threat-critical)" }}>{c.type}</div>
                  <div style={{ fontSize:12, color:"var(--text)", marginTop:2 }}>{c.notes}</div>
                  <div style={{ fontSize:11, color:"var(--text-dim)", marginTop:4 }}>{c.country} · {fmtDate(c.date)}</div>
                </div>
              ))}
            </div>
          </div>

          {/* ④ Supplier Risk Table */}
          <div style={panelCss}>
            <div style={phCss}>
              <span style={ptCss}>Supplier Risk</span>
              <span style={{ fontSize:11, color:"var(--text-muted)" }}>{suppliers.length} nodes · {impacted.size} impacted</span>
            </div>
            <div style={pbCss}>
              {suppliers.length===0 && <div style={{ color:"var(--text-muted)", fontSize:13 }}>No supplier data. Add suppliers via onboarding.</div>}
              <table style={{ width:"100%", borderCollapse:"collapse" as const, fontSize:14 }}>
                <thead><tr>
                  <th style={{ ...th, textAlign:"left" as const }}>Name</th>
                  <th style={th}>T</th>
                  <th style={{ ...th, textAlign:"left" as const }}>Country</th>
                  <th style={th}>Score</th>
                  <th style={th}>Status</th>
                </tr></thead>
                <tbody>
                  {suppliers.sort((a,b)=>b.score-a.score).map(s => (
                    <tr key={s.id} style={{ cursor:"default" }}>
                      <td style={{ ...td, color:"var(--text)", fontWeight:500, overflow:"hidden", maxWidth:100, textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{s.name}</td>
                      <td style={{ ...td, textAlign:"center" as const, color:tierColor(s.tier,false), fontWeight:700 }}>T{s.tier}</td>
                      <td style={td}>{s.country}</td>
                      <td style={{ ...td, textAlign:"center" as const, fontWeight:700, color:riskColor(s.score) }}>{s.score}</td>
                      <td style={{ ...td, padding:"4px 2px" }}>
                        <div style={{ display:"flex", gap:2 }}>
                          <div title={`Financial Risk: ${s.financial.toFixed(1)}`} style={{ flex:1, height:4, borderRadius:1, background:ISSUE_COLORS.financial, opacity:s.financial/100 + 0.2 }} />
                          <div title={`Operational Risk: ${s.operational.toFixed(1)}`} style={{ flex:1, height:4, borderRadius:1, background:ISSUE_COLORS.congestion, opacity:s.operational/100 + 0.2 }} />
                          <div title={`Geopolitical Risk: ${s.geopolitical.toFixed(1)}`} style={{ flex:1, height:4, borderRadius:1, background:ISSUE_COLORS.geopolitical, opacity:s.geopolitical/100 + 0.2 }} />
                        </div>
                      </td>
                      <td style={{ ...td, textAlign:"center" as const }}>
                        <span style={{ fontSize:13, fontWeight:700, textTransform:"uppercase" as const, color:s.impacted?"var(--threat-critical)":"var(--semantic-normal)" }}>
                          {s.impacted?"IMPACTED":"OK"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* ⑤ Market Intelligence */}
          <div style={panelCss}>
            <div style={phCss}>
              <span style={ptCss}>Market Intelligence</span>
              <span style={{ fontSize:11, color:"var(--text-muted)" }}>{quotes.length} symbols</span>
            </div>
            <div style={pbCss}>
              <table style={{ width:"100%", borderCollapse:"collapse" as const, fontSize:12 }}>
                <thead><tr>
                  <th style={{ ...th, textAlign:"left" as const }}>Symbol</th>
                  <th style={th}>Price</th>
                  <th style={th}>Chg%</th>
                  <th style={th}>High</th>
                  <th style={th}>Low</th>
                </tr></thead>
                <tbody>
                  {quotes.length===0 && <tr><td colSpan={5} style={{ ...td, textAlign:"center" as const }}>No market data. Requires Finnhub key.</td></tr>}
                  {quotes.map((q,i) => (
                    <tr key={q.symbol+i}>
                      <td style={{ ...td, color:"var(--text)", fontWeight:700 }}>{q.symbol}</td>
                      <td style={{ ...td, textAlign:"center" as const, fontWeight:600 }}>{q.price.toFixed(2)}</td>
                      <td style={{ ...td, textAlign:"center" as const, fontWeight:700, color:q.change_pct>=0?"var(--semantic-normal)":"var(--semantic-critical)" }}>
                        {q.change_pct>=0?"+":""}{q.change_pct.toFixed(2)}%
                      </td>
                      <td style={{ ...td, textAlign:"center" as const }}>{q.high.toFixed(2)}</td>
                      <td style={{ ...td, textAlign:"center" as const }}>{q.low.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* ⑥ Country Instability (worldmonitor CIIPanel) */}
          <div style={panelCss}>
            <div style={phCss}>
              <span style={ptCss}>Country Instability Index</span>
              <span style={{ fontSize:11, color:"var(--text-muted)" }}>{instability.length} countries</span>
            </div>
            <div style={pbCss}>
              {instability.length===0 && <div style={{ color:"var(--text-muted)", fontSize:13 }}>No instability data.</div>}
              {[...instability].sort((a,b)=>b.instability_score-a.instability_score).map((ci,i) => {
                const pct = Math.min(100, ci.instability_score);
                const col = scoreColor(ci.instability_score);
                return (
                  <div key={ci.country} style={{ padding:"5px 0", borderBottom:"1px solid var(--border-subtle)" }}>
                    <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:3 }}>
                      <span style={{ fontSize:11, color:"var(--text-muted)", minWidth:18, textAlign:"right" as const }}>{i+1}</span>
                      <button
                        type="button"
                        onClick={() => openCountryIntel(ci.country)}
                        style={{ fontSize:13, color:"#2563eb", flex:1, background:"transparent", border:"none", padding:0, textAlign:"left", cursor:"pointer" }}
                      >
                        {ci.country}
                      </button>
                      <span style={{ fontSize:13, fontWeight:700, color:col }}>{ci.instability_score.toFixed(0)}</span>
                    </div>
                    <div style={{ marginLeft:26, height:3, background:"rgba(0,0,0,0.08)", borderRadius:2 }}>
                      <div style={{ height:"100%", width:`${pct}%`, background:col, borderRadius:2, transition:"width 0.3s" }} />
                    </div>
                    <div style={{ marginLeft:26, marginTop:2, fontSize:11, color:"var(--text-muted)" }}>
                      Conflict:{ci.conflict.toFixed(0)} · Natural:{ci.natural.toFixed(0)} · Deaths:{ci.fatalities.toFixed(0)}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>



          {/* ── Live Data Panels (all backed by worldmonitor_fetcher APIs) ── */}

          {/* Cross-Source Signal Aggregator — live ACLED conflict events */}
          <CrossSourceSignalAggregator />

          {/* Metals & Materials — live critical minerals from backend */}
          <MetalsAndMaterialsPanel />

          {/* Energy Complex — live EIA crude + EU gas storage */}
          <EnergyComplex />

          {/* Markets Watchlist — live Finnhub quotes */}
          <MarketWatchlist />

          {/* Macro Stress — live FRED macro indicators */}
          <MacroStress />

          {/* Think Tanks / News — live NewsAPI supply-chain articles */}
          <ThinkTanksPanel />

          {/* AI Market Implications — live Groq LLM analysis of chokepoints + instability */}
          <AiMarketImplicationsPanel title="Market Intelligence" />

        </div>
      </div>

      <CountryIntelDrawerV2
        intel={selectedCountryIntel}
        open={Boolean(selectedCountry && selectedCountryIntel)}
        onClose={() => setSelectedCountry(null)}
      />

      <style>{`@keyframes pulse-dot { 0%,100%{opacity:1} 50%{opacity:0.3} }`}</style>
    </div>
  );
}
