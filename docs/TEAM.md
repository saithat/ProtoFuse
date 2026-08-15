# Phillip and Sai work split

## Shared repository

Both people work in ProtoFuse and may push small commits directly to `main`. Keep CI
enabled, pull with rebase before pushing, and never force-push or rewrite `main` history.
Coordinate before changing `MethodologySpec`, the generated-program collection contract,
or the learned-fusion output contract.

## Shared scientific agent

Both Phillip and Sai work in `src/protofuse/scientific_agent/` and jointly own:

- evidence-grounded methodology extraction;
- prompt and schema evaluation;
- Paperclip or local-paper adapters;
- synthetic or redistributable extraction fixtures.

## Phillip: paper to Proto program collection

Primary directory: `src/protofuse/phillip/`

- Ingest a paper and produce a validated `MethodologySpec`.
- Bind component requests through a reviewed Proto registry.
- Generate a collection folder containing one or more readable Proto `.py` designs.
- Automatically write and validate the collection manifest.
- Smoke-test every reviewed program against pinned Proto.

Phillip does not need to produce Sai's step catalog, runtime profile, fusion plan,
training dataset, or surrogate report.

## Sai: learned fusion

Primary directory: `src/protofuse/sai/`

- Scan Phillip's generated Proto program collections.
- Catalog recurring model-step groups across programs.
- Profile their runtime, frequency, cost, reuse, and effect on optimizer decisions.
- Select one common expensive group such as Boltz plus downstream scoring models.
- Train a joint surrogate for the selected full-step outputs.
- Calibrate an applicability and uncertainty gate that defers unsafe cases to the full
  models.
- Measure risk versus coverage, full-model calls avoided, scientific decision quality,
  runtime, and cost.

## Integration habit

For each learned-fusion experiment:

1. Phillip freezes one generated program collection.
2. Sai profiles the original programs and selects one recurring expensive step group.
3. Both approve the group inputs, outputs, scientific thresholds, and asymmetric error
   costs before training.
4. Sai trains only on joint full-model traces from that group.
5. Sai calibrates the deferral policy on held-out targets, scaffolds, or families.
6. Both review the risk-coverage and cost curves.
7. Phillip runs the accepted selective surrogate through the end-to-end pipeline with
   full-model fallback enabled.
