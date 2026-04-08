import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { RFQ } from "@/lib/api";

const FIFTEEN_MINUTES_MS = 15 * 60 * 1000;

/* ─── Dashboard Home ────────────────────────────────────────── */
export const useDashboardKpis = () =>
  useQuery({ queryKey: ["dashboard", "kpis"], queryFn: api.dashboard.kpis, refetchInterval: FIFTEEN_MINUTES_MS });

export const useDashboardEvents = () =>
  useQuery({ queryKey: ["dashboard", "events"], queryFn: api.dashboard.events, refetchInterval: FIFTEEN_MINUTES_MS });

export const useDashboardWorkflows = () =>
  useQuery({ queryKey: ["dashboard", "workflows"], queryFn: api.dashboard.workflows, refetchInterval: FIFTEEN_MINUTES_MS });

export const useDashboardSuppliers = () =>
  useQuery({ queryKey: ["dashboard", "suppliers"], queryFn: api.dashboard.suppliers, refetchInterval: FIFTEEN_MINUTES_MS });

/* ─── Risk Map ───────────────────────────────────────────────── */
export const useRiskEvents = (params?: { region?: string; severity?: string }) =>
  useQuery({
    queryKey: ["risks", "events", params],
    queryFn: () => api.risks.events(params),
    refetchInterval: FIFTEEN_MINUTES_MS,
  });

export const useRiskSuppliers = (params?: { tier?: string; minScore?: number; maxScore?: number }) =>
  useQuery({
    queryKey: ["risks", "suppliers", params],
    queryFn: () => api.risks.suppliers(params),
    refetchInterval: FIFTEEN_MINUTES_MS,
  });

/* ─── Route Intelligence ─────────────────────────────────────── */
export const useRoutes = (origin?: string, destination?: string, mode?: string) =>
  useQuery({
    queryKey: ["routes", origin, destination, mode],
    queryFn: () => api.routes.list(origin, destination, mode),
    enabled: !!(origin && destination),
    refetchInterval: FIFTEEN_MINUTES_MS,
  });

/* ─── Signal Monitor ─────────────────────────────────────────── */
export const useHazards = () =>
  useQuery({ queryKey: ["signals", "hazards"], queryFn: api.signals.hazards, refetchInterval: FIFTEEN_MINUTES_MS });

export const useNewsSignals = () =>
  useQuery({ queryKey: ["signals", "news"], queryFn: api.signals.news, refetchInterval: FIFTEEN_MINUTES_MS });

export const useDataSources = () =>
  useQuery({ queryKey: ["signals", "sources"], queryFn: api.signals.sources, refetchInterval: FIFTEEN_MINUTES_MS });

/* ─── Audit Log ──────────────────────────────────────────────── */
export const useAuditLog = () =>
  useQuery({ queryKey: ["audit"], queryFn: api.audit.list, refetchInterval: FIFTEEN_MINUTES_MS });

/* ─── RFQ Manager ────────────────────────────────────────────── */
export const useRFQs = (status?: string) =>
  useQuery({ queryKey: ["rfq", status], queryFn: () => api.rfq.list(status), refetchInterval: FIFTEEN_MINUTES_MS });

export const useCreateRFQ = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<RFQ>) => api.rfq.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rfq"] }),
  });
};

/* ─── Exposure Scores ────────────────────────────────────────── */
export const useExposureSummary = () =>
  useQuery({ queryKey: ["exposure", "summary"], queryFn: api.exposure.summary, refetchInterval: FIFTEEN_MINUTES_MS });

export const useExposureSuppliers = () =>
  useQuery({ queryKey: ["exposure", "suppliers"], queryFn: api.exposure.suppliers, refetchInterval: FIFTEEN_MINUTES_MS });

/* ─── Settings ───────────────────────────────────────────────── */
export const useProfile = () =>
  useQuery({ queryKey: ["settings", "profile"], queryFn: api.settings.profile, refetchInterval: FIFTEEN_MINUTES_MS });

export const useUpdateProfile = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.settings.updateProfile,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["settings", "profile"] }),
  });
};

export const useBilling = () =>
  useQuery({ queryKey: ["settings", "billing"], queryFn: api.settings.billing, refetchInterval: FIFTEEN_MINUTES_MS });

export const useNetworkGraph = () =>
  useQuery({ queryKey: ["network", "graph"], queryFn: api.network.graph, refetchInterval: FIFTEEN_MINUTES_MS });
