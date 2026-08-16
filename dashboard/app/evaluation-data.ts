export type RunStatus = "paired" | "baseline" | "missing";

export type BenchmarkRun = {
  id: string;
  workload: string;
  tier: string;
  work: string;
  fullSeconds: number;
  fusedSeconds: number | null;
  speedup: number | null;
  objective: string;
  objectiveError: string;
  status: RunStatus;
  note: string;
};

export const auditDate = "15 Aug 2026";

export const benchmarks: BenchmarkRun[] = [
  {
    id: "custom-full",
    workload: "CUSTOM eGFP lung",
    tier: "smoke · paired diagnostic",
    work: "10 unseen trajectories × 20 steps",
    fullSeconds: 0.4111,
    fusedSeconds: 0.4074,
    speedup: 1.009,
    objective: "Tissue codon score",
    objectiveError: "0 final-energy error · 10 / 10 identical outputs",
    status: "paired",
    note: "Unreviewed tissue-only linear artifact with 35% surrogate coverage. The 95% speedup interval was 0.893–1.139×, so this was rejected as a speedup demo.",
  },
  {
    id: "esm2-smoke",
    workload: "ESM-2 protein maturation",
    tier: "smoke · Modal",
    work: "50 MCMC iterations",
    fullSeconds: 478.693,
    fusedSeconds: null,
    speedup: null,
    objective: "ESM-2 perplexity + pLDDT / PAE",
    objectiveError: "Not computed against paper objective",
    status: "baseline",
    note: "Original full-model path completed. This fixture is anchored to an internal candidate-workflow document, not a canonical paper.",
  },
  {
    id: "antibody-smoke",
    workload: "Antibody CDR maturation",
    tier: "smoke · Modal",
    work: "30 MCMC iterations",
    fullSeconds: 1848.9482,
    fusedSeconds: null,
    speedup: null,
    objective: "AbLang NLL + ipTM gates",
    objectiveError: "Not computed against paper objective",
    status: "baseline",
    note: "Original full-model path completed with a runtime compatibility workaround.",
  },
  {
    id: "rfdiffusion-smoke",
    workload: "RFdiffusion3 + Boltz-2 binder",
    tier: "smoke · Modal",
    work: "2 optimization cycles",
    fullSeconds: 622.1855,
    fusedSeconds: null,
    speedup: null,
    objective: "ipTM + binding strength + quality gates",
    objectiveError: "Not computed against paper objective",
    status: "baseline",
    note: "Original full-model path completed with runtime compatibility workarounds.",
  },
  {
    id: "boltz-sweep-smoke",
    workload: "Boltz-2 state sweep",
    tier: "smoke · Modal",
    work: "6 samples · 3 retained",
    fullSeconds: 404.573,
    fusedSeconds: null,
    speedup: null,
    objective: "State RMSD + mean pLDDT",
    objectiveError: "Not computed against paper objective",
    status: "baseline",
    note: "Original full-model sweep completed. No learned fused equivalent exists.",
  },
];

export const traceRows = [
  { layer: "Run summary", state: "partial", detail: "Wall time, tier, work count, and final output exist for four Modal smokes plus one local paired diagnostic." },
  { layer: "Operational checkpoint", state: "available", detail: "Every completed MCMC step, cycling round, or rejection proposal batch is saved atomically with optimizer and RNG state." },
  { layer: "Eval-grade proposal trace", state: "partial", detail: "The CUSTOM smoke has 600 parent-constraint rows across ten trajectories; the other workloads do not yet have teacher traces." },
  { layer: "Parent model outputs", state: "partial", detail: "A versioned CUSTOM teacher trace exists locally, but there is no cross-workload teacher table or external test trace." },
  { layer: "Surrogate output + uncertainty", state: "partial", detail: "The paired CUSTOM report aggregates real predictions and uncertainty gates; these records are not yet joined into the durable proposal trace." },
  { layer: "Route + defer reason", state: "partial", detail: "The paired diagnostic recorded 70 surrogate routes, 93 uncertainty deferrals, and 37 OOD deferrals." },
  { layer: "Objective + paper provenance", state: "partial", detail: "32 of 62 constraints have evidence entries; 3 of 15 fixtures point to paper-specific local text." },
] as const;

export const heldOutRows = [
  { cohort: "Current train", count: "120 states", coverage: "6 complete trajectories", verdict: "available" },
  { cohort: "Current calibration / val", count: "40 states", coverage: "2 complete trajectories", verdict: "available" },
  { cohort: "Current model audit", count: "40 states", coverage: "2 trajectories; inspected during model choice", verdict: "thin" },
  { cohort: "Paired downstream run", count: "200 proposals", coverage: "10 unseen trajectories; seeds 10–19", verdict: "available" },
  { cohort: "Planned train / val / test", count: "60 / 20 / 20", coverage: "Independent trajectories, not proposal rows", verdict: "missing" },
  { cohort: "Designed challenge set", count: "40–60 cases", coverage: "GC extremes, OOD, boundaries, non-finite", verdict: "missing" },
];

export const measurementGroups = [
  {
    title: "Objective fidelity",
    items: ["Per-objective MAE / RMSE / max error", "Rank correlation and top-k recall", "Paper-threshold pass/fail agreement", "Pareto hypervolume for multi-objective runs"],
  },
  {
    title: "Routing safety",
    items: ["False-accept rate on negative samples", "False-reject rate on valuable positives", "Selective risk vs coverage", "Deferral precision, reason, and parent recovery"],
  },
  {
    title: "Optimizer outcome",
    items: ["Final regret vs full-model run", "Best-seen score over steps and time", "Time-to-paper-threshold", "Seed-to-seed variance and win / tie / loss"],
  },
  {
    title: "Systems cost",
    items: ["End-to-end and per-step p50 / p95 latency", "Full-model calls and GPU-seconds avoided", "Dollar cost, memory, cache hit rate", "Failures, retries, and fallback overhead"],
  },
];
