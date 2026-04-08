/**
 * Central API layer for Praecantator Frontend.
 * All data comes from the backend — no hardcoded values here.
 */

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const userId = localStorage.getItem("user_id") || "local-user";
  const token = localStorage.getItem("access_token") || "";
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      "X-User-Id": userId,
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options?.headers || {}),
    },
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
  workflowId?: string | null;
  body?: string;
}

export type RFQStatus = "Draft" | "Pending Approval" | "Sent" | "Responded" | "Closed";

export interface RFQThreadMessage {
  id: number;
  rfq_id: string;
  direction: "outbound" | "inbound" | "note";
  sender?: string | null;
  body: string;
  created_at: string;
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

export interface WorkflowAnalysisResponse {
  provider: "gemini" | "groq" | "local";
  analysis: string;
}

export interface WorkflowReportUpsertRequest {
  workflow_id: string;
  stage: "detect" | "assess" | "decide" | "act" | "audit";
  payload: Record<string, unknown>;
}

export interface AuthRegisterRequest {
  email: string;
  password: string;
  company_name?: string;
}

export interface AuthRegisterResponse {
  user_id: string;
  email: string;
  company_name: string;
}

export interface AuthLoginRequest {
  email: string;
  password: string;
}

export interface AuthLoginResponse {
  user_id: string;
  access_token: string;
  refresh_token: string;
}

export interface OnboardingCompleteRequest {
  user_id: string;
  company_name: string;
  industry: string;
  region: string;
  logistics_nodes: Record<string, unknown>[];
  suppliers: Record<string, unknown>[];
  backup_suppliers: Record<string, unknown>[];
  alert_threshold: number;
  transport_preferences: { sea: boolean; air: boolean; land: boolean };
  gmail_oauth_token?: string | null;
  slack_webhook?: string | null;
}

export interface OnboardingStatusResponse {
  user_id: string;
  complete: boolean;
  updated_at?: string;
}

export interface WorkflowReportSummary {
  workflow_id: string;
  updated_at: string;
  summary: Record<string, unknown>;
}

/* ─── Endpoints ─────────────────────────────────────────────── */

export const api = {
  auth: {
    register: (payload: AuthRegisterRequest) =>
      request<AuthRegisterResponse>("/auth/register", { method: "POST", body: JSON.stringify(payload) }),
    login: (payload: AuthLoginRequest) =>
      request<AuthLoginResponse>("/auth/login", { method: "POST", body: JSON.stringify(payload) }),
  },
  onboarding: {
    complete: (payload: OnboardingCompleteRequest) =>
      request<{ status: string; user_id: string; updated_at?: string }>("/onboarding/complete", { method: "POST", body: JSON.stringify(payload) }),
    status: (userId: string) => request<OnboardingStatusResponse>(`/onboarding/status/${encodeURIComponent(userId)}`),
  },
  contexts: {
    get: (userId: string) => request<{ user_id: string; updated_at?: string; context: Record<string, unknown> }>(`/contexts/${encodeURIComponent(userId)}`),
  },
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
  workflow: {
    analyze: (payload: { event: Record<string, unknown>; suppliers: Record<string, unknown>[]; assessment?: Record<string, unknown> }) =>
      request<WorkflowAnalysisResponse>("/workflow/analyze", { method: "POST", body: JSON.stringify(payload) }),
    upsertReportStage: (payload: WorkflowReportUpsertRequest) =>
      request<{ status: string; workflow_id: string; stage: string }>("/workflow/report", { method: "POST", body: JSON.stringify(payload) }),
    reportPdfUrl: (workflowId: string) => `${BASE}/workflow/report/${workflowId}/pdf`,
  },
  rfq: {
    list: (status?: string) => {
      const q = status ? `?status=${status}` : "";
      return request<RFQ[]>(`/rfq${q}`);
    },
    create: (data: Partial<RFQ>) =>
      request<RFQ>("/rfq", { method: "POST", body: JSON.stringify(data) }),
    updateStatus: (id: string, status: string) =>
      request<{ id: string; status: string }>(`/rfq/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify({ status }) }),
    thread: (id: string) => request<{ rfq_id: string; messages: RFQThreadMessage[] }>(`/rfq/${encodeURIComponent(id)}/thread`),
    addThreadMessage: (id: string, payload: { direction: "outbound" | "inbound" | "note"; sender?: string; body: string }) =>
      request<{ status: string; message: RFQThreadMessage }>(`/rfq/${encodeURIComponent(id)}/thread`, { method: "POST", body: JSON.stringify(payload) }),
  },
  workflows: {
    list: () => request<WorkflowReportSummary[]>("/workflows"),
    reportPdfUrl: (workflowId: string) => `${BASE}/workflow/report/${workflowId}/pdf`,
    reportJson: (workflowId: string) => request<Record<string, unknown>>(`/workflow/report/${encodeURIComponent(workflowId)}`),
  },
  compliance: {
    summary: () => request<{ total_workflows: number; avg_response_time_seconds: number; actions_breakdown: Record<string, number> }>("/audit/compliance"),
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
