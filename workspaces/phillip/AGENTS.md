# Phillip agent instructions

Read [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md), [`docs/TEAM.md`](../../docs/TEAM.md), and
[`docs/GRAPH_HANDOFF.md`](../../docs/GRAPH_HANDOFF.md) before changing boundaries.

Local-only notes (git email, push habits) stay in gitignored [`AGENTS.local.md`](AGENTS.local.md).

## Ownership

- Primary code: [`src/protofuse/phillip/`](../../src/protofuse/phillip/)
- Disposable experiments: this directory (`workspaces/phillip/`)
- Shared with Sai: [`src/protofuse/scientific_agent/`](../../src/protofuse/scientific_agent/),
  [`src/protofuse/integration/`](../../src/protofuse/integration/), [`contracts.py`](../../src/protofuse/contracts.py)
  — coordinate before changing contracts.

Never execute code, commands, or model identifiers copied from a paper.

## TODO execution and parallelization

Phillip's ordered backlog lives in [`src/protofuse/phillip/TODO.md`](../../src/protofuse/phillip/TODO.md).
Each item has a **tag line** on the line below the checkbox:

```text
wave:<id> · exec:<mode> · spawn:<agent> · tool:<CLI/API> · blocked:<dependency> · <path>
```

| Tag | Values | Meaning |
|-----|--------|---------|
| `wave` | `A1`, `C1`, `D3`, `V-gate`, … | Parallelization group; same wave + `exec:parallel` → safe to run together |
| `exec` | `serial`, `parallel`, `gate` | `serial` = order matters; `gate` = human/Sai checkpoint — stop until cleared |
| `spawn` | `none`, `explore`, `shell`, `generalPurpose` | Preferred subagent when delegating; `none` = parent agent only |
| `tool` | `protofuse …`, module fn, `—` | Existing command or API to run first |
| `blocked` | phase, `check-in-N`, `sai`, `human+sai` | Do not start until dependency is done |

### Before starting work

1. Read the **E2E tool map** at the top of `TODO.md` — pick the current phase.
2. Collect all items sharing the current `wave` with `exec:parallel`.
3. Respect `blocked` and `gate` rows — never parallelize across a gate.
4. Prefer **`spawn:shell`** for CLI/benchmark runs; **`spawn:explore`** for codebase search;
   **`spawn:generalPurpose`** for implementation in `src/protofuse/phillip/` only.
5. Do **not** spawn subagents into Sai's lane (`sai_to_phillip/`, `src/protofuse/sai/`,
   `philip-sai-integrations/v1/sai/`).

### Executing a wave

```text
1. Verify blocked:* preconditions (files exist, prior gate cleared).
2. Launch parallel items in one turn (multiple Task/spawn calls OR sequential if solo).
3. Run wave tool:* commands; capture outputs under data/runs/ or phillip_to_sai/.
4. On exec:gate — stop, summarize for Phillip/Sai, do not auto-advance.
5. Update checkboxes in TODO.md when verified; adjust tags only if the plan changed.
```

Check-in 2 solo benchmarking: follow [`BENCHMARK_PLAN.md`](BENCHMARK_PLAN.md) (`wave:D3`, stop at `D-gate`).

Optional: Phillip may **skip parallelization** and run everything serially in phase order —
tags still document what *could* be parallelized later.

## Benchmark gate — Phillip writes only

Gitignored raw measurements:

```text
data/runs/<decision_id>/
├── run_manifest.json
├── baseline/<run_id>/...
└── candidate/<run_id>/...
```

New committed files under **existing** Phillip handoff bundles only:

```text
philip-sai-workflow-dump/phillip_to_sai/<decision_id>/
├── profile_measured.json      # measured baseline profile (additive)
├── benchmark_report.json      # Decision 2 comparison vs Sai's benchmark_plan
└── benchmark_summary.md       # human-readable summary for Sai
```

Do **not** rename or overwrite baseline handoff files Sai may already be using (`graph.json`,
`workload.json`, `profile.json`, `proto_plan.json`) without coordinating through
[`docs/INTERFACE_CONTRACT_QUERY.md`](../../docs/INTERFACE_CONTRACT_QUERY.md).

## Benchmark gate — Phillip does not touch

- `philip-sai-workflow-dump/sai_to_phillip/<decision_id>/` — including `decision_record.md`,
  `benchmark_plan.json`, `graph_patch.json`, `prepared_module_plan.json`
