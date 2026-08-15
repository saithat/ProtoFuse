# Benchmark gate — resolved defaults (v1)

Joint decisions for Phillip/Sai benchmark infrastructure. **Do not change a row here
without resolving a query in [`INTERFACE_CONTRACT_QUERY.md`](INTERFACE_CONTRACT_QUERY.md)
with both partners.**

| # | Decision | v1 default | Resolved |
|---|----------|------------|----------|
| 1 | Measured profile | Add `profile_measured.json` alongside `profile.json` in `phillip_to_sai/` | 2026-08-15, `dnachisel-v1` |
| 2 | Decision 2 record | Sai updates `sai_to_phillip/.../decision_record.md`; Phillip writes `benchmark_report.json` | 2026-08-15, `dnachisel-v1` |
| 3 | Exactness | Invariants pass + eval count unchanged + scores within epsilon | 2026-08-15, `dnachisel-v1` |
| 4 | Candidate API | `build_candidate_program(...)` in `src/protofuse/sai/protocstage.py` | 2026-08-15, `dnachisel-v1` |
| 5 | Threshold authority | Sai owns `benchmark_plan.json`; Phillip reports ratios only | 2026-08-15, `dnachisel-v1` |
| 6 | Contracts | Untyped dicts in v1; typed models deferred | 2026-08-15, `dnachisel-v1` |
| 7 | Scenario lane | Phillip does not edit Sai's `v1/sai/` scenarios without query | 2026-08-15, `dnachisel-v1` |

Phillip never writes under `sai_to_phillip/`. Sai never overwrites Phillip's baseline graph files.

To propose a violation, use [`INTERFACE_CONTRACT_QUERY.md`](INTERFACE_CONTRACT_QUERY.md).
