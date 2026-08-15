# Sai workspace

Use this directory for Sai's disposable marimo notebooks and ProtoStage experiments.
Promote stable, tested code into `src/protofuse/sai/`; do not commit large runs here.

**Interface contract with Phillip:** [`docs/INTERFACE_CONTRACT_QUERY.md`](../../docs/INTERFACE_CONTRACT_QUERY.md)
— answer the baseline Q1–Q7 with Phillip before changing handoff boundaries. Resolved
defaults: [`docs/BENCHMARK_DECISIONS.md`](../../docs/BENCHMARK_DECISIONS.md).

Sai writes `sai_to_phillip/<decision_id>/` and owns `build_candidate_program()` in
`src/protofuse/sai/protocstage.py`. Phillip writes measured benchmarks to
`phillip_to_sai/<decision_id>/` and `data/runs/` only.
