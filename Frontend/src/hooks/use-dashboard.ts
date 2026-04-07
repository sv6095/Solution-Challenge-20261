import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { RFQ } from "@/lib/api";

/* ─── Dashboard Home ────────────────────────────────────────── */
export const useDashboardKpis = () =>
  useQuery({ queryKey: ["dashboard", "kpis"], queryFn: api.dashboard.kpis });

export const useDashboardEvents = () =>
  useQuery({ queryKey: ["dashboard", "events"], queryFn: api.dashboard.events });

export const useDashboardWorkflows = () =>
  useQuery({ queryKey: ["dashboard", "workflows"], queryFn: api.dashboard.workflows });

export const useDashboardSuppliers = () =>
  useQuery({ queryKey: ["dashboard", "suppliers"], queryFn: api.dashboard.suppliers });

/* ─── Risk Map ───────────────────────────────────────────────── */
export const useRiskEvents = (params?: { region?: string; severity?: string }) =>
  useQuery({
    queryKey: ["risks", "events", params],
    queryFn: () => api.risks.events(params),
  });

export const useRiskSuppliers = (params?: { tier?: string; minScore?: number; maxScore?: number }) =>
  useQuery({
    queryKey: ["risks", "suppliers", params],
    queryFn: () => api.risks.suppliers(params),
  });

/* ─── Route Intelligence ─────────────────────────────────────── */
export const useRoutes = (origin?: string, destination?: string, mode?: string) =>
  useQuery({
    queryKey: ["routes", origin, destination, mode],
    queryFn: () => api.routes.list(origin, destination, mode),
    enabled: !!(origin && destination),
  });

/* ─── Signal Monitor ─────────────────────────────────────────── */
export const useHazards = () =>
  useQuery({ queryKey: ["signals", "hazards"], queryFn: api.signals.hazards, refetchInterval: 60_000 });

export const useNewsSignals = () =>
  useQuery({ queryKey: ["signals", "news"], queryFn: api.signals.news, refetchInterval: 60_000 });

export const useDataSources = () =>
  useQuery({ queryKey: ["signals", "sources"], queryFn: api.signals.sources, refetchInterval: 30_000 });

/* ─── Audit Log ──────────────────────────────────────────────── */
export const useAuditLog = () =>
  useQuery({ queryKey: ["audit"], queryFn: api.audit.list });

/* ─── RFQ Manager ────────────────────────────────────────────── */
export const useRFQs = (status?: string) =>
  useQuery({ queryKey: ["rfq", status], queryFn: () => api.rfq.list(status) });

export const useCreateRFQ = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<RFQ>) => api.rfq.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rfq"] }),
  });
};

/* ─── Exposure Scores ────────────────────────────────────────── */
export const useExposureSummary = () =>
  useQuery({ queryKey: ["exposure", "summary"], queryFn: api.exposure.summary });

export const useExposureSuppliers = () =>
  useQuery({ queryKey: ["exposure", "suppliers"], queryFn: api.exposure.suppliers });

/* ─── Settings ───────────────────────────────────────────────── */
export const useProfile = () =>
  useQuery({ queryKey: ["settings", "profile"], queryFn: api.settings.profile });

export const useUpdateProfile = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.settings.updateProfile,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["settings", "profile"] }),
  });
};

export const useBilling = () =>
  useQuery({ queryKey: ["settings", "billing"], queryFn: api.settings.billing });
