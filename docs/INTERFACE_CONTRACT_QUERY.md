# Interface contract query (Phillip ↔ Sai)

Use this document when either partner needs to **change, override, or violate** the default
handoff boundary. Treat it as a shared query at the interface contract: one person proposes,
both answer, you record the resolution before merging code or committing handoff files.

Related: [`docs/BENCHMARK_DECISIONS.md`](BENCHMARK_DECISIONS.md) (resolved defaults),
[`docs/GRAPH_HANDOFF.md`](GRAPH_HANDOFF.md) (artifact shapes),
[`philip-sai-workflow-dump/README.md`](../philip-sai-workflow-dump/README.md) (two lanes).

## Default contract (do not violate without resolution)

### Phillip writes

| Location | Files |
|----------|--------|
| `data/runs/<decision_id>/` (gitignored) | `run_manifest.json`, `baseline/`, `candidate/` run artifacts |
| `philip-sai-workflow-dump/phillip_to_sai/<decision_id>/` | **New only:** `profile_measured.json`, `benchmark_report.json`, `benchmark_summary.md` plus existing baseline handoff files |

### Phillip does not touch

- `philip-sai-workflow-dump/sai_to_phillip/<decision_id>/`
- `src/protofuse/sai/` (call `build_candidate_program()` only)
- `philip-sai-integrations/v1/sai/<scenario_id>/` (Sai-registered scenarios)

### Sai writes

| Location | Files |
|----------|--------|
| `philip-sai-workflow-dump/sai_to_phillip/<decision_id>/` | `benchmark_plan.json`, `graph_patch.json`, `prepared_module_plan.json`, `decision_record.md`, … |
| `src/protofuse/sai/` | `build_candidate_program()`, ProtoStage logic |
| `philip-sai-integrations/v1/sai/` | scenarios Sai selects |

### Sai does not touch

