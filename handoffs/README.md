# Reviewed learned-fusion reports

Phillip's generated programs follow `docs/PROGRAM_COLLECTION.md` and live under
`proto_programs/`; there is no separate manual
Phillip-to-Sai handoff bundle.

Sai may place a compact, reviewed report here:

```text
handoffs/
└── sai_to_phillip/<collection_id>/
    ├── summary.md
    ├── step_catalog.json
    ├── hotpaths.json
    ├── fusion_spec.json
    ├── risk_coverage.json
    ├── benchmark_report.json
    └── decision_record.md
```

Do not commit raw traces, teacher labels, confidential sequences, credentials, surrogate
weights, or model caches. Those belong under ignored `data/` paths.
