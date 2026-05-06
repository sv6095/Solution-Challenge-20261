/**
 * Central API layer for Praecantator Frontend.
 * All data comes from the backend — no hardcoded values here.
 */

import type { ReasoningStep } from "@/types/workflow";

function normalizeApiBase(rawBase?: string): string {
  const value = (rawBase || "").trim();
  if (!value) return "/api";
  return value.endsWith("/") ? value.slice(0, -1) : value;
}

const BASE = normalizeApiBase(
  import.meta.env.VITE_API_URL ?? import.meta.env.VITE_API_BASE_URL ?? "/api",
);

type AuthPersistence = "local" | "session";

const ACCESS_TOKEN_KEY = "access_token";
const REFRESH_TOKEN_KEY = "refresh_token";
const USER_ID_KEY = "user_id";
const PERSISTENCE_KEY = "auth_persistence";
/** `local` = backend JWT from email/password; `firebase` = Firebase ID token (e.g. Google sign-in). */
const AUTH_KIND_KEY = "auth_kind";

export type AuthKind = "local" | "firebase";

export function getAuthKind(): AuthKind {
  const v = readStoredValue(AUTH_KIND_KEY).trim().toLowerCase();
  return v === "firebase" ? "firebase" : "local";
}

function readStoredValue(key: string): string {
  return sessionStorage.getItem(key) || localStorage.getItem(key) || "";
}

function writeStoredValue(key: string, value: string, persistence: AuthPersistence): void {
  const primary = persistence === "local" ? localStorage : sessionStorage;
  const secondary = persistence === "local" ? sessionStorage : localStorage;
  if (value) {
    primary.setItem(key, value);
  } else {
    primary.removeItem(key);
  }
  secondary.removeItem(key);
}

export function getAccessToken(): string {
  return readStoredValue(ACCESS_TOKEN_KEY);
}

export function getRefreshToken(): string {
  return readStoredValue(REFRESH_TOKEN_KEY);
}

export function getUserId(): string {
  return readStoredValue(USER_ID_KEY);
}

export function getAuthPersistence(): AuthPersistence {
  return readStoredValue(PERSISTENCE_KEY) === "local" ? "local" : "session";
}

export function storeAuthSession(payload: {
  userId: string;
  accessToken: string;
  refreshToken?: string;
  rememberMe?: boolean;
  authKind?: AuthKind;
}): void {
  const persistence: AuthPersistence = payload.rememberMe ? "local" : getAuthPersistence();
  const resolvedPersistence: AuthPersistence = payload.rememberMe === undefined ? persistence : (payload.rememberMe ? "local" : "session");
  writeStoredValue(USER_ID_KEY, payload.userId, resolvedPersistence);
  writeStoredValue(ACCESS_TOKEN_KEY, payload.accessToken, resolvedPersistence);
  writeStoredValue(REFRESH_TOKEN_KEY, payload.refreshToken || getRefreshToken(), resolvedPersistence);
  writeStoredValue(PERSISTENCE_KEY, resolvedPersistence, resolvedPersistence);
  const kind: AuthKind =
    payload.authKind ?? (readStoredValue(AUTH_KIND_KEY) === "firebase" ? "firebase" : "local");
  writeStoredValue(AUTH_KIND_KEY, kind, resolvedPersistence);
}

export function clearAuthSession(): void {
  for (const storage of [localStorage, sessionStorage]) {
    storage.removeItem(ACCESS_TOKEN_KEY);
    storage.removeItem(REFRESH_TOKEN_KEY);
    storage.removeItem(USER_ID_KEY);
    storage.removeItem(PERSISTENCE_KEY);
    storage.removeItem(AUTH_KIND_KEY);
  }
  void import("firebase/auth").then(({ signOut, getAuth }) => {
    void import("@/lib/firebase").then(({ getFirebaseApp }) => {
      const fa = getFirebaseApp();
      if (fa) void signOut(getAuth(fa)).catch(() => undefined);
    });
  });
}

