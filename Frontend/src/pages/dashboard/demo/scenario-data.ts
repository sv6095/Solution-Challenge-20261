import type {
  AssessmentCard,
  AuditCertificate,
  ReasoningStep,
  RouteOption,
  Signal,
  SupplierNode,
  WorkflowState,
} from "@/types/workflow";

export type DemoStage = {
  stage: WorkflowState["stage"];
  title: string;
  agent: string;
  summary: string;
  outcome: string;
};

export type DemoPipelineStep = {
  id: string;
  order: number;
  title: string;
  agent: string;
  mode: "autonomous" | "human" | "execution";
  summary: string;
  outcome: string;
};

export const demoWorkflowState: WorkflowState = {
  workflow_id: "demo-typhoon-yagi-2026-04",
  stage: "AUDIT",
  status: "complete",
  created_at: "2026-04-17T03:47:00Z",
  updated_at: "2026-04-17T07:15:24Z",
};

export const demoSignals: Signal[] = [
  {
    signal_id: "sig-nasa-yagi",
    title: "Typhoon Yagi tracked over the South China Sea",
    event_type: "severeStorm",
    severity: 8.8,
    location: "South China Sea",
    lat: 18.2,
    lng: 114.8,
    source: "NASA EONET",
    source_url: "https://eonet.gsfc.nasa.gov/",
    source_type: "government",
    verified: true,
    corroborated_by: ["NewsAPI", "GDELT", "GNews"],
    corroboration_count: 3,
    detected_at: "2026-04-17T03:47:00Z",
    relevance_score: 0.91,
  },
  {
    signal_id: "sig-news-yagi",
    title: "Ports in Vietnam prepare suspensions as Typhoon Yagi intensifies",
    event_type: "portDisruption",
    severity: 7.9,
    location: "Ho Chi Minh City",
    lat: 10.8231,
    lng: 106.6297,
    source: "NewsAPI",
    source_url: "https://newsapi.org/",
    source_type: "news",
    verified: false,
    corroborated_by: ["NASA EONET", "GDELT"],
    corroboration_count: 2,
    detected_at: "2026-04-17T03:47:00Z",
    relevance_score: 0.86,
  },
  {
    signal_id: "sig-gdelt-yagi",
    title: "Regional logistics advisories indicate vessel delays and cargo backlog risk",
    event_type: "logisticsAlert",
    severity: 7.2,
    location: "Vietnam and Singapore corridor",
    lat: 1.3521,
    lng: 103.8198,
    source: "GDELT",
    source_url: "https://www.gdeltproject.org/",
    source_type: "geopolitical",
    verified: false,
    corroborated_by: ["NASA EONET", "NewsAPI"],
    corroboration_count: 2,
    detected_at: "2026-04-17T03:47:00Z",
    relevance_score: 0.81,
  },
];

export const demoSuppliers: SupplierNode[] = [
  {
    supplier_id: "sup-hcm-01",
    name: "Ho Chi Minh Assembly",
    city: "Ho Chi Minh City",
    country: "Vietnam",
    tier: 1,
    transport_mode: "sea",
    category: "PCB sub-assemblies",
    lat: 10.8231,
    lng: 106.6297,
    exposure_score: 92,
    exposure_label: "High Risk",
    risk_points: 5,
    is_backup: false,
    email: "ops@hcm-assembly.example",
  },
  {
    supplier_id: "sup-penang-01",
    name: "Penang Components",
    city: "George Town",
    country: "Malaysia",
    tier: 1,
    transport_mode: "sea",
    category: "microcontrollers",
    lat: 5.4141,
    lng: 100.3288,
    exposure_score: 84,
    exposure_label: "High Risk",
    risk_points: 5,
    is_backup: false,
    email: "supply@penang-components.example",
  },
  {
    supplier_id: "sup-shenzhen-02",
    name: "Shenzhen Substrates",
    city: "Shenzhen",
    country: "China",
    tier: 2,
    transport_mode: "mixed",
    category: "substrates",
    lat: 22.5431,
    lng: 114.0579,
    exposure_score: 71,
    exposure_label: "High Risk",
    risk_points: 5,
    is_backup: false,
  },
  {
    supplier_id: "sup-bangalore-backup",
    name: "Bangalore Electronics",
    city: "Bangalore",
    country: "India",
    tier: 1,
    transport_mode: "land",
    category: "backup PCB line",
    lat: 12.9716,
    lng: 77.5946,
    exposure_score: 18,
    exposure_label: "Low Risk",
    risk_points: 1,
    is_backup: true,
    email: "procurement@bangalore-electronics.example",
  },
];

export const demoRoutes: RouteOption[] = [
  {
    mode: "sea",
    engine: "haversine",
    distance_km: 3220,
    transit_days: 31,
    cost_usd: 1890,
    lane: "Pacific",
    selected: false,
    recommended: false,
  },
  {
    mode: "air",
    engine: "maps",
    distance_km: 2735,
    duration_hours: 51,
    flight_hours: 8.5,
    cost_usd: 8200,
    selected: true,
    recommended: true,
    currency: "INR",
    cost_local: 683000,
  },
  {
    mode: "land",
    engine: "sssp",
    distance_km: 0,
    duration_hours: 0,
    cost_usd: 0,
    selected: false,
    recommended: false,
  },
];

