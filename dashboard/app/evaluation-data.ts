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
    tier: "full · injected pilot",
    work: "20 chains × 100 iterations",
    fullSeconds: 2.1837,
    fusedSeconds: 2.0116,
    speedup: 1.0856,
    objective: "Tissue codon score + GC%",
    objectiveError: "2.21e−15 tissue MAE · 1.36e−13 pp GC MAE",
    status: "paired",
    note: "Paired experimental injection. It is not a registered FusionBundle and the support gate is not wired into routing.",
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
  { layer: "Run summary", state: "partial", detail: "Wall time, tier, work count, and final output exist for four Modal smokes." },
  { layer: "Operational checkpoint", state: "available", detail: "Every completed MCMC step, cycling round, or rejection proposal batch is saved atomically with optimizer and RNG state." },
  { layer: "Eval-grade proposal trace", state: "partial", detail: "A durable unit ledger now stores energy summaries and sequence hashes, but not raw teacher outputs or objective-level latency." },
  { layer: "Parent model outputs", state: "missing", detail: "No durable, versioned teacher-output table across workloads." },
  { layer: "Surrogate output + uncertainty", state: "missing", detail: "No registered bundle emits prediction, uncertainty, and gate records." },
  { layer: "Route + defer reason", state: "missing", detail: "Router behavior has synthetic unit tests, not real workload traces." },
  { layer: "Objective + paper provenance", state: "partial", detail: "21 of 51 constraints have evidence entries; only 3 of 12 fixtures point to paper text." },
] as const;

export const heldOutRows = [
  { cohort: "Train", count: "1,198", coverage: "CUSTOM trajectory groups 0–2", verdict: "available" },
  { cohort: "Calibration / val", count: "396", coverage: "CUSTOM trajectory group 3", verdict: "available" },
  { cohort: "Audit / test", count: "398", coverage: "CUSTOM trajectory group 4", verdict: "available" },
  { cohort: "Full-trajectory holdout", count: "1,998", coverage: "20 separate 100-step chains", verdict: "available" },
  { cohort: "Negative / OOD challenges", count: "4", coverage: "Hand-crafted; all correctly rejected", verdict: "thin" },
  { cohort: "Held-out high-value positives", count: "0", coverage: "No positive acceptance test set", verdict: "missing" },
  { cohort: "Positive-but-uncertain deferrals", count: "0", coverage: "No safe-deferral test set", verdict: "missing" },
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