let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    if (getAuthKind() === "firebase") {
      try {
        const { getFirebaseApp } = await import("@/lib/firebase");
        const { getAuth } = await import("firebase/auth");
        const fa = getFirebaseApp();
        if (!fa) return null;
        const auth = getAuth(fa);
        const u = auth.currentUser;
        if (!u) {
          clearAuthSession();
          return null;
        }
        const t = await u.getIdToken(true);
        storeAuthSession({
          userId: u.uid,
          accessToken: t,
          refreshToken: getRefreshToken(),
          rememberMe: getAuthPersistence() === "local",
          authKind: "firebase",
        });
        return t;
      } catch {
        return null;
      }
    }

    const refreshToken = getRefreshToken();
    if (!refreshToken) return null;

    const headers = new Headers();
    headers.set("Content-Type", "application/json");
    headers.set("X-User-Id", getUserId());

    try {
      const response = await fetch(`${BASE}/auth/refresh`, {
        method: "POST",
        headers,
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!response.ok) {
        clearAuthSession();
        return null;
      }

      const payload = await response.json() as AuthLoginResponse;
      storeAuthSession({
        userId: payload.user_id || getUserId(),
        accessToken: payload.access_token,
        refreshToken: payload.refresh_token || refreshToken,
        rememberMe: getAuthPersistence() === "local",
        authKind: "local",
      });
      return payload.access_token;
    } catch {
      return null;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

async function request<T>(path: string, options?: RequestInit, retryOnAuthFailure = true): Promise<T> {
  const userId = getUserId();
  const token = getAccessToken();
  const callerHeaders = new Headers(options?.headers);
  const headers = new Headers();
  headers.set("Content-Type", "application/json");
  if (userId) {
    headers.set("X-User-Id", userId);
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  callerHeaders.forEach((value, key) => {
    headers.set(key, value);
  });
  if (userId && !headers.has("X-User-Id")) {
    headers.set("X-User-Id", userId);
  }
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  let res: Response;
  try {
    const { headers: _ignoredHeaders, ...restOptions } = options ?? {};
    res = await fetch(`${BASE}${path}`, {
      ...restOptions,
      headers,
    });
  } catch {
    throw new Error(
      "Backend unreachable. Start FastAPI on 127.0.0.1:8000 or set VITE_API_URL to a live API base.",
    );
  }
  if (
    res.status === 401 &&
    retryOnAuthFailure &&
    path !== "/auth/login" &&
    path !== "/api/auth/login" &&
    path !== "/auth/refresh" &&
    path !== "/api/auth/refresh"
  ) {
    const refreshedToken = await refreshAccessToken();
    if (refreshedToken) {
      const retryHeaders = new Headers(options?.headers);
      retryHeaders.set("Authorization", `Bearer ${refreshedToken}`);
      return request<T>(path, { ...options, headers: retryHeaders }, false);
    }
  }

  if (!res.ok) {
    let message = `API ${path} failed: ${res.status}`;
    try {
      const errorBody = await res.json() as { detail?: unknown; message?: string };
      if (typeof errorBody?.message === "string" && errorBody.message.trim()) {
        message = errorBody.message.trim();
      } else if (typeof errorBody?.detail === "string" && errorBody.detail.trim()) {
        message = errorBody.detail.trim();
      } else if (
        errorBody?.detail &&
        typeof errorBody.detail === "object" &&
        "message" in (errorBody.detail as Record<string, unknown>) &&
        typeof (errorBody.detail as Record<string, unknown>).message === "string"
      ) {
        message = String((errorBody.detail as Record<string, unknown>).message);
      }
    } catch {
      // Keep the fallback HTTP status message when the response body is not JSON.
    }
    throw new Error(message);
  }
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
  [key: string]: unknown;
}

export type { ReasoningStep } from "@/types/workflow";

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
  /** When set, routing_agent reasoning steps attach to this workflow in the backend. */
  workflow_id?: string | null;
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
  label: string;
  category: string;
  source_url: string;
  active: boolean;
  lastFetch: string;
  recordCount: number;
  latencyMs: number | null;
}

export interface CategorizedSignal {
  id: string;
  event_type: string;
  title: string;
  location: string;
  severity: string;
  severity_raw: number;
  lat: number;
  lng: number;
  source: string;
  source_category: string;
  url: string;
  time: string;
  // sentiment fields
  sentiment_topic?: string | null;
  sentiment_positive_pct?: number | null;
  sentiment_negative_pct?: number | null;
  sentiment_neutral_pct?: number | null;
  sentiment_post_count?: number | null;
  sentiment?: string | null;
  sentiment_score?: number | null;
}

export interface CategorizedSignals {
  disaster: CategorizedSignal[];
  geopolitical: CategorizedSignal[];
  news: CategorizedSignal[];
  regulatory: CategorizedSignal[];
  sentiment: CategorizedSignal[];
  humanitarian: CategorizedSignal[];
  social_news: CategorizedSignal[];
  maritime?: CategorizedSignal[];
  trade?: CategorizedSignal[];
}

export interface SentimentSignal {
  id: string;
  source: string;
  topic: string;
  positive_pct: number;
  negative_pct: number;
  neutral_pct: number;
  post_count: number;
  time: string;
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

export interface AgentChatResponse {
  conversation_id: string;
  sequence: string[];
  route: Record<string, unknown>;
  supervisor?: Record<string, unknown>;
  outputs: Record<string, unknown>;
  text: string;
}

export interface WorkflowReportUpsertRequest {
  workflow_id: string;
  stage: "detect" | "assess" | "decide" | "act" | "audit";
  payload: Record<string, unknown>;
}

export interface WorkflowStartResponse {
  status: string;
  workflow_id: string;
  state: Record<string, unknown>;
}

export interface WorkflowStateResponse {
  workflow_id: string;
  status: string;
  state: Record<string, unknown>;
  event: Record<string, unknown>;
}

export interface AuthRegisterRequest {
  email: string;
  password: string;
  company_name?: string;
  full_name?: string;
}

export interface AuthRegisterResponse {
  user_id: string;
  email: string;
  company_name: string;
  full_name: string;
}

export interface AuthProfileResponse {
  user_id: string;
  email: string;
  full_name: string;
  company_name: string;
}

export interface AuthLoginRequest {
  email: string;
  password: string;
  remember_me?: boolean;
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
  primary_contact_name?: string;
  primary_contact_email?: string;
  company_size?: string;
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

export interface CommandBriefing {
  critical_count: number;
  watch_count: number;
  resolved_count: number;
  nominal_nodes: number;
  total_nodes: number;
  status_breakdown?: Record<string, number>;
  critical_incidents?: Array<Record<string, unknown>>;
  watch_incidents?: Array<Record<string, unknown>>;
  recent_resolved?: Array<Record<string, unknown>>;
  network_health?: Record<string, unknown>;
}

export interface IntelligenceMonteCarloRequest {
  signal: Record<string, unknown>;
  runs?: number;
}

export interface IntelligenceMonteCarloResponse {
  status: string;
  existing?: boolean;
  incident?: Record<string, unknown>;
  simulation?: Record<string, unknown>;
  data_quality?: Record<string, unknown>;
  reason?: string;
}

export interface IntelligenceSimulationIncident {
  id: string;
  event_title?: string;
  severity?: string;
  status?: string;
  affected_node_count?: number;
  total_exposure_usd?: number;
  gnn_confidence?: number;
  simulation_only?: boolean;
  created_at?: string;
  monte_carlo?: Record<string, unknown>;
}

export interface IntelligenceGapItem {
  id: string;
  category: "freshness" | "completeness" | "coverage" | "drift" | string;
  severity: "critical" | "high" | "medium" | "low" | string;
  blocking: boolean;
  status: "open" | "resolved" | string;
  evidence: Record<string, unknown>;
  recommended_fix: string;
}

export interface IntelligenceGapResponse {
  user_id: string;
  generated_at: string;
  overall_status: "healthy" | "degraded" | "critical" | string;
  blocking: boolean;
  gap_count: number;
  gaps: IntelligenceGapItem[];
  summary: Record<string, unknown>;
}

/* ─── Endpoints ─────────────────────────────────────────────── */

export const api = {
  auth: {
    register: (payload: AuthRegisterRequest) =>
      request<AuthRegisterResponse>("/auth/register", { method: "POST", body: JSON.stringify(payload) }),
    login: (payload: AuthLoginRequest) =>
      request<AuthLoginResponse>("/auth/login", { method: "POST", body: JSON.stringify(payload) }),
    profile: (userId: string) =>
      request<AuthProfileResponse>(`/api/auth/profile/${encodeURIComponent(userId)}`),
  },
  onboarding: {
    complete: (payload: OnboardingCompleteRequest) =>
      request<{ status: string; user_id: string; updated_at?: string }>("/onboarding/complete", { method: "POST", body: JSON.stringify(payload) }),
    status: (userId: string) =>
      request<OnboardingStatusResponse>(`/api/onboarding/status/${encodeURIComponent(userId)}`),
  },
  contexts: {
    get: (userId: string) =>
      request<{ user_id: string; updated_at?: string; context: Record<string, unknown> }>(
        `/api/contexts/${encodeURIComponent(userId)}`,
      ),
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
    categorized: () => request<CategorizedSignals>("/signals/categorized"),
    sentiment: () => request<SentimentSignal[]>("/signals/sentiment"),
    refresh: () => request<{ status: string; message: string }>("/signals/refresh", { method: "POST" }),
  },
  audit: {
    list: () => request<AuditEntry[]>("/audit"),
    exportPdf: (id: string) => `${BASE}/audit/${id}/pdf`,
    exportAll: () => `${BASE}/audit/export`,
  },
  workflow: {
    analyze: (payload: {
      event: Record<string, unknown>;
      suppliers: Record<string, unknown>[];
      assessment?: Record<string, unknown>;
      workflow_id?: string | null;
    }) =>
      request<WorkflowAnalysisResponse>("/workflow/analyze", { method: "POST", body: JSON.stringify(payload) }),
    upsertReportStage: (payload: WorkflowReportUpsertRequest) =>
      request<{ status: string; workflow_id: string; stage: string }>("/workflow/report", { method: "POST", body: JSON.stringify(payload) }),
    reportPdfUrl: (workflowId: string) => `${BASE}/workflow/report/${workflowId}/pdf`,
    reasoning: (workflowId: string) =>
      request<{ workflow_id: string; steps: ReasoningStep[] }>(
        `/workflow/reasoning/${encodeURIComponent(workflowId)}`,
      ),
    reasoningRender: (workflowId: string) =>
      request<{ workflow_id: string; steps: (ReasoningStep & { narrative?: string })[] }>(
        `/workflow/reasoning/${encodeURIComponent(workflowId)}/render`,
      ),
    state: (workflowId: string) =>
      request<WorkflowStateResponse>(`/workflow/state/${encodeURIComponent(workflowId)}`),
    start: (payload: {
      workflow_id: string;
      user_id: string;
      selected_signal?: Record<string, unknown>;
      local_currency?: string;
      affected_suppliers?: Record<string, unknown>[];
    }) => request<WorkflowStartResponse>("/workflow/start", { method: "POST", body: JSON.stringify(payload) }),
    approve: (workflowId: string, payload: { action: "reroute" | "backup_supplier" | "both"; mode?: "sea" | "air" | "land" | null }) =>
      request<WorkflowStartResponse>(`/workflow/${encodeURIComponent(workflowId)}/approve`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
  },
  agents: {
    chat: (payload: {
      message: string;
      workflow_id?: string | null;
      session_id?: string | null;
      context?: Record<string, unknown>;
    }) => request<AgentChatResponse>("/agents/chat", { method: "POST", body: JSON.stringify(payload) }),
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
  incidents: {
    summary: () => request<{ critical_count: number; watch_count: number; resolved_count: number; nominal_nodes: number; total_nodes: number }>("/incidents/summary"),
    briefing: () => request<CommandBriefing>("/command/briefing"),
    generate: () => request<Record<string, unknown>>("/incidents/generate", { method: "POST" }),
  },
  intelligence: {
    gaps: () => request<IntelligenceGapResponse>("/intelligence/gaps"),
    monteCarlo: (payload: IntelligenceMonteCarloRequest) =>
      request<IntelligenceMonteCarloResponse>("/intelligence/monte-carlo", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    simulationIncidents: (status?: string) =>
      request<IntelligenceSimulationIncident[]>(
        `/intelligence/monte-carlo/incidents${status ? `?status=${encodeURIComponent(status)}` : ""}`,
      ),
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
  workflowNetwork: {
    save: (payload: {
      user_id: string;
      nodes: Record<string, unknown>[];
      routes: Record<string, unknown>[];
      description?: string;
    }) =>
      request<{ status: string; node_count: number; route_count: number; saved_at: string }>(
        "/workflow/network",
        { method: "POST", body: JSON.stringify(payload) },
      ),
    get: (userId: string) =>
      request<{ user_id: string; network: Record<string, unknown>; has_network: boolean }>(
        `/workflow/network/${encodeURIComponent(userId)}`,
      ),
    monitor: (payload: {
      user_id: string;
      nodes: Record<string, unknown>[];
      events?: Record<string, unknown>[];
    }) =>
      request<{
        filtered_events: Array<Record<string, unknown>>;
        total_scanned: number;
        intersection_count: number;
        node_count: number;
      }>("/workflow/network/monitor", { method: "POST", body: JSON.stringify(payload) }),
  },
  // ── WorldMonitor global intelligence data layer ──────────────────────────
  global: {
    hazards: () => request<{ data: GlobalHazard[]; source: string }>("/global/hazards"),
    earthquakes: () => request<{ data: Earthquake[]; source: string }>("/global/earthquakes"),
    conflict: () => request<{ data: ConflictEvent[]; source: string }>("/global/conflict"),
    gdelt: () => request<{ data: GdeltEvent[]; source: string }>("/global/gdelt"),
    disasters: () => request<{ data: GdacsAlert[]; source: string }>("/global/disasters"),
    supplyChainNews: () => request<{ data: NewsArticle[]; source: string }>("/global/news/supply-chain"),
    marketQuotes: () => request<{ data: MarketQuote[]; source: string }>("/global/market/quotes"),
    energy: () => request<{ data: Record<string, unknown>; source: string }>("/global/energy"),
    macro: () => request<{ data: Record<string, MacroSeries>; source: string }>("/global/macro"),
    chokepoints: () => request<{ data: ScoredChokepoint[] }>("/global/chokepoints"),
    shippingStress: () => request<ShippingStress>("/global/shipping/stress"),
    shippingIndices: () => request<{ data: ShippingIndex[] }>("/global/shipping/indices"),
    countryInstability: () => request<{ data: CountryInstability[] }>("/global/country-instability"),
    strategicRisk: () => request<StrategicRisk>("/global/strategic-risk"),
    marketImplications: () => request<MarketImplications>("/global/market-implications"),
    fires: () => request<{ data: FireDetection[]; source: string }>("/global/fires"),
    aviation: () => request<{ data: FlightRecord[]; source: string }>("/global/aviation"),
    airQuality: () => request<{ data: AirQualityRecord[]; source: string }>("/global/air-quality"),
    minerals: () => request<{ data: CriticalMineral[] }>("/global/minerals"),
    summary: () => request<GlobalSummary>("/global/summary"),
    refresh: () => request<{ status: string; message: string }>("/global/refresh", { method: "POST" }),
  },
};

// ── WorldMonitor types ────────────────────────────────────────────────────────

export interface GlobalHazard {
  id: string; title: string; category: string; source: string;
  lng: number | null; lat: number | null; time: string | null; severity: string;
}

export interface Earthquake {
  id: string; title: string; lng: number | null; lat: number | null;
  magnitude: number; depth_km: number | null; place: string; time: number;
  url: string; severity: string; source: string;
}

export interface ConflictEvent {
  id: string; date: string; type: string; country: string; region: string;
  lat: number; lng: number; fatalities: number; notes: string; source: string;
}

export interface GdeltEvent {
  title: string; url: string; source: string; seendate: string;
  country: string; lang: string; event_type: string;
}

export interface GdacsAlert {
  id: string; title: string; type: string; severity: string;
  country: string; lat: number | null; lng: number | null; url: string; source: string;
}

export interface NewsArticle {
  id: string; title: string; description: string; url: string;
  source: string; publishedAt: string; category: string;
}

export interface MarketQuote {
  symbol: string; price: number; change: number; change_pct: number;
  high: number; low: number; open: number; prev_close: number; time: string;
}

export interface MacroSeries {
  value: string; date: string;
}

export interface ScoredChokepoint {
  id: string; name: string; lng: number; lat: number;
  traffic_pct: number; category: string; risk_score: number;
  trend: string; eonet_nearby?: number; acled_nearby?: number;
  last_scored?: string;
}

export interface ShippingStress {
  stress_score: number; stress_level: string;
  carriers: { name: string; risk: string }[];
  high_risk_chokepoints: string[];
  fetched_at: string;
}

export interface ShippingIndex {
  id: string; name: string; unit: string;
}

export interface CountryInstability {
  country: string; instability_score: number;
  conflict: number; natural: number; fatalities: number;
}

export interface StrategicRisk {
  score: number; level: string; trend: string;
  components: { chokepoint_risk: number; country_instability: number; active_events: number };
  computed_at: string;
}

export interface MarketImplications {
  summary: string[]; generated_at: string; model: string;
}

export interface FireDetection {
  lat: number; lng: number; brightness: number;
  acq_date: string; confidence: string; source: string;
}

export interface FlightRecord {
  flight_iata: string; airline: string; departure: string;
  arrival: string; status: string; departure_time: string;
}

export interface AirQualityRecord {
  city: string; location: string; lat: number; lng: number; country: string;
}

export interface CriticalMineral {
  id: string; name: string; primary_producer: string; share_pct: number;
}

export interface GlobalSummary {
  strategic_risk: StrategicRisk;
  shipping_stress: ShippingStress;
  chokepoints: ScoredChokepoint[];
  top_instability: CountryInstability[];
  market_implications: MarketImplications;
  active_hazards: number;
  active_fires: number;
  conflict_events: number;
  minerals: CriticalMineral[];
}

