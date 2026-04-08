/**
 * Central API layer for Praecantator Frontend.
 * All data comes from the backend — no hardcoded values here.
 */

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status}`);
  return res.json() as Promise<T>;
}

/* ─── Types ─────────────────────────────────────────────────── */

export interface KpiSummary {
  totalSuppliers: number;
  activeRiskEvents: number;
  avgExposure: number;
  rfqsSent: number;
}

export interface RiskEvent {
  id: string;
  title: string;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  description: string;
  timestamp: string;
  analyst: string;
  lat: number;
  lng: number;
  region: string;
  url?: string;
}

export interface WorkflowEntry {
  id: string;
  title: string;
  description: string;
  timestamp: string;
  status: "complete" | "active" | "pending";
}

export interface Supplier {
  id: string;
  name: string;
  country: string;
  location: string;
  tier: string;
  category: string;
  exposureScore: number;
  trend: "up" | "down" | "stable";
  status: "Critical" | "High" | "Medium" | "Low";
  lat: number;
  lng: number;
}

export interface Route {
  id: string;
  label: string;
  origin: string;
  originLng: number;
  originLat: number;
  destination: string;
  destinationLng: number;
  destinationLat: number;
  transitDays: string;
  costMin: number;
  costMax: number;
  riskScore: number;
  recommended: boolean;
  coordinates?: [number, number][];
}

export interface WorkflowRouteRequest {
  origin: { lat: number; lng: number; country_code: string };
  destination: { lat: number; lng: number; country_code: string };
  target_currency?: string;
}

export interface WorkflowRoutesResponse {
  route_comparison: Array<Record<string, unknown>>;
  currency_risk_index: number;
  recommended_mode: "sea" | "air" | "land";
}

export interface NaturalHazard {
  id: string;
  type: string;
  title: string;
  location: string;
  time: string;
  severity: "High" | "Medium" | "Low";
  lat: number;
  lng: number;
  url?: string;
}

export interface NewsSignal {
  id: string;
  source: string;
  title: string;
  location: string;
  time: string;
  relevanceScore: number;
  url: string;
}

export interface DataSource {
  id: string;
  name: string;
  active: boolean;
  lastFetch: string;
  recordCount: number;
  latencyMs: number | null;
}

export interface AuditEntry {
  id: string;
  event: string;
  suppliers: string;
  decision: string;
  executedBy: string;
  timestamp: string;
  durationMs: number;
}

export interface RFQ {
  id: string;
  supplier: string;
  eventTrigger: string;
  dateSent: string;
  status: "Draft" | "Sent" | "Responded" | "Closed";
}

export interface UserProfile {
  name: string;
  email: string;
  company: string;
  role: string;
}

export interface BillingInfo {
  plan: string;
  monthlyRate: number;
  workflowRunsUsed: number;
  workflowRunsLimit: number;
  rfqsSent: number;
  suppliersUsed: number;
  suppliersLimit: number;
}

export interface NetworkHub {
  id: string;
  city: string;
  lng: number;
  lat: number;
  type: "primary" | "secondary";
  shipments: number;
  region: "west" | "midwest" | "south" | "northeast";
}

export interface NetworkRoute {
  from: string;
  to: string;
  mode: "air" | "ground";
  shipments: number;
  status: "active" | "delayed";
}

export interface NetworkGraphResponse {
  hubs: NetworkHub[];
  routes: NetworkRoute[];
}

/* ─── Endpoints ─────────────────────────────────────────────── */

export const api = {
  dashboard: {
    kpis: () => request<KpiSummary>("/dashboard/kpis"),
    events: () => request<RiskEvent[]>("/dashboard/events"),
    workflows: () => request<WorkflowEntry[]>("/dashboard/workflows"),
    suppliers: () => request<Supplier[]>("/dashboard/suppliers?limit=5"),
  },
  risks: {
    events: (params?: { region?: string; severity?: string }) => {
      const clean = Object.fromEntries(
        Object.entries(params ?? {}).filter(([, v]) => v !== undefined && v !== null && `${v}` !== "undefined")
      ) as Record<string, string>;
      const q = new URLSearchParams(clean).toString();
      return request<RiskEvent[]>(`/risks/events${q ? `?${q}` : ""}`);
    },
    suppliers: (params?: { tier?: string; minScore?: number; maxScore?: number }) => {
      const clean = Object.fromEntries(
        Object.entries(params ?? {}).filter(([, v]) => v !== undefined && v !== null && `${v}` !== "undefined")
      ) as Record<string, string>;
      const q = new URLSearchParams(clean).toString();
      return request<Supplier[]>(`/risks/suppliers${q ? `?${q}` : ""}`);
    },
  },
  routes: {
    list: (origin?: string, destination?: string, mode?: string) => {
      const q = new URLSearchParams({
        ...(origin ? { origin } : {}),
        ...(destination ? { destination } : {}),
        ...(mode ? { mode } : {}),
      }).toString();
      return request<Route[]>(`/routes${q ? `?${q}` : ""}`);
    },
    workflow: (payload: WorkflowRouteRequest) =>
      request<WorkflowRoutesResponse>("/workflow/routes", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
  },
  signals: {
    hazards: () => request<NaturalHazard[]>("/signals/hazards"),
    news: () => request<NewsSignal[]>("/signals/news"),
    sources: () => request<DataSource[]>("/signals/sources"),
  },
  audit: {
    list: () => request<AuditEntry[]>("/audit"),
    exportPdf: (id: string) => `${BASE}/audit/${id}/pdf`,
    exportAll: () => `${BASE}/audit/export`,
  },
  rfq: {
    list: (status?: string) => {
      const q = status ? `?status=${status}` : "";
      return request<RFQ[]>(`/rfq${q}`);
    },
    create: (data: Partial<RFQ>) =>
      request<RFQ>("/rfq", { method: "POST", body: JSON.stringify(data) }),
  },
  exposure: {
    summary: () => request<{ avgScore: number; criticalNodes: number; totalMonitored: number }>("/exposure/summary"),
    suppliers: () => request<Supplier[]>("/exposure/suppliers"),
  },
  settings: {
    profile: () => request<UserProfile>("/settings/profile"),
    updateProfile: (data: Partial<UserProfile>) =>
      request<UserProfile>("/settings/profile", { method: "PATCH", body: JSON.stringify(data) }),
    billing: () => request<BillingInfo>("/settings/billing"),
  },
  network: {
    graph: () => request<NetworkGraphResponse>("/network/graph"),
  },
};
