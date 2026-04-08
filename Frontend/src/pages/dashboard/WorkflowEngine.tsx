import { useMemo, useRef, useState, useEffect } from "react";
import { CheckCircle, Circle, Zap, FileText, Loader2 } from "lucide-react";
import { useDashboardEvents, useRiskSuppliers } from "@/hooks/use-dashboard";
import { useWorkflowEvent } from "@/hooks/use-workflow-event";
import { api } from "@/lib/api";
import { useSearchParams } from "react-router-dom";

const STAGES = ["DETECT", "ASSESS", "DECIDE", "ACT", "AUDIT"];

type ContextNode = {
  name?: string;
  node_type?: string;
  address?: string;
  tier?: string;
  lat?: number;
  lng?: number;
  transport_modes?: { sea?: boolean; air?: boolean; land?: boolean };
  safety_stock_days?: number | string;
  daily_throughput_usd?: number | string;
};

type ContextSupplier = {
  name?: string;
  email?: string;
  country?: string;
  tier?: string;
  category?: string;
  origin_nodes?: string;
  incoterm?: string;
  backup_supplier?: boolean;
};

function renderBrief(text: string) {
  const normalize = (line: string) =>
    (line || "")
      // render markdown bold as plain text
      .replace(/\*\*(.*?)\*\*/g, "$1")
      // clean any stray bold markers
      .replace(/\*\*/g, "")
      .trimEnd();

  const blocks = (text || "").split("\n").map(normalize);
  return (
    <div className="space-y-3">
      {blocks.map((line, idx) => {
        if (!line.trim()) return <div key={idx} className="h-1" />;
        if (line.startsWith("###")) {
          return (
            <h3 key={idx} className="font-headline font-bold text-base text-foreground mt-4">
              {line.replace(/^###\s*/, "")}
            </h3>
          );
        }
        if (line.startsWith("- ")) {
          return (
            <div key={idx} className="flex gap-2 text-body-md text-secondary leading-relaxed">
              <span className="text-sentinel mt-[2px]">•</span>
              <span>{line.replace(/^-+\s*/, "")}</span>
            </div>
          );
        }
        return (
          <p key={idx} className="text-body-md text-secondary leading-relaxed">
            {line}
          </p>
        );
      })}
    </div>
  );
}

function haversineKm(a: { lat: number; lng: number }, b: { lat: number; lng: number }) {
  const R = 6371;
  const dLat = ((b.lat - a.lat) * Math.PI) / 180;
  const dLng = ((b.lng - a.lng) * Math.PI) / 180;
  const lat1 = (a.lat * Math.PI) / 180;
  const lat2 = (b.lat * Math.PI) / 180;
  const x =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.sin(dLng / 2) * Math.sin(dLng / 2) * Math.cos(lat1) * Math.cos(lat2);
  const c = 2 * Math.atan2(Math.sqrt(x), Math.sqrt(1 - x));
  return R * c;
}

function impactRadiusKm(event: any) {
  const type = String(event?.type || event?.event_type || event?.title || "").toLowerCase();
  if (type.includes("wildfire") || type.includes("fire")) return 50;
  if (type.includes("cyclone") || type.includes("storm") || type.includes("typhoon") || type.includes("hurricane")) return 300;
  if (type.includes("earthquake")) return 200;
  if (type.includes("port strike") || type.includes("strike")) return 25;
  return 120;
}

const WorkflowEngine = () => {
  const workflowId = "demo-workflow-001";
  const [searchParams] = useSearchParams();
  const [currentStage, setCurrentStage] = useState(1);
  const [analysis, setAnalysis] = useState<string>("");
  const [analysisProvider, setAnalysisProvider] = useState<string>("");
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [reportSyncing, setReportSyncing] = useState(false);
  const [stageDecision, setStageDecision] = useState<"reroute" | "backup_supplier">("reroute");
  const [contextNodes, setContextNodes] = useState<ContextNode[]>([]);
  const [contextSuppliers, setContextSuppliers] = useState<ContextSupplier[]>([]);
  const [atRiskNodes, setAtRiskNodes] = useState<Array<ContextNode & { distance_km: number }>>([]);
  const [selectedSupplierName, setSelectedSupplierName] = useState<string>("");
  const [selectedOriginNodeName, setSelectedOriginNodeName] = useState<string>("");
  const [destinationQuery, setDestinationQuery] = useState<string>("");
  const [destinationPoint, setDestinationPoint] = useState<{ lat: number; lng: number } | null>(null);
  const [cargo, setCargo] = useState({ weight_tonnes: "2", volume_cbm: "8", hazmat: false, temperature: false });
  const [routeComparison, setRouteComparison] = useState<Array<Record<string, any>>>([]);
  const [recommendedMode, setRecommendedMode] = useState<"sea" | "air" | "land" | "">("");
  const [currencyRiskIndex, setCurrencyRiskIndex] = useState<number | null>(null);
  const [selectedMode, setSelectedMode] = useState<"sea" | "air" | "land" | "">("");
  const [decideLoading, setDecideLoading] = useState(false);
  const [actDone, setActDone] = useState(false);
  const [rfqDraft, setRfqDraft] = useState<{ recipient: string; subject: string; body: string } | null>(null);
  const [rfqSending, setRfqSending] = useState(false);
  const { data: events, isLoading: eLoading } = useDashboardEvents();
  const { data: suppliers, isLoading: sLoading } = useRiskSuppliers();
  const workflowEvent = useWorkflowEvent(workflowId);
  const stageTimesRef = useRef<{ detect?: string; assess?: string; decide?: string; act?: string; audit?: string }>({});

  useEffect(() => {
    if (!workflowEvent?.stage) return;
    const stageIndex = STAGES.findIndex((s) => s.toLowerCase() === workflowEvent.stage?.toLowerCase());
    if (stageIndex >= 0) {
      setCurrentStage(stageIndex);
    }
  }, [workflowEvent?.stage]);

  // Advance to DETECT when we have a critical event
  const preloaded = useMemo(() => {
    const raw = sessionStorage.getItem("preloaded_workflow_event");
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch {
      return null;
    }
  }, [searchParams.get("entry")]);

  const activeEvent = (preloaded as any) ?? (events?.find((e) => e.severity === "CRITICAL") ?? events?.[0]);
  const affectedSuppliers = suppliers?.filter((s) => s.exposureScore > 60).slice(0, 3);

  const stageLabel = STAGES[currentStage] ?? "ASSESS";
  const stageKey = useMemo(() => stageLabel.toLowerCase() as "detect" | "assess" | "decide" | "act" | "audit", [stageLabel]);

  useEffect(() => {
    const userId = localStorage.getItem("user_id") || "local-user";
    api.contexts
      .get(userId)
      .then((res) => {
        const nodes = (res.context?.logistics_nodes as any[]) || [];
        const supp = (res.context?.suppliers as any[]) || [];
        setContextNodes(nodes);
        setContextSuppliers(supp);
      })
      .catch(() => {
        setContextNodes([]);
        setContextSuppliers([]);
      });
  }, []);

  useEffect(() => {
    if (!activeEvent || typeof activeEvent.lat !== "number" || typeof activeEvent.lng !== "number") {
      setAtRiskNodes([]);
      return;
    }
    const evt = { lat: Number(activeEvent.lat), lng: Number(activeEvent.lng) };
    const radius = impactRadiusKm(activeEvent);
    const list = (contextNodes || [])
      .filter((n) => typeof n.lat === "number" && typeof n.lng === "number")
      .map((n) => ({ ...n, distance_km: haversineKm(evt, { lat: Number(n.lat), lng: Number(n.lng) }) }))
      .filter((n) => n.distance_km <= radius)
      .sort((a, b) => a.distance_km - b.distance_km)
      .slice(0, 8);
    setAtRiskNodes(list);
  }, [activeEvent?.lat, activeEvent?.lng, contextNodes]);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      if (!activeEvent) return;
      setAnalysisLoading(true);
      try {
        const res = await api.workflow.analyze({
          event: activeEvent as unknown as Record<string, unknown>,
          suppliers: (affectedSuppliers ?? []) as unknown as Record<string, unknown>[],
        });
        if (cancelled) return;
        setAnalysis(res.analysis);
        setAnalysisProvider(res.provider);
      } catch {
        if (cancelled) return;
        setAnalysis("");
        setAnalysisProvider("");
      } finally {
        if (!cancelled) setAnalysisLoading(false);
      }
    };
    run();
    return () => {
      cancelled = true;
    };
  }, [activeEvent?.id, affectedSuppliers?.map((s) => s.id).join(",")]);

  const geocodePlace = async (query: string) => {
    const q = (query || "").trim();
    if (!q) return null;
    try {
      const response = await fetch(
        `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(q)}&format=json&limit=1`,
      );
      const data = (await response.json()) as Array<{ lat: string; lon: string }>;
      if (!data?.length) return null;
      return { lat: Number(data[0].lat), lng: Number(data[0].lon) };
    } catch {
      return null;
    }
  };

  const selectedSupplier = useMemo(
    () => contextSuppliers.find((s) => (s.name || "") === selectedSupplierName) ?? null,
    [contextSuppliers, selectedSupplierName],
  );
  const originCandidates = useMemo(() => {
    const all = contextNodes.filter((n) => n.name && typeof n.lat === "number" && typeof n.lng === "number");
    const hint = String(selectedSupplier?.origin_nodes || "").trim();
    if (!hint) return all;
    const hints = hint.split(",").map((s) => s.trim()).filter(Boolean);
    if (!hints.length) return all;
    const matched = all.filter((n) => hints.some((h) => String(n.name || "").toLowerCase().includes(h.toLowerCase())));
    return matched.length ? matched : all;
  }, [contextNodes, selectedSupplier?.origin_nodes]);

  useEffect(() => {
    // Set sensible defaults when entering decide stage / when context loads.
    if (!selectedSupplierName && contextSuppliers.length) {
      setSelectedSupplierName(String(contextSuppliers[0]?.name || ""));
    }
  }, [contextSuppliers, selectedSupplierName]);

  useEffect(() => {
    if (!selectedOriginNodeName && originCandidates.length) {
      setSelectedOriginNodeName(String(originCandidates[0]?.name || ""));
    }
  }, [originCandidates, selectedOriginNodeName]);

  const selectedOriginNode = useMemo(
    () => originCandidates.find((n) => (n.name || "") === selectedOriginNodeName) ?? null,
    [originCandidates, selectedOriginNodeName],
  );

  const computeRoutes = async () => {
    if (!selectedOriginNode || typeof selectedOriginNode.lat !== "number" || typeof selectedOriginNode.lng !== "number") return;
    setDecideLoading(true);
    try {
      let dest = destinationPoint;
      if (!dest) {
        dest = await geocodePlace(destinationQuery);
        if (dest) setDestinationPoint(dest);
      }
      if (!dest) return;
      const res = await api.routes.workflow({
        origin: { lat: Number(selectedOriginNode.lat), lng: Number(selectedOriginNode.lng), country_code: "US" },
        destination: { lat: Number(dest.lat), lng: Number(dest.lng), country_code: "US" },
        target_currency: "USD",
      });
      setRouteComparison((res.route_comparison || []) as any);
      setRecommendedMode(res.recommended_mode);
      setCurrencyRiskIndex(res.currency_risk_index);
      setSelectedMode(res.recommended_mode);
      stageTimesRef.current.decide = new Date().toISOString();
      await api.workflow.upsertReportStage({
        workflow_id: workflowId,
        stage: "decide",
        payload: {
          decided_at: stageTimesRef.current.decide,
          supplier: selectedSupplier,
          origin_node: selectedOriginNode,
          destination_query: destinationQuery,
          destination_point: dest,
          cargo,
          decision_gate: stageDecision,
          recommended_mode: res.recommended_mode,
          currency_risk_index: res.currency_risk_index,
          route_comparison: res.route_comparison,
          selected_mode: res.recommended_mode,
        },
      });
    } finally {
      setDecideLoading(false);
    }
  };

  const confirmAct = async () => {
    const now = new Date().toISOString();
    stageTimesRef.current.act = now;
    setRfqDraft(null);
    setActDone(false);

    if (stageDecision === "reroute") {
      await api.workflow.upsertReportStage({
        workflow_id: workflowId,
        stage: "act",
        payload: {
          decision: "reroute",
          executed_at: now,
          selected_mode: selectedMode || recommendedMode || null,
          origin_node: selectedOriginNode,
          destination_query: destinationQuery,
          destination_point: destinationPoint,
          constraints: cargo,
          details: `Reroute approved. Mode=${selectedMode || recommendedMode || "—"}.`,
        },
      });
      setActDone(true);
      return;
    }

    // backup supplier path: draft RFQ from context
    const backup = (contextSuppliers || []).find((s) => Boolean(s.backup_supplier) && s.email) || selectedSupplier;
    const recipient = String(backup?.email || "").trim() || "backup@example.com";
    const subject = `Emergency RFQ — ${String(activeEvent?.title || "Disruption")} — ${selectedOriginNodeName || "Origin"}`;
    const body = [
      `Hello,`,
      ``,
      `We are activating contingency sourcing due to: ${String(activeEvent?.title || "a disruption signal")}.`,
      `Origin: ${selectedOriginNodeName || "—"}`,
      `Destination: ${destinationQuery || "—"}`,
      `Incoterm: ${String(backup?.incoterm || "FOB")}`,
      ``,
      `Requested: ${String(backup?.category || "materials")} (${String(backup?.name || "supplier")})`,
      `Cargo constraints: weight ${cargo.weight_tonnes}t, volume ${cargo.volume_cbm}cbm, hazmat=${cargo.hazmat ? "Y" : "N"}, temp=${cargo.temperature ? "Y" : "N"}`,
      ``,
      `Please respond within 48 hours with price, lead time, and capacity confirmation.`,
      ``,
      `Thanks,`,
      `${localStorage.getItem("user_id") || "operator"}`,
    ].join("\n");

    setRfqDraft({ recipient, subject, body });
    await api.workflow.upsertReportStage({
      workflow_id: workflowId,
      stage: "act",
      payload: {
        decision: "backup_supplier",
        executed_at: now,
        rfq: { recipient, subject, body, status: "drafted" },
        details: "RFQ drafted and awaiting send approval.",
      },
    });
  };

  const sendRfq = async () => {
    if (!rfqDraft) return;
    setRfqSending(true);
    try {
      const created = await api.rfq.create({
        supplier: rfqDraft.recipient,
        eventTrigger: rfqDraft.subject,
        body: rfqDraft.body,
        status: "Sent",
        workflowId,
      } as any);
      await api.workflow.upsertReportStage({
        workflow_id: workflowId,
        stage: "act",
        payload: {
          decision: "backup_supplier",
          executed_at: stageTimesRef.current.act || new Date().toISOString(),
          rfq: { id: created.id, recipient: rfqDraft.recipient, subject: rfqDraft.subject, body: rfqDraft.body, status: "sent" },
          details: `RFQ sent to ${rfqDraft.recipient}.`,
        },
      });
      setActDone(true);
    } finally {
      setRfqSending(false);
    }
  };

  const completeAudit = async () => {
    const now = new Date().toISOString();
    stageTimesRef.current.audit = now;
    // compute response time from detect->act (fallback: detect->now)
    const report = await api.workflows.reportJson(workflowId).catch(() => null);
    const detectedAt = (report as any)?.detect?.detected_at || stageTimesRef.current.detect;
    const executedAt = (report as any)?.act?.executed_at || stageTimesRef.current.act;
    const startMs = detectedAt ? new Date(detectedAt).getTime() : Date.now();
    const endMs = executedAt ? new Date(executedAt).getTime() : Date.now();
    const responseSeconds = Math.max(0, Math.round((endMs - startMs) / 1000));
    const timeline = [
      `DETECT @ ${detectedAt || "—"}`,
      `ASSESS @ ${stageTimesRef.current.assess || "—"}`,
      `DECIDE @ ${stageTimesRef.current.decide || "—"}`,
      `ACT @ ${executedAt || "—"}`,
      `AUDIT @ ${now}`,
    ].join(" · ");
    await api.workflow.upsertReportStage({
      workflow_id: workflowId,
      stage: "audit",
      payload: {
        status: "complete",
        completed_at: now,
        timeline,
        response_time_seconds: responseSeconds,
      },
    });
  };

  // Persist stage payload to backend so PDF becomes detailed.
  useEffect(() => {
    let cancelled = false;
    const sync = async () => {
      if (!activeEvent) return;
      setReportSyncing(true);
      try {
        const now = new Date().toISOString();
        if (!stageTimesRef.current.detect && stageKey === "detect") stageTimesRef.current.detect = now;
        if (!stageTimesRef.current.assess && stageKey === "assess") stageTimesRef.current.assess = now;
        const incidentStream = (events ?? []).slice(0, 5).map((e) => ({
          id: e.id,
          title: e.title,
          severity: e.severity,
          region: e.region,
          timestamp: e.timestamp,
        }));

        if (stageKey === "detect") {
          await api.workflow.upsertReportStage({
            workflow_id: workflowId,
            stage: "detect",
            payload: {
              event: activeEvent,
              incident_stream: incidentStream,
              detected_at: stageTimesRef.current.detect,
              affected_suppliers: affectedSuppliers ?? [],
              at_risk_nodes: atRiskNodes.map((n) => ({
                name: n.name,
                node_type: n.node_type,
                distance_km: Number(n.distance_km.toFixed(1)),
                transport_modes: n.transport_modes,
              })),
              impact_radius_km: impactRadiusKm(activeEvent),
            },
          });
        }

        if (stageKey === "assess") {
          // Demo assessment numbers (backend also has ML, but this keeps UI deterministic)
          const exposureUsd = Math.round((affectedSuppliers?.reduce((a, s) => a + s.exposureScore, 0) ?? 0) * 2500);
          const daysAtRisk = Math.max(2, Math.round((activeEvent.severity === "CRITICAL" ? 8 : activeEvent.severity === "HIGH" ? 5 : 3)));
          const seaAffected = atRiskNodes.some((n) => n.transport_modes?.sea || String(n.node_type || "").toLowerCase().includes("port"));
          const airAffected = atRiskNodes.some((n) => n.transport_modes?.air || String(n.node_type || "").toLowerCase().includes("airport"));
          const landAffected = atRiskNodes.some((n) => n.transport_modes?.land || true);
          await api.workflow.upsertReportStage({
            workflow_id: workflowId,
            stage: "assess",
            payload: {
              analysis_provider: analysisProvider || "local",
              analysis: analysis || activeEvent.description,
              confidence: workflowEvent?.confidence ?? 0.78,
              days_at_risk: daysAtRisk,
              exposure_usd: exposureUsd,
              affected_nodes: atRiskNodes.length,
              transport_mode_impact: { sea: seaAffected, air: airAffected, land: landAffected },
              sea_layer: seaAffected
                ? { sea_state: "moderate", wave_height_m: 2.4, piracy_risk: "elevated", recommended_lane: "cape", lane_switch_days_added: 7, lane_switch_cost_usd: 279 }
                : null,
              air_layer: airAffected
                ? { sigmet_active: false, vaac_ash: false, closed_airspace: [], reroute_required: false, reroute_adds_hrs: 0.0, airport_congestion_origin: "moderate", airport_congestion_dest: "low" }
                : null,
              land_layer: landAffected
                ? { selected: "maps_route", reason: "emergency — minimize ETA", political_risk: "low", cargo_constraints: [] }
                : null,
              assessed_at: stageTimesRef.current.assess,
            },
          });
        }
      } finally {
        if (!cancelled) setReportSyncing(false);
      }
    };
    sync();
    return () => {
      cancelled = true;
    };
  }, [stageKey, workflowId, activeEvent?.id, analysis, analysisProvider, stageDecision, atRiskNodes]);

  return (
    <div>
      {/* Stage Progress */}
      <div className="flex items-center justify-between mb-10 max-w-3xl mx-auto">
        {STAGES.map((stage, i) => (
          <div key={stage} className="flex items-center gap-2">
            <button
              onClick={() => setCurrentStage(i)}
              className={`flex items-center justify-center w-10 h-10 rounded-full transition-all ${
                i < currentStage ? "bg-surface-highest text-foreground" :
                i === currentStage ? "bg-sentinel text-background sentinel-glow" :
                "bg-surface-high text-secondary"
              }`}
              title={stage}
              aria-label={stage}
            >
              {i < currentStage ? <CheckCircle size={18} /> : <Circle size={18} />}
            </button>
            <span className={`text-label-sm uppercase tracking-widest hidden md:block ${i === currentStage ? "text-sentinel font-bold" : "text-secondary"}`}>
              {stage}
            </span>
            {i < STAGES.length - 1 && <div className="w-12 lg:w-24 h-px bg-border mx-2" />}
          </div>
        ))}
      </div>

      <div className="grid lg:grid-cols-[1fr_1fr] gap-6">
        {/* Left: AI Analysis */}
        <div className="space-y-4">
          <div className="surface-container-high rounded-lg p-6 relative">
            <div className="absolute left-0 top-0 bottom-0 w-1 rounded-l bg-sentinel" />
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 bg-sentinel/20 rounded-lg flex items-center justify-center">
                <Zap size={20} className="text-sentinel" />
              </div>
              <div>
                <h2 className="font-headline text-xl font-bold">
                  {currentStage === 0 ? "Detecting signals…" :
                   currentStage === 1 ? "Gemini is analyzing…" :
                   currentStage === 2 ? "Deciding optimal response…" :
                   currentStage === 3 ? "Executing actions…" :
                   "Audit complete"}
                </h2>
                <p className="text-body-md text-secondary">
                  {currentStage <= 1 ? "Deep-scanning multi-tier nodes" :
                   currentStage === 2 ? "Evaluating risk mitigation options" :
                   currentStage === 3 ? "Dispatching workflows" :
                   "Review workflow execution record"}
                </p>
              </div>
            </div>
            <div className="h-px bg-border my-4" />
            {eLoading || analysisLoading ? (
              <div className="flex justify-center py-4"><Loader2 className="animate-spin text-secondary" /></div>
            ) : activeEvent ? (
              <div className="space-y-3">
                {!!analysisProvider && (
                  <div className="text-label-sm text-secondary uppercase tracking-widest">
                    Analysis engine: <span className="text-sentinel">{analysisProvider}</span>
                    {reportSyncing ? <span className="text-secondary"> · syncing report…</span> : null}
                  </div>
                )}
                {renderBrief(analysis || activeEvent.description)}
              </div>
            ) : (
              <p className="text-body-md text-secondary leading-relaxed">No critical events detected. All systems nominal.</p>
            )}
          </div>

          {stageKey === "detect" && atRiskNodes.length > 0 ? (
            <div className="surface-container-high rounded-lg p-6">
              <h3 className="font-headline font-bold text-lg mb-2">At-risk nodes (intersection)</h3>
              <p className="text-body-md text-secondary mb-4">
                Impact radius: <span className="text-foreground font-medium">{impactRadiusKm(activeEvent)} km</span>
              </p>
              <div className="space-y-3">
                {atRiskNodes.map((n, idx) => (
                  <div key={`${n.name}-${idx}`} className="flex items-center justify-between">
                    <div>
                      <p className="font-headline font-bold text-sm">{n.name || "Node"}</p>
                      <p className="text-label-sm text-secondary">{n.node_type || "node"} · {n.distance_km.toFixed(1)} km away</p>
                    </div>
                    <div className="flex gap-2 text-label-sm">
                      <span className={`px-2 py-1 rounded-sm ${n.transport_modes?.sea ? "bg-sentinel/10 text-sentinel" : "bg-surface-highest text-secondary"}`}>Sea</span>
                      <span className={`px-2 py-1 rounded-sm ${n.transport_modes?.air ? "bg-sentinel/10 text-sentinel" : "bg-surface-highest text-secondary"}`}>Air</span>
                      <span className={`px-2 py-1 rounded-sm ${n.transport_modes?.land ? "bg-sentinel/10 text-sentinel" : "bg-surface-highest text-secondary"}`}>Land</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {/* Live Incident Stream */}
          <div className="surface-container-high rounded-lg p-6">
            <span className="text-label-sm text-secondary uppercase tracking-widest">Live Incident Stream</span>
            {eLoading ? (
              <div className="mt-3 flex justify-center"><Loader2 className="animate-spin text-secondary" /></div>
            ) : events?.slice(0, 3).map((ev) => (
              <div key={ev.id} className="surface-container rounded-lg p-4 mt-3 relative">
                <div className={`absolute left-0 top-0 bottom-0 w-1 rounded-l ${ev.severity === "CRITICAL" || ev.severity === "HIGH" ? "bg-sentinel" : "bg-yellow-500"}`} />
                <div className="flex items-center gap-2 mb-1">
                  <span className={ev.severity === "CRITICAL" ? "text-sentinel" : "text-yellow-500"}>▲</span>
                  <h3 className="font-headline font-bold text-sm">{ev.title}</h3>
                </div>
                <p className="text-body-md text-secondary">{ev.description}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Right: Impact + Suppliers */}
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="surface-container-high rounded-lg p-6 relative">
              <div className="absolute left-0 top-0 bottom-0 w-1 rounded-l bg-sentinel" />
              <div className="flex items-center justify-between mb-2">
                <span className="text-sentinel">📊</span>
                <span className="glass-panel px-2 py-0.5 rounded-sm text-label-sm">Estimated</span>
              </div>
              <p className="text-label-sm text-secondary uppercase tracking-widest">Supplier Exposure</p>
              <p className="font-headline text-3xl font-bold mt-1">
                {sLoading ? "—" : `${affectedSuppliers?.length ?? 0} nodes`}
              </p>
              <p className="text-label-sm text-secondary mt-1">above 60% threshold</p>
            </div>

            <div className="surface-container-high rounded-lg p-6 relative">
              <div className="absolute left-0 top-0 bottom-0 w-1 rounded-l bg-sentinel" />
              <div className="flex items-center justify-between mb-2">
                <span className="text-sentinel">⚠</span>
                <span className="glass-panel px-2 py-0.5 rounded-sm text-label-sm text-sentinel">
                  {eLoading ? "…" : (events?.filter((e) => e.severity === "CRITICAL")?.length ?? 0) > 0 ? "Critical" : "Moderate"}
                </span>
              </div>
              <p className="text-label-sm text-secondary uppercase tracking-widest">Active Events</p>
              <p className="font-headline text-3xl font-bold mt-1">
                {eLoading ? "—" : events?.length ?? 0}
              </p>
              <p className="text-body-md text-secondary mt-2">Across {new Set(events?.map((e) => e.region)).size ?? 0} regions.</p>
            </div>
          </div>

          {/* Affected Suppliers */}
          <div className="surface-container-high rounded-lg p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-headline font-bold text-lg">High Exposure Nodes</h3>
              <span className="text-label-sm text-secondary uppercase tracking-widest">
                {sLoading ? "…" : `${affectedSuppliers?.length ?? 0} Nodes`}
              </span>
            </div>
            {sLoading ? (
              <div className="flex justify-center py-4"><Loader2 className="animate-spin text-secondary" /></div>
            ) : affectedSuppliers?.length === 0 ? (
              <p className="text-body-md text-secondary text-center py-4">No high-exposure suppliers.</p>
            ) : (
              <div className="space-y-3">
                {affectedSuppliers?.map((s) => (
                  <div key={s.id} className="flex items-center justify-between py-3">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 surface-container-highest rounded-sm flex items-center justify-center">
                        <FileText size={14} className="text-secondary" />
                      </div>
                      <div>
                        <p className="font-headline font-bold text-sm">{s.name}</p>
                        <p className="text-label-sm text-secondary">{s.location} · {s.tier}</p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className={`text-body-md font-bold ${s.exposureScore > 75 ? "text-sentinel" : "text-yellow-500"}`}>
                        {s.exposureScore > 75 ? "Critical Impact" : "Moderate Risk"}
                      </p>
                      <p className="text-label-sm text-secondary">Score: {s.exposureScore.toFixed(1)}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {stageKey === "decide" ? (
            <div className="surface-container-high rounded-lg p-6 space-y-4">
              <h3 className="font-headline font-bold text-lg">Route inputs (from onboarding)</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <label className="space-y-1">
                  <div className="text-label-sm text-secondary uppercase tracking-widest">Supplier</div>
                  <select
                    value={selectedSupplierName}
                    onChange={(e) => setSelectedSupplierName(e.target.value)}
                    className="w-full bg-surface-highest border border-border rounded-sm px-3 py-2 text-body-md"
                  >
                    {(contextSuppliers || []).map((s, idx) => (
                      <option key={`${s.name}-${idx}`} value={String(s.name || "")}>
                        {String(s.name || "Supplier")}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="space-y-1">
                  <div className="text-label-sm text-secondary uppercase tracking-widest">Origin node</div>
                  <select
                    value={selectedOriginNodeName}
                    onChange={(e) => setSelectedOriginNodeName(e.target.value)}
                    className="w-full bg-surface-highest border border-border rounded-sm px-3 py-2 text-body-md"
                  >
                    {originCandidates.map((n, idx) => (
                      <option key={`${n.name}-${idx}`} value={String(n.name || "")}>
                        {String(n.name || "Node")}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <label className="space-y-1">
                <div className="text-label-sm text-secondary uppercase tracking-widest">Destination (city/port/warehouse)</div>
                <input
                  value={destinationQuery}
                  onChange={(e) => {
                    setDestinationQuery(e.target.value);
                    setDestinationPoint(null);
                  }}
                  placeholder="e.g., Bangalore, India"
                  className="w-full bg-surface-highest border border-border rounded-sm px-3 py-2 text-body-md"
                />
              </label>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <label className="space-y-1">
                  <div className="text-label-sm text-secondary uppercase tracking-widest">Weight (t)</div>
                  <input
                    value={cargo.weight_tonnes}
                    onChange={(e) => setCargo((c) => ({ ...c, weight_tonnes: e.target.value }))}
                    className="w-full bg-surface-highest border border-border rounded-sm px-3 py-2 text-body-md"
                  />
                </label>
                <label className="space-y-1">
                  <div className="text-label-sm text-secondary uppercase tracking-widest">Volume (cbm)</div>
                  <input
                    value={cargo.volume_cbm}
                    onChange={(e) => setCargo((c) => ({ ...c, volume_cbm: e.target.value }))}
                    className="w-full bg-surface-highest border border-border rounded-sm px-3 py-2 text-body-md"
                  />
                </label>
                <label className="flex items-center gap-2 mt-6">
                  <input
                    type="checkbox"
                    checked={cargo.hazmat}
                    onChange={(e) => setCargo((c) => ({ ...c, hazmat: e.target.checked }))}
                  />
                  <span className="text-body-md text-secondary">Hazmat</span>
                </label>
                <label className="flex items-center gap-2 mt-6">
                  <input
                    type="checkbox"
                    checked={cargo.temperature}
                    onChange={(e) => setCargo((c) => ({ ...c, temperature: e.target.checked }))}
                  />
                  <span className="text-body-md text-secondary">Temp-controlled</span>
                </label>
              </div>

              <button
                type="button"
                onClick={computeRoutes}
                disabled={decideLoading || !selectedOriginNodeName || !destinationQuery.trim()}
                className="w-full bg-foreground text-background py-3 rounded-sm font-medium flex items-center justify-center gap-2 hover:opacity-90 transition-opacity disabled:opacity-40"
              >
                {decideLoading ? <Loader2 className="animate-spin" size={16} /> : null}
                Compute Sea / Air / Land options
              </button>

              {routeComparison?.length ? (
                <div className="space-y-3">
                  <div className="text-label-sm text-secondary uppercase tracking-widest">
                    Recommended: <span className="text-sentinel">{recommendedMode || "—"}</span>
                    {typeof currencyRiskIndex === "number" ? (
                      <span className="text-secondary"> · currency risk index {currencyRiskIndex.toFixed(2)}</span>
                    ) : null}
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-body-md">
                      <thead className="text-label-sm text-secondary uppercase tracking-widest">
                        <tr>
                          <th className="py-2">Mode</th>
                          <th className="py-2">Time</th>
                          <th className="py-2">Distance</th>
                          <th className="py-2">Cost</th>
                          <th className="py-2">Select</th>
                        </tr>
                      </thead>
                      <tbody>
                        {routeComparison.map((r, idx) => (
                          <tr key={idx} className="border-t border-border">
                            <td className="py-2 font-medium">{String(r.mode || "—")}</td>
                            <td className="py-2">{String(r.transit_days ? `${r.transit_days} d` : r.flight_hours ? `${r.flight_hours} h` : r?.maps?.duration || "—")}</td>
                            <td className="py-2">{typeof r.distance_km === "number" ? `${r.distance_km.toFixed(0)} km` : "—"}</td>
                            <td className="py-2">{typeof r.cost_usd === "number" ? `$${Math.round(r.cost_usd).toLocaleString()}` : "—"}</td>
                            <td className="py-2">
                              <button
                                type="button"
                                onClick={async () => {
                                  const mode = String(r.mode || "") as any;
                                  setSelectedMode(mode);
                                  await api.workflow.upsertReportStage({
                                    workflow_id: workflowId,
                                    stage: "decide",
                                    payload: {
                                      decided_at: stageTimesRef.current.decide || new Date().toISOString(),
                                      decision_gate: stageDecision,
                                      supplier: selectedSupplier,
                                      origin_node: selectedOriginNode,
                                      destination_query: destinationQuery,
                                      destination_point: destinationPoint,
                                      cargo,
                                      recommended_mode: recommendedMode || null,
                                      currency_risk_index: currencyRiskIndex,
                                      route_comparison: routeComparison,
                                      selected_mode: mode,
                                    },
                                  });
                                }}
                                className={`px-3 py-1 rounded-sm border ${
                                  selectedMode === String(r.mode) ? "border-sentinel bg-sentinel/10 text-sentinel" : "border-border hover:bg-surface-highest/30"
                                }`}
                              >
                                {selectedMode === String(r.mode) ? "Selected" : "Choose"}
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : (
                <p className="text-body-md text-secondary">
                  Choose supplier + origin from onboarding, add a destination, then compute. The result is written into the workflow report and appears in the Audit PDF.
                </p>
              )}
            </div>
          ) : null}

          {stageKey === "act" ? (
            <div className="surface-container-high rounded-lg p-6 space-y-4">
              <h3 className="font-headline font-bold text-lg">Execute action</h3>
              {stageDecision === "reroute" ? (
                <div className="space-y-3">
                  <p className="text-body-md text-secondary">
                    Approve the reroute using your selected mode. This will be logged into the audit certificate (no hardcoded values).
                  </p>
                  <button
                    type="button"
                    onClick={async () => {
                      await confirmAct();
                      setCurrentStage(4);
                    }}
                    disabled={actDone || !(selectedMode || recommendedMode)}
                    className="w-full bg-foreground text-background py-3 rounded-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-40"
                  >
                    Confirm reroute and advance to AUDIT
                  </button>
                </div>
              ) : (
                <div className="space-y-3">
                  {!rfqDraft ? (
                    <button
                      type="button"
                      onClick={confirmAct}
                      className="w-full bg-foreground text-background py-3 rounded-sm font-medium hover:opacity-90 transition-opacity"
                    >
                      Draft RFQ from onboarding context
                    </button>
                  ) : (
                    <div className="space-y-3">
                      <label className="space-y-1">
                        <div className="text-label-sm text-secondary uppercase tracking-widest">To</div>
                        <input
                          value={rfqDraft.recipient}
                          onChange={(e) => setRfqDraft((d) => (d ? { ...d, recipient: e.target.value } : d))}
                          className="w-full bg-surface-highest border border-border rounded-sm px-3 py-2 text-body-md"
                        />
                      </label>
                      <label className="space-y-1">
                        <div className="text-label-sm text-secondary uppercase tracking-widest">Subject</div>
                        <input
                          value={rfqDraft.subject}
                          onChange={(e) => setRfqDraft((d) => (d ? { ...d, subject: e.target.value } : d))}
                          className="w-full bg-surface-highest border border-border rounded-sm px-3 py-2 text-body-md"
                        />
                      </label>
                      <label className="space-y-1">
                        <div className="text-label-sm text-secondary uppercase tracking-widest">Body</div>
                        <textarea
                          value={rfqDraft.body}
                          onChange={(e) => setRfqDraft((d) => (d ? { ...d, body: e.target.value } : d))}
                          rows={8}
                          className="w-full bg-surface-highest border border-border rounded-sm px-3 py-2 text-body-md"
                        />
                      </label>
                      <button
                        type="button"
                        onClick={async () => {
                          await sendRfq();
                          setCurrentStage(4);
                        }}
                        disabled={rfqSending || actDone}
                        className="w-full bg-foreground text-background py-3 rounded-sm font-medium flex items-center justify-center gap-2 hover:opacity-90 transition-opacity disabled:opacity-40"
                      >
                        {rfqSending ? <Loader2 className="animate-spin" size={16} /> : null}
                        Send RFQ and advance to AUDIT
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : null}

          {stageKey === "audit" ? (
            <div className="surface-container-high rounded-lg p-6 space-y-3">
              <h3 className="font-headline font-bold text-lg">Finalize audit</h3>
              <p className="text-body-md text-secondary">
                This writes the real response time and timeline into the workflow report, and the PDF is generated from that data (no hardcoded placeholders).
              </p>
              <button
                type="button"
                onClick={completeAudit}
                className="w-full bg-foreground text-background py-3 rounded-sm font-medium hover:opacity-90 transition-opacity"
              >
                Finalize audit record
              </button>
            </div>
          ) : null}

          {/* Decision + PDF at the end */}
          {currentStage >= 2 && currentStage < 4 ? (
            <div className="surface-container-high rounded-lg p-6">
              <h3 className="font-headline font-bold text-lg mb-3">Decision Gate (one click)</h3>
              <p className="text-label-sm text-secondary uppercase tracking-widest mb-3">
                Selected: <span className="text-sentinel">{stageDecision === "reroute" ? "Reroute shipments" : "Activate backup supplier"}</span>
              </p>
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => setStageDecision("reroute")}
                  className={`px-3 py-3 rounded-sm border transition-colors ${
                    stageDecision === "reroute" ? "border-sentinel bg-sentinel/10" : "border-border hover:bg-surface-highest/30"
                  }`}
                >
                  <div className="font-headline font-bold text-sm">Option A</div>
                  <div className="text-label-sm text-secondary mt-1">Reroute shipments</div>
                </button>
                <button
                  type="button"
                  onClick={() => setStageDecision("backup_supplier")}
                  className={`px-3 py-3 rounded-sm border transition-colors ${
                    stageDecision === "backup_supplier" ? "border-sentinel bg-sentinel/10" : "border-border hover:bg-surface-highest/30"
                  }`}
                >
                  <div className="font-headline font-bold text-sm">Option B</div>
                  <div className="text-label-sm text-secondary mt-1">Activate backup supplier</div>
                </button>
              </div>
              <p className="text-label-sm text-secondary mt-3">
                This selection is what gets written into the compliance report as the single human approval point.
              </p>
            </div>
          ) : null}

          {currentStage >= 4 ? (
            <div className="surface-container-high rounded-lg p-6">
              <h3 className="font-headline font-bold text-lg mb-2">Audit Certificate</h3>
              <p className="text-body-md text-secondary mb-4">
                The workflow has generated a full stage-by-stage compliance report.
              </p>
              <a
                href={api.workflow.reportPdfUrl(workflowId)}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center justify-center w-full bg-foreground text-background py-3 rounded-sm font-medium hover:opacity-90 transition-opacity"
              >
                Download Audit Report (PDF)
              </a>
            </div>
          ) : null}

          <button
            onClick={async () => {
              if (stageKey === "decide") {
                if (!routeComparison?.length) {
                  await computeRoutes();
                  return;
                }
                setCurrentStage(3);
                return;
              }
              if (stageKey === "act") {
                // Encourage using explicit ACT buttons above (confirm/send). Keep fallback.
                if (!actDone) {
                  await confirmAct();
                  return;
                }
                setCurrentStage(4);
                return;
              }
              if (stageKey === "audit") {
                await completeAudit();
                return;
              }
              setCurrentStage((s) => Math.min(s + 1, STAGES.length - 1));
            }}
            disabled={currentStage >= STAGES.length - 1}
            className="w-full bg-foreground text-background py-3 rounded-sm font-medium flex items-center justify-center gap-2 hover:opacity-90 transition-opacity disabled:opacity-40"
          >
            {currentStage >= STAGES.length - 1 ? "Workflow Complete ✓" : `Advance to ${STAGES[currentStage + 1]} →`}
          </button>
        </div>
      </div>
    </div>
  );
};

export default WorkflowEngine;
