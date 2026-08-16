# Portable evaluation report

`protofuse-evaluation.html` is a self-contained, interactive snapshot of the aggregate evidence
available when it was generated. It explains the motivation, shows the observed full-path and
surrogate results, and turns missing evidence into an explicit measurement plan. Open it directly
in a browser; its tabs and expandable evidence use only embedded JavaScript. It has no external
fonts, scripts, stylesheets, hosted APIs, authentication, or ChatGPT dependency.

The versioned paired-evaluation JSON emitted by `protofuse fusion evaluate --out ...` is the
canonical scientific result. This HTML file is only its presentation layer and may also contain
legacy aggregate inputs until the report generator is updated to ingest a paired result directly.

Regenerate it after copying result artifacts into the ignored data directories:

```bash
python3 scripts/build_visualization_bundle.py --strict
python3 scripts/build_evaluation_report.py
```

Expected inputs:

- `data/analysis/modal_smoke_summary.json`;
- `data/analysis/custom-egfp-lung/surrogate_pilot_report.json`;
- optional `data/analysis/other_examples_audit.json`;
- optional checkpoint runs under `data/runs/checkpoints/<run>/<tier>/`;
- the tracked curated bundle under `data/visualizations/`;
- reviewed methodology files under `workspaces/phillip/fixtures/*/methodology.json`.

Use `--strict` when the primary Modal and pilot summaries must both be present. Alternate
locations can be supplied with `--analysis-dir`, `--checkpoint-dir`, and `--output`.

Only aggregate fields and reviewed final-candidate visualization records are copied into the
report. Curated final sequences are embedded for inspection; proposal pools, raw teacher outputs,
credentials, model caches, and provider failure payloads remain excluded. Each input receives a
SHA-256 provenance record. The normalized report data is also embedded as JSON under the
`protofuse-report-data` element for downstream parsing.

The surrogate model card reports the metrics present in the pilot artifact: calibration and
audit MAE/max error, trajectory error and support coverage, OOD challenge outcomes, speedup,
and final-design agreement. Metrics that are not present or are not meaningful for the current
regression pilot—such as a training-loss curve or classification accuracy—are labeled explicitly.

The evidence appendix also explains the split unit. One seeded optimizer trajectory can emit many
correlated proposal rows, but all of them remain in one train, calibration, or test group. It shows
the preferred 60/20/20 trajectory collection target separately from raw proposal-sample counts.
