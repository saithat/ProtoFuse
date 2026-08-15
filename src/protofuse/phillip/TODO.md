# Phillip TODO

Goal: own paper to ordinary executable Proto, provide a frozen program collection to Sai,
and validate accepted automatic fusions end to end.

## Paper to programs

- [ ] Finish Paperclip/local-text ingestion with evidence and `unknowns`.
- [ ] Maintain a reviewed registry of allowed Proto components and typed parameters.
- [ ] Generate readable `design_*.py` from a reviewed `MethodologySpec`.
- [ ] Refuse source generation or execution while any binding is unresolved.
- [ ] Validate allow-listed imports and confirm generated modules are inert on import.

## Program collection

- [x] Finalize `design_*.py` files without importing them.
- [x] Generate `collection.json` with stable metadata and SHA-256 hashes.
- [x] Validate collection paths, review status, uniqueness, and hashes.
- [ ] Freeze a real generated collection and give Sai only its path/ID.

## Final E2E

- [ ] Review Sai's measured fusion target and decision-relevant outputs.
- [ ] Run the ordinary program through `protofuse.optimize()` with Sai's registered bundle.
- [ ] Compare identical inputs, seeds, versions, and hardware for original and selective
      paths.
- [ ] Confirm deferrals invoke the full model and final candidates receive the agreed
      authoritative validation.

## Joint decisions

- [ ] Methodology behavior.
- [ ] Collection freeze.
- [ ] Fusion target, outputs, applicability domain, thresholds, and error costs.
- [ ] Risk/coverage operating point and final accept/reject decision.
