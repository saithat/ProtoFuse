export type RunStatus = "confirmed" | "paired" | "baseline" | "missing";

export type BenchmarkRun = {
  id: string;
  workload: string;
  tier: string;
  work: string;
  fullSeconds: number | null;
  fusedSeconds: number | null;
  speedup: number | null;
  objective: string;
  objectiveError: string;
  status: RunStatus;
  note: string;
};

export const auditDate = "16 Aug 2026";

export const benchmarks: BenchmarkRun[] = [
  {
    id: "custom-adaptive-confirmation",
    workload: "CUSTOM adaptive MFE",
    tier: "full-pool · fresh confirmation · CPU",
    work: "4 seeds × 1,000 candidates",
    fullSeconds: null,
    fusedSeconds: null,
    speedup: 9.7171,
    objective: "Selective body-MFE with exact boundary and final-candidate recovery",
    objectiveError: "4 / 4 exact top-10 sets · 100% mean and minimum recall",
    status: "confirmed",
    note: "The frozen top-20 plus tail-2 policy passed every fresh confirmation gate: identical candidate pools, exact selected MFE values, no failed arms, 96.1% surrogate coverage, and 156 exact routes. This confirms one narrow experimental path; it does not approve broad automatic fusion.",
  },
  {
    id: "custom-sampled-window",
    workload: "CUSTOM sampled-window MFE",
    tier: "full-pool · initial paired cohort · CPU",
    work: "10 seeds × 1,000 candidates",
    fullSeconds: null,
    fusedSeconds: null,
    speedup: 12.2609,
    objective: "Stride-8 sampled body-MFE with uncertainty fallback",
    objectiveError: "0.91 mean top-10 recall · 0.80 minimum",
    status: "paired",
    note: "The frozen external audit passed at 99.075% coverage, 4.205% normalized accepted MAE, and 0.9835 accepted Spearman. The paired cohort avoided most MFE work, but approximate pool-wide ranking changed some top-10 members; the adaptive confirmation above is the stronger fidelity result.",
  },
  {
    id: "custom-exact-parallel",
    workload: "CUSTOM exact-parallel MFE",
    tier: "full-pool · paired systems result · CPU",
    work: "10 seeds × 1,000 candidates",
    fullSeconds: null,
    fusedSeconds: null,
    speedup: 5.7943,
    objective: "Complete released CUSTOM body-MFE calculation",
    objectiveError: "10 / 10 identical ordered top-10 sets",
    status: "paired",
    note: "Eight ordered worker processes reproduced every MFE calculation and exact selected outputs. The wall-time gain is a cores-for-time systems result: it parallelizes 10,000 parent evaluations and avoids no scientific calculations.",
  },
  {
    id: "ligandmpnn-esmfold",
    workload: "LigandMPNN + ESMFold",
    tier: "smoke · exploratory paired GPU",
    work: "2 seeds × 6 routing decisions",
    fullSeconds: 47.6435,
    fusedSeconds: 27.4646,
    speedup: 1.7347,
    objective: "LigandMPNN probability loss + ESMFold confidence energy",
    objectiveError: "Final outputs matched · frozen external audit failed",
    status: "paired",
    note: "The two Modal H100 pairs preserved final sequence and energy, with seven surrogate routes and five fallbacks. The separate 20-sample, four-trajectory audit failed both normalized-MAE and rank-correlation gates, so the artifact remains ineligible for automatic deployment.",
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
  { layer: "Paired run summaries", state: "available", detail: "CUSTOM has 24 full-pool paired runs across exact, sampled, and fresh adaptive cohorts; LigandMPNN + ESMFold adds two exploratory GPU pairs." },
  { layer: "Operational checkpoint", state: "available", detail: "Every completed MCMC step, cycling round, or rejection proposal batch is saved atomically with optimizer and RNG state." },
  { layer: "Eval-grade proposal traces", state: "available", detail: "Full-pool CUSTOM traces, ten LigandMPNN + ESMFold trajectories, and complete scaled Evo2 development and independent-audit trajectories exist locally." },
  { layer: "Frozen external audits", state: "available", detail: "CUSTOM sampled MFE passed its four-group audit; the joint LigandMPNN and scaled Evo2 artifacts failed their independent audit gates." },
  { layer: "Surrogate output + uncertainty", state: "partial", detail: "Paired reports aggregate predictions, coverage, routes, and fallbacks, but those records are not yet joined into one cross-workload proposal ledger." },
  { layer: "Route + defer reason", state: "available", detail: "The fresh CUSTOM confirmation recorded 3,844 surrogate routes and 156 exact routes; the Evo2 audit deferred all 192 proposals." },
  { layer: "Objective + paper provenance", state: "partial", detail: "CUSTOM establishes released-implementation parity, LigandMPNN is objective-matched, and Evo2 is explicitly a scaled rather than paper-length reproduction." },
] as const;

export const heldOutRows = [
  { cohort: "CUSTOM frozen audit", count: "4,000", coverage: "4 untouched full-pool groups · 99.075% coverage", verdict: "pass" },
  { cohort: "CUSTOM fresh confirmation", count: "4,000", coverage: "4 previously unopened paired seeds · exact top-10 recall", verdict: "pass" },
  { cohort: "Ligand joint development", count: "30", coverage: "6 trajectories · used for model selection", verdict: "thin" },
  { cohort: "Ligand joint external audit", count: "20", coverage: "4 hash- and group-disjoint trajectories", verdict: "fail" },
  { cohort: "Evo2 scaled development", count: "192", coverage: "1 trajectory · 32 dependent input-batch groups", verdict: "thin" },
  { cohort: "Evo2 independent audit", count: "192", coverage: "1 new seed · all proposals safely deferred", verdict: "fail" },
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
