# Proto program collection and learned-fusion handoff

Phillip's handoff is a directory of generated Proto Python files. Sai analyzes those
programs to discover recurring expensive model-step groups. Protocol Buffers `.proto`
files are not involved.

## Phillip's generated collection

Write each collection to:

```text
proto_programs/generated/<collection_id>/
├── collection.json
├── design_001.py
├── design_002.py
└── inputs/
    └── example.json          # optional, synthetic or redistributable
```

The code generator—not Phillip manually—writes `collection.json`. It records:

- collection and program IDs;
- file hashes and `build_program` entry points;
- pinned Proto and registry versions;
- input roles and seed policy;
- source `MethodologySpec` IDs, never raw paper text;
- review and executable-safety status.

Each Python file must:

- expose `build_program()`;
- avoid execution, network calls, and model loading during import;
- use only allow-listed imports and reviewed registry symbols;
- use stable, readable local names;
- keep confidential sequences and credentials outside the file.

Synthetic collections suitable for tests live under `proto_programs/fixtures/`. Raw
inputs and execution outputs stay under ignored `data/` directories.

## Sai's analysis and learned-fusion outputs

Raw traces, training examples, calibration data, and surrogate weights live under
ignored `data/analysis/` and `data/models/`. A compact reviewed report may be placed in:

```text
handoffs/sai_to_phillip/<collection_id>/
├── summary.md
├── step_catalog.json
├── hotpaths.json
├── fusion_spec.json
├── risk_coverage.json
├── benchmark_report.json
└── decision_record.md
```

`fusion_spec.json` identifies the teacher step group, joint outputs, student inputs,
applicability domain, uncertainty estimators, deferral rules, full-model fallback, and
final-validation policy. `risk_coverage.json` reports coverage and selective risk at all
candidate gate thresholds rather than only one preferred operating point.

## Decision sequence

1. Review and freeze Phillip's generated program collection.
2. Profile the unchanged programs and rank recurring expensive step groups.
3. Jointly select one group and define decision-relevant outputs and error costs.
4. Train the fused surrogate on joint teacher traces.
5. Calibrate the abstention gate on held-out targets, scaffolds, or sequence families.
6. Compare full execution with selective surrogate execution using the same programs,
   inputs, seeds, and device class.
7. Accept, reject, or defer based on risk-coverage, top-k recall, false decisions,
   full-model calls avoided, wall time, and cost.
8. Run Phillip's end-to-end integration with fallback and final validation enabled.
