# Reviewed graph handoffs

Use these directories for compact, reviewed, non-sensitive decision artifacts following
`docs/GRAPH_HANDOFF.md`.

```text
handoffs/
├── phillip_to_sai/<decision_id>/
│   ├── summary.md
│   ├── proto_plan.json
│   ├── graph.json
│   ├── workload.json
│   ├── profile.json
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