export const demoAssessment: AssessmentCard = {
  workflow_id: demoWorkflowState.workflow_id,
  affected_suppliers: demoSuppliers.filter((supplier) => !supplier.is_backup),
  exposure_usd: 2100000,
  exposure_local: 174615000,
  exposure_currency: "INR",
  days_at_risk: 4,
  confidence: 0.87,
  analysis_summary:
    "Typhoon Yagi materially disrupts Vietnam-linked PCB supply. Air activation of the Bangalore backup lane prevents stockout while preserving auditability.",
  inflation_risk: "MODERATE",
  currency_risk_index: 62,
};

export const demoReasoningSteps: ReasoningStep[] = [
  {
    agent: "signal_agent",
    stage: "signal_relevance_check",
    detail:
      "NASA EONET severe storm matched 3 supplier geofences. Cross-source corroboration raised confidence above the autonomous assessment threshold.",
    status: "success",
    timestamp: "2026-04-17T03:47:00Z",
    timestamp_ms: 1776397620000,
    output: { score: 0.91, passed: true, corroborated_by: 3 },
  },
  {
    agent: "assessment_agent",
    stage: "gnn_risk_propagation",
    detail:
      "Praecantator risk propagation pushed the storm impact across the real supplier topology, identifying direct and cascading node exposure before the financial summary was assembled.",
    status: "success",
    timestamp: "2026-04-17T03:47:01Z",
    timestamp_ms: 1776397621000,
    output: { cost_usd: 2100000, days_at_risk: 4 },
  },
  {
    agent: "graph_agent",
    stage: "graph_forward_pass",
    detail:
      "The graph agent injected the disruption event into the supply chain graph and scored upstream and downstream dependencies to surface hidden tier-2 propagation risk.",
    status: "success",
    timestamp: "2026-04-17T03:47:01Z",
    timestamp_ms: 1776397621050,
    output: { affected_nodes: 3, total_nodes_scanned: 847, model: "praecantator" },
  },
  {
    agent: "assessment_agent",
    stage: "llm_fallback",
    detail:
      "Demo mode shows the dev fallback path too: if the primary model is unavailable, the fallback engine can still generate the same brief and preserve operator continuity.",
    status: "fallback",
    timestamp: "2026-04-17T03:47:01Z",
    timestamp_ms: 1776397621300,
    output: { primary: "AI AGENT", fallback: "FALLBACK ENGINE" },
  },
  {
    agent: "routing_agent",
    stage: "sssp_cache_check",
    detail:
      "Sea, air, and land route engines ran in parallel. Air produced the only route that beats the 4-day stockout deadline with acceptable confidence.",
    status: "success",
    timestamp: "2026-04-17T03:47:02Z",
    timestamp_ms: 1776397622000,
    output: { cache_hit: false, recommended_mode: "air" },
  },
  {
    agent: "decision_agent",
    stage: "human_gate_evaluation",
    detail:
      "Decision policy compared confidence, value at risk, and stockout window, then packaged a single approval recommendation instead of raw analytics alone.",
    status: "success",
    timestamp: "2026-04-17T03:47:02Z",
    timestamp_ms: 1776397622400,
    output: { confidence: 0.87, requires_human_gate: true, recommendation: "approve_backup_supplier_and_air_route" },
  },
  {
    agent: "rfq_agent",
    stage: "emergency_rfq_draft",
    detail:
      "RFQ draft generated with quantity, delivery window, target price, and Chennai destination already filled from shared workflow state.",
    status: "success",
    timestamp: "2026-04-17T03:47:03Z",
    timestamp_ms: 1776397623000,
    output: { supplier: "Bangalore Electronics", units: 4200 },
  },
  {
    agent: "notification_agent",
    stage: "incident_card_published",
    detail:
      "The incident card was written to the dashboard feed with recommendation, route options, affected nodes, and approval state already pre-populated.",
    status: "success",
    timestamp: "2026-04-17T03:47:03Z",
    timestamp_ms: 1776397623400,
    output: { status: "AWAITING_APPROVAL", notification_sent: true },
  },
  {
    agent: "action_agent",
    stage: "post_approval_execution",
    detail:
      "After one human approval, the system dispatched the RFQ, confirmed the route, and generated the airway-bill reference as compensable post-approval actions.",
    status: "success",
    timestamp: "2026-04-17T07:15:23Z",
    timestamp_ms: 1776410123000,
    output: { rfq_sent: true, route_confirmed: true, awb_reference: "AWB-7F4C92AB" },
  },
  {
    agent: "audit_agent",
    stage: "certificate_generation",
    detail:
      "Audit trail persisted with reasoning steps, action approval timestamp, and the PDF-ready incident certificate for downstream compliance review.",
    status: "success",
    timestamp: "2026-04-17T07:15:24Z",
    timestamp_ms: 1776410124000,
    output: { frameworks: ["EU CSDDD", "Internal SCRM SOP"] },
  },
];

