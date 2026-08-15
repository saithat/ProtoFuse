# Phillip benchmark plan (solo E2E)

Runbook for Phillip-owned baseline profiling and per-proto-step benchmarks **before**
the formal Decision 2 gate with Sai. Follow this plan at **Check-in 2**; defer joint
accept/reject until touch-base (see [Touch-base later](#touch-base-later)).

Related: [`AGENTS.md`](AGENTS.md) (lane boundaries), [`docs/GRAPH_HANDOFF.md`](../../docs/GRAPH_HANDOFF.md)
(artifact shapes), [`docs/BENCHMARK_DECISIONS.md`](../../docs/BENCHMARK_DECISIONS.md) (joint defaults).

---

## Goal

1. Run each pipeline **end to end** on a small representative workload.
2. Save **measured** timing and call counts **per stable graph node** (proto step).
3. Keep raw traces gitignored; commit only compact summaries when useful for Sai review.
4. **Do not** cross Sai's lane or edit `src/protofuse/sai/` until touch-base.

---

## Pipelines and decision IDs

| Pipeline | Scenario ID | Decision ID | Role |
|----------|-------------|-------------|------|
| 1 — baseline toy DNA | `balanced-gc` | *(optional — regression only)* | Sanity check; no Sai optimization handoff |
| 2 — DNA Chisel paper | `dnachisel-gc-optimization` | `dnachisel-v1` | Primary profiling target for Sai hot-path work |

Catalog: [`philip-sai-integrations/v1/catalog.json`](../../philip-sai-integrations/v1/catalog.json).

---

## When to run this plan

| Check-in | Use this plan? | Action |
|----------|----------------|--------|
| **0 — methodology** | No | Approve `MethodologySpec` with Sai first |
| **1 — graph freeze** | No | Freeze `graph.json` / `workload.json` in `phillip_to_sai/` |
| **2 — baseline profile** | **Yes — start here** | Run solo baseline E2E; write `profile_measured.json` |
| **Decision 1** | Read-only | Review Sai's `benchmark_plan.json`; do not change it |
| **Decision 2** | Defer | Formal `benchmark compare` + Sai `decision_record.md` at touch-base |
| **3 — integration** | After Decision 2 | Full E2E with accepted candidate graph |

---

## Artifact layout

### Gitignored — raw measurements (Phillip writes)

```text
data/runs/<decision_id>/
├── run_manifest.json
└── baseline/<run_id>/
    ├── run_config.json
    ├── trace.json          # per-node wall time, calls, cache stats
    ├── invariants.json
    └── quality.json
```

Optional later (after Sai returns a patch):

```text
data/runs/<decision_id>/candidate/<run_id>/...
```

### Committed — compact handoff (Phillip writes, additive only)

```text
philip-sai-workflow-dump/phillip_to_sai/<decision_id>/
├── graph.json              # existing — do not overwrite without query
├── workload.json
├── profile.json            # estimates — keep if Sai already ranked on these
├── profile_measured.json   # NEW — measured aggregate per node
├── benchmark_summary.md    # optional notes for yourself / Sai preview
└── benchmark_report.json   # optional — exploratory only until Decision 2
```

**Do not write:** `philip-sai-workflow-dump/sai_to_phillip/` (Sai's lane).

---

## Per-proto-step metrics to capture

For every stable `node_id` in `graph.json`, each baseline run should record:

| Field | Source |
|-------|--------|
| `calls` | Constraint/generator invocations in trace |
| `duration_ms_total` / `duration_ms_mean` | Measured wall time (allocated by step count today) |
| `cache_hits` / `cache_misses` | When instrumentation adds them |
| `quality_contribution` | From constraint scores / invariants |
| `measurement` | Always `"measured"` in `profile_measured.json` |

Headline bottleneck: node with highest `duration_ms_total` (also in trace aggregate).

Scientific checks on every run:

- invariants pass (`invariants.json`)
- constraint evaluation count (sum of constraint node `calls`)
- final constraint scores (for later exactness compare)

---

## Step-by-step workflow

### 1. Prerequisites (Check-in 1 done)

- Handoff bundle exists under `philip-sai-workflow-dump/phillip_to_sai/<decision_id>/`.
- `graph.json` and `workload.json` frozen; node IDs stable.
- Scenario registered and valid:

```bash
uv run protofuse integrations validate
```

### 2. Measured baseline run (Check-in 2)

Default for `dnachisel-v1`:

```bash
uv run protofuse benchmark baseline \
  --decision-id dnachisel-v1 \
  --scenario dnachisel-gc-optimization \
  --seed 0 \
  --repetitions 3 \
  --device local
```

This:

- builds the baseline program from the scenario + handoff graph
- runs E2E and writes per-run traces under `data/runs/dnachisel-v1/baseline/`
- aggregates into `philip_to_sai/dnachisel-v1/profile_measured.json`

**Solo defaults** (you may use these without Sai):

| Setting | Value | Notes |
|---------|-------|-------|
| `seed` | `0` | Match handoff workload when possible |
| `repetitions` | `3` | Median across runs for stability |
| `device` | `local` | Modal later if needed |
| `variant` | `baseline` only | Skip candidate until touch-base |

### 3. Inspect per-step results

After baseline:

```bash
# Latest trace (gitignored)
ls data/runs/dnachisel-v1/baseline/
cat data/runs/dnachisel-v1/baseline/<run_id>/trace.json

# Committed aggregate
cat philip-sai-workflow-dump/phillip_to_sai/dnachisel-v1/profile_measured.json
```

Rank hot paths locally by `duration_ms_total`. Note the top node ID in
`benchmark_summary.md` if Sai has not picked a target yet.

### 4. Optional regression — Pipeline 1

```bash
uv run protofuse benchmark baseline \
  --decision-id balanced-gc-smoke \
  --scenario balanced-gc \
  --seed 0 \
  --repetitions 1
```

Use a separate `decision_id` so traces do not mix with `dnachisel-v1`.

### 5. Stop here (solo mode)

Do **not** run `benchmark compare` or `benchmark candidate` until touch-base unless
Sai has approved Decision 1 and you both want a formal gate dry-run.

Exploratory compare output is **not** a Decision 2 outcome.

---

## Touch-base later

When Phillip and Sai sync, resolve together:

1. **Check-in 2 sign-off** — Is `profile_measured.json` enough for hot-path ranking?
2. **Decision 1** — Accept Sai's `prepared_module_plan.json` / `graph_patch.json` /
   `benchmark_plan.json`.
3. **Decision 2** — Run formal compare:

```bash
uv run protofuse benchmark compare \
  --decision-id dnachisel-v1 \
  --scenario dnachisel-gc-optimization
```

Sai updates `sai_to_phillip/dnachisel-v1/decision_record.md` (accept / reject / defer).

4. **ProtoStage scope** — Is `build_candidate_program()` v1 sufficient?
5. **Q1–Q7** — Confirm defaults in [`docs/BENCHMARK_DECISIONS.md`](../../docs/BENCHMARK_DECISIONS.md)
   or open a query in [`docs/INTERFACE_CONTRACT_QUERY.md`](../../docs/INTERFACE_CONTRACT_QUERY.md).

---

## Lane rules (reminder)

| Phillip may | Phillip must not |
|-------------|------------------|
| Write `data/runs/` | Write `sai_to_phillip/` |
| Add `profile_measured.json`, summaries under `phillip_to_sai/` | Edit `benchmark_plan.json` or `decision_record.md` |
| Call `build_candidate_program()` only during formal compare | Edit `src/protofuse/sai/` |
| Propose threshold changes via PR or interface query | Edit `philip-sai-integrations/v1/sai/` scenarios |

---

## Pre-push checklist

```bash
uv run ruff check .
uv run pytest
uv run protofuse integrations validate
```

Commit only compact handoff files; never commit `data/runs/` or paper text.