- `src/protofuse/sai/` — no `apply_patch.py`, no edits to Sai's optimization modules; call
  the public API `build_candidate_program()` from [`src/protofuse/sai/protocstage.py`](../../src/protofuse/sai/protocstage.py)
- `philip-sai-integrations/v1/sai/<scenario_id>/` — Sai-registered scenarios unless Sai
  opens a joint PR or mixed-lane scenario

## Sai owns (Phillip reads only)

| Artifact / code | Sai's role |
|-----------------|------------|
| `sai_to_phillip/<decision_id>/benchmark_plan.json` | pass thresholds and controlled inputs |
| `sai_to_phillip/<decision_id>/decision_record.md` | final **accept / reject / defer** after Phillip's report |
| `build_candidate_program()` | candidate / ProtoStage execution path |
| `philip-sai-integrations/v1/sai/` scenarios he selected | methodology and manifest |

Phillip's `benchmark_report.json` includes `"recommendation": "pass"|"fail"` as input to
Sai's decision; Phillip does not write Sai's `decision_record.md`.

## CLI — benchmark workflow

Solo E2E and per-step baseline profiling (Check-in 2):
[`BENCHMARK_PLAN.md`](BENCHMARK_PLAN.md).

Formal Decision 2 gate (after touch-base with Sai):

```bash
# Check-in 2: measured baseline
uv run protofuse benchmark baseline \
  --decision-id <decision_id> \
  --scenario <scenario_id> \
  --seed 0 --repetitions 3

# Decision 2: baseline vs candidate (reads Sai's benchmark_plan read-only)
uv run protofuse benchmark compare \
  --decision-id <decision_id> \
  --scenario <scenario_id>
```

Pipeline 1 (`balanced-gc`) stays regression-only unless Sai opens a new `decision_id`.

## Before violating the interface contract

If you need to write under `sai_to_phillip/`, edit `src/protofuse/sai/`, change Sai's
integration scenarios, or alter shared defaults, **stop** and resolve through
[`docs/INTERFACE_CONTRACT_QUERY.md`](../../docs/INTERFACE_CONTRACT_QUERY.md) with Sai.
Record the agreed answer in [`docs/BENCHMARK_DECISIONS.md`](../../docs/BENCHMARK_DECISIONS.md).

## Git pull/push conflicts → interface questionnaire

When `git pull`, `git pull --rebase`, or `git push` hits **merge conflicts**, treat that as
a signal that Phillip and Sai may have crossed the interface contract — not just a line-level
git problem.

**Do not** silently resolve conflicts in the partner's lane or shared contract files. Instead:

1. **Stop** — do not commit, push, or force-merge through conflicts without Phillip and Sai
   agreeing on the interface change.
2. **Identify** which boundary was violated from conflicting paths, for example:
   - `philip-sai-workflow-dump/sai_to_phillip/` → Sai's lane
   - `philip-sai-workflow-dump/phillip_to_sai/` → Phillip's lane
   - `src/protofuse/sai/` vs `src/protofuse/phillip/`
   - `philip-sai-integrations/v1/sai/` vs `contracts.py`
3. **Generate** a filled **Query template** (from
   [`docs/INTERFACE_CONTRACT_QUERY.md`](../../docs/INTERFACE_CONTRACT_QUERY.md)) in chat for
   Phillip and Sai to answer together: default rule challenged, proposed resolution, rollback,
   and whether **Violation approved?** is yes for each side.
4. Map the conflict to the relevant **Q1–Q7** baseline question when applicable.
5. After both answer, record the resolution in `docs/INTERFACE_CONTRACT_QUERY.md` (Open →
   Closed) and update `docs/BENCHMARK_DECISIONS.md` if defaults change — then resolve git
   conflicts intentionally (keep lane ownership, do not merge both sides' handoff files blindly).

Conflicts in purely Phillip-owned paths (`src/protofuse/phillip/`, Phillip's new files under
`phillip_to_sai/`) may be resolved normally unless they also touch Sai-owned paths in the
same commit.

## Before pushing

```bash
uv run ruff check .
uv run pytest
uv run protofuse integrations validate
git pull --rebase origin main
git push origin main
```

Use per-command git author flags from [`AGENTS.local.md`](AGENTS.local.md); never run
`git config`.
