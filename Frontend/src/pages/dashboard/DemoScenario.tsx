import { useState } from "react";
import {
  Activity,
  ArrowRight,
  BadgeCheck,
  BrainCircuit,
  CloudLightning,
  FileCheck,
  Gauge,
  Plane,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Target,
} from "lucide-react";

import {
  demoAssessment,
  demoAuditCertificate,
  demoPipelineSteps,
  demoReasoningSteps,
  demoRoutes,
  demoSignals,
  demoStages,
  demoSuppliers,
  demoWorkflowState,
} from "@/pages/dashboard/demo/scenario-data";
import { runDemoMonteCarlo } from "@/pages/dashboard/demo/monte-carlo";

const severityTone = (score: number) => {
  if (score >= 80) return "text-red-300 bg-red-500/10 border-red-500/30";
  if (score >= 50) return "text-amber-300 bg-amber-500/10 border-amber-500/30";
  return "text-emerald-300 bg-emerald-500/10 border-emerald-500/30";
};

const DemoScenario = () => {
  const [seed, setSeed] = useState(417);
  const simulation = runDemoMonteCarlo(demoRoutes, seed);
  const recommendedRoute = demoRoutes.find((route) => route.recommended) ?? demoRoutes[0];

  return (
    <div className="space-y-6">
      <section className="relative overflow-hidden rounded-3xl border border-border/60 bg-[radial-gradient(circle_at_top_left,rgba(59,130,246,0.18),transparent_30%),radial-gradient(circle_at_top_right,rgba(234,88,12,0.16),transparent_35%),linear-gradient(180deg,rgba(15,23,42,0.94),rgba(7,10,18,0.98))] p-6 shadow-2xl shadow-black/20">
        <div className="absolute inset-y-0 right-0 w-1/3 bg-[linear-gradient(90deg,transparent,rgba(255,255,255,0.04))]" />
        <div className="relative grid gap-6 xl:grid-cols-[1.7fr_1fr]">
          <div className="space-y-4">
            <div className="inline-flex items-center gap-2 rounded-full border border-cyan-400/30 bg-cyan-400/10 px-3 py-1 text-[11px] font-mono uppercase tracking-[0.25em] text-cyan-200">
              <Sparkles className="h-3.5 w-3.5" />
              Demo Walkthrough
            </div>
            <div>
              <h1 className="text-3xl font-bold tracking-tight text-white">Typhoon Yagi Scenario Lab</h1>
              <p className="mt-2 max-w-3xl text-sm leading-7 text-slate-300">
                This page is a dashboard-native fake incident built for demos. It shows how Praecantator detects a disruption,
                runs Praecantator risk propagation on the supplier graph, packages a recommendation, drafts the RFQ, and closes the audit trail using the same autonomous pipeline
                shape defined in the backend.
              </p>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <div className="text-[11px] font-mono uppercase tracking-[0.18em] text-slate-400">Workflow</div>
                <div className="mt-2 text-2xl font-semibold text-white">{demoWorkflowState.status}</div>
                <div className="mt-1 text-sm text-slate-300">Stage: {demoWorkflowState.stage}</div>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <div className="text-[11px] font-mono uppercase tracking-[0.18em] text-slate-400">Exposure</div>
                <div className="mt-2 text-2xl font-semibold text-white">${(demoAssessment.exposure_usd / 1_000_000).toFixed(1)}M</div>
                <div className="mt-1 text-sm text-slate-300">{demoAssessment.days_at_risk} days to first stockout</div>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <div className="text-[11px] font-mono uppercase tracking-[0.18em] text-slate-400">Decision</div>
                <div className="mt-2 text-2xl font-semibold capitalize text-white">{recommendedRoute.mode}</div>
                <div className="mt-1 text-sm text-slate-300">Praecantator-ranked incident + backup supplier + RFQ</div>
              </div>
            </div>
          </div>

          <div className="rounded-3xl border border-cyan-400/20 bg-slate-950/60 p-5 backdrop-blur">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-[11px] font-mono uppercase tracking-[0.22em] text-slate-400">Monte Carlo</div>
                <div className="mt-1 text-lg font-semibold text-white">Demo confidence sweep</div>
              </div>
              <button
                type="button"
                onClick={() => setSeed((current) => current + 37)}
                className="inline-flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-900/80 px-3 py-2 text-xs font-medium text-slate-200 transition hover:border-slate-500 hover:text-white"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                Rerun
              </button>
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/10 p-4">
                <div className="text-[11px] font-mono uppercase tracking-[0.18em] text-emerald-200">Protected runs</div>
                <div className="mt-2 text-3xl font-semibold text-white">{Math.round(simulation.protectedRate * 100)}%</div>
              </div>
              <div className="rounded-2xl border border-sky-500/20 bg-sky-500/10 p-4">
                <div className="text-[11px] font-mono uppercase tracking-[0.18em] text-sky-200">Route reliability</div>
                <div className="mt-2 text-3xl font-semibold text-white">{Math.round(simulation.routeReliability * 100)}%</div>
              </div>
              <div className="rounded-2xl border border-amber-500/20 bg-amber-500/10 p-4">
                <div className="text-[11px] font-mono uppercase tracking-[0.18em] text-amber-200">Avg delay if missed</div>
                <div className="mt-2 text-3xl font-semibold text-white">{simulation.averageDelayDays.toFixed(1)}d</div>
              </div>
              <div className="rounded-2xl border border-fuchsia-500/20 bg-fuchsia-500/10 p-4">
                <div className="text-[11px] font-mono uppercase tracking-[0.18em] text-fuchsia-200">Exposure avoided</div>
                <div className="mt-2 text-3xl font-semibold text-white">${(simulation.expectedExposureAvoidedUsd / 1_000_000).toFixed(2)}M</div>
              </div>
            </div>

            <div className="mt-4 rounded-2xl border border-border/60 bg-slate-900/80 p-4">
              <div className="flex items-center gap-2 text-sm font-medium text-white">
                <Gauge className="h-4 w-4 text-cyan-300" />
                Recommendation
              </div>
              <p className="mt-2 text-sm leading-6 text-slate-300">
                Based on {simulation.runs} simulated disruptions, the preferred action is <span className="font-semibold text-white">{simulation.recommendation}</span>.
                Worst modeled downside for a missed response is ${(simulation.worstCaseLossUsd / 1_000_000).toFixed(2)}M.
              </p>
            </div>

            <div className="mt-4 rounded-2xl border border-amber-500/20 bg-amber-500/10 p-4">
              <div className="text-[11px] font-mono uppercase tracking-[0.18em] text-amber-200">Reality-check probe node</div>
              <div className="mt-2 text-lg font-semibold text-white">{simulation.probeNode.name}</div>
              <p className="mt-2 text-sm leading-6 text-slate-200">
                Exposure score {simulation.probeNode.exposureScore} · daily throughput ${(simulation.probeNode.dailyThroughputUsd / 1_000).toFixed(0)}k ·
                stockout window {simulation.probeNode.stockoutDays.toFixed(1)} days · modeled worst-case risk ${(simulation.probeNode.riskUsd / 1_000_000).toFixed(2)}M.
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="rounded-3xl border border-border/60 bg-surface-low p-5">
        <div className="flex items-center gap-2">
          <Activity className="h-5 w-5 text-cyan-300" />
          <h2 className="text-xl font-semibold text-white">Exact autonomous pipeline sequence</h2>
        </div>
        <p className="mt-2 text-sm leading-6 text-slate-400">
          This sequence now mirrors the backend workflow in `autonomous_pipeline.py`: seven autonomous steps, one human review step, then post-approval execution.
        </p>
        <div className="mt-5 grid gap-3 xl:grid-cols-3">
          {demoPipelineSteps.map((step) => (
            <div key={step.id} className="rounded-2xl border border-border/60 bg-slate-950/40 p-4">
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs font-mono uppercase tracking-[0.18em] text-slate-400">Step {step.order}</span>
                <span
                  className={`rounded-full border px-2.5 py-1 text-[11px] font-mono uppercase tracking-[0.18em] ${
                    step.mode === "autonomous"
                      ? "border-cyan-500/30 bg-cyan-500/10 text-cyan-200"
                      : step.mode === "human"
                        ? "border-amber-500/30 bg-amber-500/10 text-amber-200"
                        : "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
                  }`}
                >
                  {step.mode}
                </span>
              </div>
              <div className="mt-3 text-lg font-semibold text-white">{step.title}</div>
              <div className="mt-1 text-xs font-mono uppercase tracking-[0.18em] text-cyan-300">{step.agent}</div>
              <p className="mt-3 text-sm leading-6 text-slate-300">{step.summary}</p>
              <div className="mt-3 rounded-xl border border-border/60 bg-slate-900/70 p-3 text-sm leading-6 text-slate-200">
                {step.outcome}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-5">
        {demoStages.map((stage, index) => (
          <div key={stage.stage} className="rounded-2xl border border-border/60 bg-surface-low p-4 shadow-sm">
            <div className="flex items-center justify-between">
              <div className="text-[11px] font-mono uppercase tracking-[0.18em] text-slate-400">{stage.stage}</div>
              {index < demoStages.length - 1 && <ArrowRight className="h-4 w-4 text-slate-600" />}
            </div>
            <div className="mt-3 text-lg font-semibold text-white">{stage.title}</div>
            <div className="mt-1 text-xs font-mono uppercase tracking-[0.18em] text-cyan-300">{stage.agent}</div>
            <p className="mt-3 text-sm leading-6 text-slate-300">{stage.summary}</p>
            <div className="mt-4 rounded-xl border border-border/60 bg-slate-950/40 p-3 text-sm leading-6 text-slate-200">
              {stage.outcome}
            </div>
          </div>
        ))}
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <div className="space-y-6">
          <div className="rounded-3xl border border-border/60 bg-surface-low p-5">
            <div className="flex items-center gap-2">
              <CloudLightning className="h-5 w-5 text-cyan-300" />
              <h2 className="text-xl font-semibold text-white">Signals feeding the workflow</h2>
            </div>
            <p className="mt-2 text-sm leading-6 text-slate-400">
              These are fake records, but they mirror the fields your real signal agent uses: source, verification level, corroboration, and relevance score.
            </p>
            <div className="mt-5 space-y-3">
              {demoSignals.map((signal) => (
                <div key={signal.signal_id} className="rounded-2xl border border-border/60 bg-slate-950/40 p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`rounded-full border px-2.5 py-1 text-[11px] font-mono uppercase tracking-[0.18em] ${severityTone(signal.severity * 10)}`}>
                      {signal.source}
                    </span>
                    {signal.verified && (
                      <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-mono uppercase tracking-[0.18em] text-emerald-200">
                        Verified
                      </span>
                    )}
                  </div>
                  <div className="mt-3 text-base font-semibold text-white">{signal.title}</div>
                  <div className="mt-1 text-sm text-slate-400">
                    {signal.location} · relevance {(signal.relevance_score * 100).toFixed(0)}% · corroborated by {signal.corroboration_count} additional source{signal.corroboration_count === 1 ? "" : "s"}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-3xl border border-border/60 bg-surface-low p-5">
            <div className="flex items-center gap-2">
              <Target className="h-5 w-5 text-amber-300" />
              <h2 className="text-xl font-semibold text-white">Praecantator-scored suppliers and backup lane</h2>
            </div>
            <div className="mt-5 space-y-3">
              {demoSuppliers.map((supplier) => (
                <div key={supplier.supplier_id} className="rounded-2xl border border-border/60 bg-slate-950/40 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-base font-semibold text-white">{supplier.name}</div>
                      <div className="mt-1 text-sm text-slate-400">
                        Tier {supplier.tier} · {supplier.city}, {supplier.country} · {supplier.category}
                      </div>
                    </div>
                    <span className={`rounded-full border px-3 py-1 text-xs font-mono uppercase tracking-[0.18em] ${severityTone(supplier.exposure_score)}`}>
                      {supplier.exposure_label}
                    </span>
                  </div>
                  <div className="mt-3 flex items-center justify-between text-sm text-slate-300">
                    <span>Exposure score: {supplier.exposure_score}</span>
                    <span>{supplier.is_backup ? "Backup-ready supplier" : "Primary network dependency"}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="space-y-6">
          <div className="rounded-3xl border border-border/60 bg-surface-low p-5">
            <div className="flex items-center gap-2">
              <Plane className="h-5 w-5 text-emerald-300" />
              <h2 className="text-xl font-semibold text-white">Decision console</h2>
            </div>
            <p className="mt-2 text-sm leading-6 text-slate-400">
              This explains the routing and decision-agent handoff in plain English for a demo audience: why the app doesn&apos;t stop at Praecantator scores, but turns them into an executable recommendation.
            </p>
            <div className="mt-5 space-y-3">
              {demoRoutes.map((route) => (
                <div key={`${route.mode}-${route.engine ?? "na"}`} className="rounded-2xl border border-border/60 bg-slate-950/40 p-4">
                  <div className="flex items-center justify-between">
                    <div className="text-base font-semibold capitalize text-white">{route.mode}</div>
                    <div className="flex gap-2">
                      {route.recommended && (
                        <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-mono uppercase tracking-[0.18em] text-emerald-200">
                          Recommended
                        </span>
                      )}
                      {route.selected && (
                        <span className="rounded-full border border-cyan-500/30 bg-cyan-500/10 px-2.5 py-1 text-[11px] font-mono uppercase tracking-[0.18em] text-cyan-200">
                          Selected
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="mt-2 text-sm leading-6 text-slate-400">
                    Engine: {route.engine ?? "n/a"} · Distance: {route.distance_km.toLocaleString()} km · Cost: ${route.cost_usd.toLocaleString()}
                  </div>
                  <div className="mt-2 text-sm text-slate-300">
                    {route.mode === "sea" && `Transit time ${route.transit_days} days misses the stockout window.`}
                    {route.mode === "air" && `Arrives in roughly ${route.duration_hours} hours and preserves production continuity.`}
                    {route.mode === "land" && "No practical corridor for this cross-sea emergency, so the engine is retained for completeness but not chosen."}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-3xl border border-border/60 bg-surface-low p-5">
            <div className="flex items-center gap-2">
              <BrainCircuit className="h-5 w-5 text-fuchsia-300" />
              <h2 className="text-xl font-semibold text-white">Agent reasoning feed</h2>
            </div>
            <div className="mt-5 space-y-3">
              {demoReasoningSteps.map((step) => (
                <div key={`${step.timestamp_ms}-${step.stage}`} className="rounded-2xl border border-border/60 bg-slate-950/40 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-xs font-mono uppercase tracking-[0.18em] text-cyan-300">{step.agent}</div>
                      <div className="mt-1 text-sm font-semibold uppercase tracking-[0.08em] text-white">{step.stage.replace(/_/g, " ")}</div>
                    </div>
                    <span
                      className={`rounded-full border px-2.5 py-1 text-[11px] font-mono uppercase tracking-[0.18em] ${
                        step.status === "success"
                          ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
                          : step.status === "fallback"
                            ? "border-amber-500/30 bg-amber-500/10 text-amber-200"
                            : "border-red-500/30 bg-red-500/10 text-red-200"
                      }`}
                    >
                      {step.status}
                    </span>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-slate-300">{step.detail}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <div className="rounded-3xl border border-border/60 bg-surface-low p-5">
          <div className="flex items-center gap-2">
            <Activity className="h-5 w-5 text-orange-300" />
            <h2 className="text-xl font-semibold text-white">What the operator sees</h2>
          </div>
          <div className="mt-5 rounded-3xl border border-orange-500/20 bg-[linear-gradient(180deg,rgba(251,146,60,0.10),rgba(15,23,42,0.55))] p-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-lg font-semibold text-white">Typhoon Yagi · Critical incident</div>
                <div className="mt-1 text-sm text-slate-300">
                  3 suppliers affected · ${(demoAssessment.exposure_usd / 1_000_000).toFixed(1)}M exposure · {demoAssessment.days_at_risk} days to stockout
                </div>
              </div>
              <span className="rounded-full border border-red-500/30 bg-red-500/10 px-3 py-1 text-[11px] font-mono uppercase tracking-[0.18em] text-red-200">
                Needs approval
              </span>
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-3">
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-center">
                <div className="text-2xl font-semibold text-white">87%</div>
                <div className="mt-1 text-[11px] font-mono uppercase tracking-[0.16em] text-slate-400">Confidence</div>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-center">
                <div className="text-2xl font-semibold text-white">1 click</div>
                <div className="mt-1 text-[11px] font-mono uppercase tracking-[0.16em] text-slate-400">Human input</div>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-center">
                <div className="text-2xl font-semibold text-white">2.4s</div>
                <div className="mt-1 text-[11px] font-mono uppercase tracking-[0.16em] text-slate-400">Prep time</div>
              </div>
            </div>

            <div className="mt-5 rounded-2xl border border-emerald-500/20 bg-emerald-500/10 p-4">
              <div className="flex items-center gap-2 text-sm font-semibold text-white">
                <BadgeCheck className="h-4 w-4 text-emerald-300" />
                Preselected action
              </div>
              <p className="mt-2 text-sm leading-6 text-slate-200">
                Approve the decision-agent package: activate Bangalore Electronics, send the emergency RFQ, and reserve the air lane into Chennai before the first stockout threshold.
              </p>
            </div>
          </div>
        </div>

        <div className="rounded-3xl border border-border/60 bg-surface-low p-5">
          <div className="flex items-center gap-2">
            <FileCheck className="h-5 w-5 text-cyan-300" />
            <h2 className="text-xl font-semibold text-white">Audit and compliance closeout</h2>
          </div>
          <p className="mt-2 text-sm leading-6 text-slate-400">
            The final step is part of the demo because it proves the app is more than alerting. It can show the action, the reason, and the evidence chain.
          </p>

          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            <div className="rounded-2xl border border-border/60 bg-slate-950/40 p-4">
              <div className="text-[11px] font-mono uppercase tracking-[0.18em] text-slate-400">Certificate</div>
              <div className="mt-2 text-lg font-semibold text-white">{demoAuditCertificate.workflow_id}</div>
              <div className="mt-1 text-sm text-slate-400">
                Generated in {demoAuditCertificate.response_time_seconds}s with PDF export support.
              </div>
            </div>
            <div className="rounded-2xl border border-border/60 bg-slate-950/40 p-4">
              <div className="text-[11px] font-mono uppercase tracking-[0.18em] text-slate-400">Frameworks</div>
              <div className="mt-2 flex flex-wrap gap-2">
                {demoAuditCertificate.compliance_frameworks.map((framework) => (
                  <span key={framework} className="rounded-full border border-slate-700 bg-slate-900 px-2.5 py-1 text-[11px] font-mono uppercase tracking-[0.16em] text-slate-200">
                    {framework}
                  </span>
                ))}
              </div>
            </div>
          </div>

          <div className="mt-4 rounded-2xl border border-cyan-500/20 bg-cyan-500/10 p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-white">
              <ShieldCheck className="h-4 w-4 text-cyan-300" />
              Demo takeaway
            </div>
            <p className="mt-2 text-sm leading-6 text-slate-200">
              In the story told by this page, the operator does not rebuild context from email, spreadsheets, and chat threads. The app assembles the context, proposes the move,
              and leaves the human with a narrow approval decision plus a ready-made audit record.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
};

export default DemoScenario;