export const demoAuditCertificate: AuditCertificate = {
  workflow_id: demoWorkflowState.workflow_id,
  generated_at: "2026-04-17T07:15:24Z",
  response_time_seconds: 144,
  stages_completed: ["DETECT", "ASSESS", "DECIDE", "ACT", "AUDIT"],
  compliance_frameworks: ["EU CSDDD", "Supplier Continuity SOP", "Emergency Sourcing Playbook"],
  pdf_url: "/demo/audit/typhoon-yagi-certificate.pdf",
};

export const demoStages: DemoStage[] = [
  {
    stage: "DETECT",
    title: "Signal",
    agent: "signal_agent",
    summary: "Collects events from NASA EONET, NewsAPI, GDELT, and GNews.",
    outcome: "Corroborated storm signal scored 0.91 relevance and opened a workflow.",
  },
  {
    stage: "ASSESS",
    title: "Assess",
    agent: "assessment_agent",
    summary: "Runs Praecantator scoring, exposure estimates, and provider-aware LLM briefing.",
    outcome: "Three suppliers crossed the action threshold with $2.1M exposure.",
  },
  {
    stage: "DECIDE",
    title: "Decide",
    agent: "routing_agent",
    summary: "Compares route engines and confidence rules before autonomous action.",
    outcome: "Air freight plus backup supplier cleared the human-gate threshold.",
  },
  {
    stage: "ACT",
    title: "Act",
    agent: "rfq_agent",
    summary: "Drafts the RFQ, prepares outreach, and packages the recommended move.",
    outcome: "One-click approval sends the emergency RFQ and confirms the lane.",
  },
  {
    stage: "AUDIT",
    title: "Audit",
    agent: "audit_agent",
    summary: "Writes the immutable trail, produces export-ready evidence, and closes the loop.",
    outcome: "Compliance receives a complete certificate without manual reconstruction.",
  },
];

export const demoPipelineSteps: DemoPipelineStep[] = [
  {
    id: "step-1",
    order: 1,
    title: "Signal ingestion",
    agent: "signal_agent",
    mode: "autonomous",
    summary: "Reads live-style events from external signal sources and filters for supply-chain relevance.",
    outcome: "A corroborated Typhoon Yagi event opens an incident candidate.",
  },
  {
    id: "step-2",
    order: 2,
    title: "Graph scoring",
    agent: "graph_agent",
    mode: "autonomous",
    summary: "Injects the event into the supplier graph and runs Praecantator risk propagation on the topology.",
    outcome: "Direct and cascading supplier nodes are scored from the same disruption.",
  },
  {
    id: "step-3",
    order: 3,
    title: "Assessment briefing",
    agent: "assessment_agent",
    mode: "autonomous",
    summary: "Builds the exposure view, stockout horizon, and operator briefing from the Praecantator outputs.",
    outcome: "$2.1M exposure and a 4-day stockout window are calculated.",
  },
  {
    id: "step-4",
    order: 4,
    title: "Route generation",
    agent: "routing_agent",
    mode: "autonomous",
    summary: "Compares sea, air, and land options using the route engines and lane disruption context.",
    outcome: "Air is the only route that meets the deadline with acceptable risk.",
  },
  {
    id: "step-5",
    order: 5,
    title: "Decision packaging",
    agent: "decision_agent",
    mode: "autonomous",
    summary: "Applies confidence and policy logic to decide whether to escalate and what the operator should approve.",
    outcome: "A single recommended action is prepared for the human gate.",
  },
  {
    id: "step-6",
    order: 6,
    title: "RFQ drafting",
    agent: "rfq_agent",
    mode: "autonomous",
    summary: "Drafts the supplier communication with the incident context already embedded.",
    outcome: "The emergency RFQ is ready before the user opens the app.",
  },
  {
    id: "step-7",
    order: 7,
    title: "Notification and card publish",
    agent: "notification_agent",
    mode: "autonomous",
    summary: "Publishes the incident card and notifies the operator that a decision is waiting.",
    outcome: "The dashboard shows a complete pre-analyzed incident card in awaiting-approval state.",
  },
  {
    id: "step-8",
    order: 8,
    title: "Human review",
    agent: "operator",
    mode: "human",
    summary: "The operator reviews a fully assembled card instead of rebuilding context manually.",
    outcome: "One click approves the recommended action.",
  },
  {
    id: "step-9",
    order: 9,
    title: "Execution and audit",
    agent: "action_agent + audit_agent",
    mode: "execution",
    summary: "Approval triggers the side effects: dispatch RFQ, confirm route, write audit record, and close the loop.",
    outcome: "The incident moves from analysis to execution with a complete evidence trail.",
  },
];
