import type { RouteOption } from "@/types/workflow";

export type MonteCarloSummary = {
  runs: number;
  protectedRate: number;
  averageDelayDays: number;
  expectedExposureAvoidedUsd: number;
  routeReliability: number;
  worstCaseLossUsd: number;
  recommendation: "Approve air backup" | "Escalate to human gate";
  probeNode: {
    id: string;
    name: string;
    exposureScore: number;
    dailyThroughputUsd: number;
    stockoutDays: number;
    riskUsd: number;
  };
};

type Rng = () => number;

const createRng = (seed: number): Rng => {
  let value = seed % 2147483647;
  if (value <= 0) value += 2147483646;

  return () => {
    value = (value * 16807) % 2147483647;
    return (value - 1) / 2147483646;
  };
};

const randomBetween = (rng: Rng, min: number, max: number) => min + (max - min) * rng();

export const runDemoMonteCarlo = (
  routes: RouteOption[],
  seed: number,
  runs = 500,
): MonteCarloSummary => {
  const rng = createRng(seed);
  const recommendedRoute = routes.find((route) => route.recommended) ?? routes[0];
  const probeNode = {
    id: `synthetic_probe_${seed}`,
    name: "Synthetic Supplier Probe",
    exposureScore: recommendedRoute.mode === "air" ? 78 : 64,
    dailyThroughputUsd: recommendedRoute.mode === "air" ? 185000 : 142000,
    stockoutDays: recommendedRoute.mode === "air" ? 4.8 : 3.6,
    riskUsd: 0,
  };
  let protectedRuns = 0;
  let totalDelayDays = 0;
  let totalExposureAvoided = 0;
  let reliableRuns = 0;
  let worstCaseLoss = 0;

  for (let index = 0; index < runs; index += 1) {
    const disruptionDays = randomBetween(rng, 4.8, 10.4);
    const customsDrag = randomBetween(rng, 0.2, recommendedRoute.mode === "air" ? 0.8 : 1.9);
    const routeTransitDays =
      recommendedRoute.mode === "air"
        ? randomBetween(rng, 1.2, 2.9)
        : recommendedRoute.mode === "sea"
          ? randomBetween(rng, 11.5, 28.0)
          : randomBetween(rng, 3.8, 9.0);

    const reroutePenalty =
      recommendedRoute.mode === "air"
        ? randomBetween(rng, 0.05, 0.45)
        : recommendedRoute.mode === "sea"
          ? randomBetween(rng, 1.5, 4.8)
          : randomBetween(rng, 0.5, 1.8);
    const arrivalDays = routeTransitDays + customsDrag + reroutePenalty;
    const marginDays = probeNode.stockoutDays - arrivalDays;
    const protectedScenario = marginDays >= 0;
    const continuityGapDays = Math.max(0, arrivalDays - probeNode.stockoutDays);
    const exposureAvoided = protectedScenario
      ? probeNode.dailyThroughputUsd * randomBetween(rng, 7.5, 12.5)
      : probeNode.dailyThroughputUsd * randomBetween(rng, 1.4, 4.9);
    const lossIfMissed = probeNode.dailyThroughputUsd * Math.max(0.35, continuityGapDays) * randomBetween(rng, 0.45, 0.95);

    if (protectedScenario) protectedRuns += 1;
    if (arrivalDays <= disruptionDays) reliableRuns += 1;

    totalDelayDays += continuityGapDays;
    totalExposureAvoided += exposureAvoided;
    worstCaseLoss = Math.max(worstCaseLoss, lossIfMissed);
  }

  const protectedRate = protectedRuns / runs;
  const routeReliability = reliableRuns / runs;
  probeNode.riskUsd = Math.round(worstCaseLoss);

  return {
    runs,
    protectedRate,
    averageDelayDays: totalDelayDays / runs,
    expectedExposureAvoidedUsd: totalExposureAvoided / runs,
    routeReliability,
    worstCaseLossUsd: worstCaseLoss,
    recommendation:
      protectedRate >= 0.78 && routeReliability >= 0.75 ? "Approve air backup" : "Escalate to human gate",
    probeNode,
  };
};