- Phillip's baseline `graph.json`, `workload.json`, `profile.json` in `phillip_to_sai/`
- `data/runs/` (Phillip's raw traces)
- `src/protofuse/phillip/` without coordination

---

## How to use this query

1. Copy the **Query template** below into a new subsection under **Open queries**, or discuss
   in chat and then record answers here.
2. Each person fills **Phillip** and **Sai** columns (or `agree` / `defer` / `reject`).
3. If the answer **violates the default contract**, both must check **Violation approved**
   and give a one-line rollback plan.
4. When resolved, move the summary to [`docs/BENCHMARK_DECISIONS.md`](BENCHMARK_DECISIONS.md)
   and close the open query.

**Git conflicts:** If `git pull` or `git push` surfaces merge conflicts — especially under
`philip-sai-workflow-dump/`, `src/protofuse/sai/`, `src/protofuse/phillip/`, or
`philip-sai-integrations/` — Phillip's agent should generate a Query from the template
below (prefilled with conflicting paths) for both partners to answer before resolving git.
See [`workspaces/phillip/AGENTS.md`](../workspaces/phillip/AGENTS.md).

---

## Baseline decisions — answer together once per integration version

Fill these before first `protofuse benchmark compare` for a new `decision_id`, or when
reopening a gate after a material change.

### Q1 — Measured profile location

**Question:** After a measured baseline run, where does the aggregate profile live?

| | |
|---|---|
| **Default (recommended)** | Add `profile_measured.json` alongside existing `profile.json` in `phillip_to_sai/<decision_id>/`. Keep original `profile.json` if Sai already ranked on estimates. |
| **Phillip** | |
| **Sai** | |
| **Resolved** | ☐ pending · ☐ yes, use default · ☐ other: ___ |
| **Violation approved?** | ☐ N/A · ☐ yes — describe: ___ |

---

### Q2 — Decision 2 outcome record

**Question:** Who writes the final accept / reject / defer for Decision 2?

| | |
|---|---|
| **Default (recommended)** | Sai updates `sai_to_phillip/<decision_id>/decision_record.md`. Phillip writes `benchmark_report.json` + `benchmark_summary.md` in `phillip_to_sai/` only. |
| **Phillip** | |
| **Sai** | |
| **Resolved** | ☐ pending · ☐ yes, use default · ☐ other: ___ |
| **Violation approved?** | ☐ N/A · ☐ yes — describe: ___ |

---

### Q3 — Exactness gate

**Question:** What must match between baseline and candidate for the benchmark to pass?

| | |
|---|---|
| **Default (recommended)** | All of: (a) scientific invariants pass on both, (b) constraint evaluation count unchanged, (c) final constraint scores within epsilon for same seed. Sequences may differ if scores tie. |
| **Phillip** | |
| **Sai** | |
| **Resolved** | ☐ pending · ☐ yes, use default · ☐ other: ___ |
| **Violation approved?** | ☐ N/A · ☐ yes — describe: ___ |

---

### Q4 — Candidate API boundary

**Question:** How does Phillip run the candidate path without editing Sai's code?

| | |
|---|---|
| **Default (recommended)** | Phillip calls `build_candidate_program(baseline_program, decision_id=..., handoff_root=...)` from `src/protofuse/sai/protocstage.py`. Implementation stays in `src/protofuse/sai/`. Experimental code may live in `workspaces/sai/` until Sai promotes it. |
| **Phillip** | |
| **Sai** | |
| **Resolved** | ☐ pending · ☐ yes, use default · ☐ other: ___ |
| **Violation approved?** | ☐ N/A · ☐ yes — describe: ___ |

---

### Q5 — Pass threshold authority

**Question:** Who sets pass/fail thresholds, and can Phillip change them in-repo?

| | |
|---|---|
| **Default (recommended)** | Sai owns `sai_to_phillip/.../benchmark_plan.json`. Phillip runs compare read-only and reports measured ratios in `benchmark_report.json`. Phillip proposes threshold changes only via PR to Sai's lane or a new query here. |
| **Phillip** | |
| **Sai** | |
| **Resolved** | ☐ pending · ☐ yes, use default · ☐ other: ___ |
| **Violation approved?** | ☐ N/A · ☐ yes — describe: ___ |

---

### Q6 — Shared schema (`contracts.py`)

**Question:** Do benchmark artifacts use typed Pydantic models in `contracts.py`?

| | |
|---|---|
| **Default (recommended)** | v1 uses untyped dicts in benchmark JSON files. Add `BenchmarkReport` / `RunTrace` to `contracts.py` only after both approve (impacts both tracks). |
| **Phillip** | |
| **Sai** | |
| **Resolved** | ☐ pending · ☐ yes, use default · ☐ other: ___ |
| **Violation approved?** | ☐ N/A · ☐ yes — describe: ___ |

---

### Q7 — Scenario lane edits

**Question:** Can Phillip edit `philip-sai-integrations/v1/sai/<scenario_id>/` for a pipeline Sai registered?

| | |
|---|---|
| **Default (recommended)** | No — use `v1/mixed/` or `v1/contributed/` for Phillip-led changes, or Sai merges manifest/methodology updates. |
| **Phillip** | |
| **Sai** | |
| **Resolved** | ☐ pending · ☐ yes, use default · ☐ other: ___ |
| **Violation approved?** | ☐ N/A · ☐ yes — describe: ___ |

---

## Query template (copy for ad-hoc violations)

```markdown
### Query: <short title> — <decision_id or scenario_id>

**Date:** YYYY-MM-DD  
**Raised by:** Phillip | Sai  
**Default rule being challenged:** (quote from Default contract above)

**Question:** One sentence.

| | |
|---|---|
| **Proposed change** | |
| **Why needed** | |
| **Rollback if wrong** | |
| **Phillip** | agree / reject / defer — notes: |
| **Sai** | agree / reject / defer — notes: |
| **Resolved** | ☐ pending · ☐ closed |
| **Violation approved?** | ☐ no · ☐ yes |
| **Recorded in BENCHMARK_DECISIONS.md** | ☐ |
```

---

## Open queries

*(None — add ad-hoc queries above this line.)*

---

## Closed queries

### `dnachisel-v1` baseline gate — 2026-08-15

**Resolved:** Q1–Q7 use all defaults from this document. Recorded in
[`docs/BENCHMARK_DECISIONS.md`](BENCHMARK_DECISIONS.md). No contract violations.
