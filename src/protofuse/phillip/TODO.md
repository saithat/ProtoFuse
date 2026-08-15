# Phillip TODO

Goal: own paper to executable Proto, save the resulting program folder for Sai, then run
the final workflow with Sai's learned fusion.

## Paper to programs

- [ ] Finish Paperclip/local-text ingestion with evidence and `unknowns`.
- [ ] Keep a reviewed registry of allowed Proto components and typed parameters.
- [ ] Generate `proto_programs/generated/<collection_id>/design_*.py` from a reviewed
      `MethodologySpec`.
- [ ] Make every file readable, inert on import, and expose `build_program()`.
- [ ] Generate the small `collection.json` manifest and validate its hashes.
- [ ] Refuse generation or execution while any binding is unresolved.

## Handoff and final E2E

- [ ] Freeze a collection and give Sai its path; do not create a separate graph/profile
      handoff.
- [ ] Review Sai's measured fusion target and decision-relevant outputs.
- [ ] Call Sai's single selective-fusion API from the final E2E pipeline.
- [ ] Compare identical inputs/seeds for the full and selective paths.
- [ ] Verify deferrals run the full model and final candidates receive the agreed full
      validation.

## Joint decisions

- [ ] Methodology review.
- [ ] Collection freeze.
- [ ] Fusion target, outputs, thresholds, and asymmetric error costs.
- [ ] Final risk/coverage operating point and accept/reject decision.
