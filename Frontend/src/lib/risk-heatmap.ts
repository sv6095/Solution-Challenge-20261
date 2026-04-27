import type { HeatmapData } from "@/types/workflow";
import type { Supplier } from "@/lib/api";

/** Map Riskwise-style band "1"…"5" to 0–100 heat intensity. */
export function averageRiskToScore(level: string): number {
  const n = Math.min(5, Math.max(1, parseInt(String(level).trim(), 10) || 1));
  return n * 20;
}

/** Bucket exposure score 0–100 into Riskwise-style 1–5 string. */
export function exposureScoreToRiskLevel(score: number): string {
  const s = Math.max(0, Math.min(100, score));
  if (s >= 80) return "5";
  if (s >= 60) return "4";
  if (s >= 40) return "3";
  if (s >= 20) return "2";
  return "1";
}

/**
 * Build HeatmapData rows from suppliers (country field + avg exposure per country).
 */
export function heatmapDataFromSuppliers(suppliers: Supplier[]): HeatmapData[] {
  const byCountry = new Map<string, { total: number; count: number }>();
  for (const s of suppliers) {
    const c = (s.country || "").trim() || "Unknown";
    const prev = byCountry.get(c) ?? { total: 0, count: 0 };
    prev.total += s.exposureScore;
    prev.count += 1;
    byCountry.set(c, prev);
  }
  const rows: HeatmapData[] = [];
  for (const [country, { total, count }] of byCountry) {
    const avg = count ? total / count : 0;
    const level = exposureScoreToRiskLevel(avg);
    rows.push({
      country,
      average_risk: level,
      breakdown: JSON.stringify({ avg_exposure: Math.round(avg * 10) / 10, suppliers: count }),
    });
  }
  return rows.sort((a, b) => a.country.localeCompare(b.country));
}

export type HeatPointInput = {
  id: string;
  title: string;
  description?: string;
  severity?: string;
  lng: number;
  lat: number;
  severity_score: number;
};

/**
 * Turn HeatmapData + representative lat/lng per country into MapCN heat points.
 */
export function heatmapDataToPoints(
  rows: HeatmapData[],
  latLngByCountry: Record<string, { lat: number; lng: number }>,
): HeatPointInput[] {
  return rows
    .map((row) => {
      const coords = latLngByCountry[row.country];
      if (!coords) return null;
      const point: HeatPointInput = {
        id: `country_${row.country}`,
        title: `${row.country} · risk band ${row.average_risk}/5`,
        description: row.breakdown,
        severity: "MEDIUM",
        lng: coords.lng,
        lat: coords.lat,
        severity_score: averageRiskToScore(row.average_risk),
      };
      return point;
    })
    .filter((p): p is HeatPointInput => p !== null);
}

export function transformEventsToHeatmap(events: Record<string, unknown>[]): NonNullable<HeatPointInput>[] {
  return events
    .filter((e) => e.lat != null && e.lng != null)
    .map((e) => {
      let severity = 50;
      const sevStr = String(e.severity || "").toUpperCase();
      if (sevStr === "CRITICAL") severity = 100;
      else if (sevStr === "HIGH") severity = 80;
      else if (sevStr === "MODERATE" || sevStr === "MEDIUM") severity = 60;
      else if (sevStr === "LOW") severity = 30;

      return {
        id: String(e.id || Math.random()),
        lat: Number(e.lat),
        lng: Number(e.lng),
        severity_score: severity,
        title: String(e.event_title || e.title || "Event"),
        description: String(e.description || ""),
      };
    });
}
