# Philip–Sai workflow dump (`philip-sai-workflow-dump/`)

Use these directories for compact, reviewed, non-sensitive workflow and graph handoff
artifacts following `docs/GRAPH_HANDOFF.md`.

```text
philip-sai-workflow-dump/
├── phillip_to_sai/<decision_id>/
│   ├── summary.md
│   ├── proto_plan.json
│   ├── graph.json
│   ├── workload.json
│   ├── profile.json
│   ├── profile_measured.json     # optional: Phillip measured baseline profile
│   ├── benchmark_report.json     # optional: Phillip Decision 2 comparison
│   ├── benchmark_summary.md      # optional: Phillip human-readable summary
│   └── decision_request.md
└── sai_to_phillip/<decision_id>/
    ├── summary.md
    ├── prepared_module_plan.json
    ├── graph_patch.json
    ├── benchmark_plan.json
    └── decision_record.md
```

Do not copy raw traces or full generated runs here. Those belong under ignored
`data/runs/`. Before committing a bundle, remove paper text, sequences, credentials,
model artifacts, and any other confidential or large payload.

Phillip's bundle describes the scientific graph and reuse workload. Sai's response
describes the proposed prepared state, the residual computation, its invalidation and
fallback behavior, and the controlled benchmark gate. Keep field names stable, units
explicit, and measured, estimated, and unknown values distinguishable.

**Interface contract:** default write boundaries and a shared Q&A to resolve violations
are in [`docs/INTERFACE_CONTRACT_QUERY.md`](../docs/INTERFACE_CONTRACT_QUERY.md).
Phillip may append `profile_measured.json`, `benchmark_report.json`, and
`benchmark_summary.md` under `phillip_to_sai/<decision_id>/` only. Sai owns everything
under `sai_to_phillip/<decision_id>/`.
