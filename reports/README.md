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

## 16:9 slide deck (Google Slides)

`protofuse-evaluation-slides.html` is a widescreen slide deck generated from the same
aggregate data as the scroll report. Every frame is exactly **1920×1080** (16:9) with the
same gentle gray grid borders (`#d7d4cb`) used in the portable report.

Generate it after the visualization bundle and primary analysis artifacts are present:

```bash
python3 scripts/build_visualization_bundle.py --strict
python3 scripts/build_evaluation_report.py --strict --slides
```

Open `reports/protofuse-evaluation-slides.html` in a browser. Each `.slide` block is a
self-contained frame — snapshot it (screenshot or copy-as-image) and paste into Google Slides.
Use **Page setup → Widescreen 16:9** in Google Slides so pasted images align with the default canvas.

The `--slides` flag writes only the deck HTML (default:
`reports/protofuse-evaluation-slides.html`). Omit `--slides` to regenerate the scroll report
instead. Both share the same `--strict`, `--repo-root`, `--analysis-dir`, and `--output` options.

## 16:9 slide deck PDF

Export the same widescreen frames as a multi-page PDF (one 16:9 page per slide):

```bash
uv sync --extra pdf
playwright install chromium
python3 scripts/build_evaluation_report.py --strict --pdf
```

Default output: `reports/protofuse-evaluation-slides.pdf`.

Combine flags to write HTML and PDF together:

```bash
python3 scripts/build_evaluation_report.py --strict --slides --pdf
```

When both `--slides` and `--pdf` are set, `--output` applies to the format matching its extension
(`.html` or `.pdf`); the other format uses its default path.

## 16:9 slide deck PowerPoint

Export the same widescreen frames as a `.pptx` file for upload to Google Drive:

```bash
uv sync --extra pdf
playwright install chromium
python3 scripts/build_evaluation_report.py --strict --pptx
```

Default output: `reports/protofuse-evaluation-slides.pptx`. Upload to Drive and open with Google Slides.

Combine slide export flags as needed:

```bash
python3 scripts/build_evaluation_report.py --strict --slides --pdf --pptx
```

When multiple slide export flags are set, `--output` applies to the format matching its extension
(`.html`, `.pdf`, or `.pptx`); the other formats use their default paths.
