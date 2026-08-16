# Phillip handoff scope

Phillip's only deliverable to Sai is a **frozen program collection**:

```text
proto_programs/generated/<collection_id>/
├── collection.json
└── design_*.py
```

Commit that folder to `main`, then tell Sai the **collection ID** (the folder name).

## Phillip owns

- Paper → `MethodologySpec` (internal; not the handoff).
- Readable `design_*.py` with one synchronous `build_program()` per file.
- Numeric suffixes such as `_001` and `_002` are stable ordinal IDs, not tier labels. In
  the common two-file profile, `_001` is full and `_002` is smoke, but multi-design
  profiles may have several full programs. State the tier in each module's docstring and
  `build_program()` call; never rely on the suffix alone.
- No execution, network, or model loading on import.
- `finalize_collection(..., reviewed=True)` after manually reading the generated source.
- Pinning metadata in `collection.json`: methodology ID, Proto version, registry version,
  seed policy.

## Phillip does not own

Do not block on or pre-decide any of the following — Sai owns them:

- Which step groups to fuse.
- Final outputs, metrics, or acceptance criteria for a fusion.
- Error rates, uncertainty thresholds, or fallback policy.
- Surrogate training, calibration, and bundle registration.

Prior workflow artifacts (graph dumps, benchmark bundles, scenario catalogs,
`sai_to_phillip/` folders) are obsolete. Do not recreate them.

## Handoff checklist

0. **Preflight** — validate binding at paper target length before generating or scaling:
   - `uv run protofuse preflight <fixture_id> --length <paper_bp>`
   - If infeasible at paper length: document reduced scope in the fixture README with
     preflight evidence; do not silently shrink `segment_length_bp` without explanation.
   - Confirm `pytest tests/test_workload_preflight.py` passes (smoke output-length invariant).
   - See [`WORKLOAD_VALIDATION.md`](WORKLOAD_VALIDATION.md).

1. Generate `proto_programs/generated/<collection_id>/design_*.py` from a reviewed
   methodology (see `fixtures/` and `program_builders.py`).
2. Read every generated file; confirm allow-listed imports and correct workload wiring.
3. Run `finalize_collection()` → writes `collection.json` with hashes.
4. Commit the collection folder.
5. Message Sai: collection ID and path only.

If anything changes after Sai starts analysis, create a **new collection ID**; do not
edit a frozen collection in place.

## Reference

- Contract: [`docs/PROGRAM_COLLECTION.md`](../../docs/PROGRAM_COLLECTION.md)
- API: `src/protofuse/phillip/generator.py` (`finalize_collection`)
- Validation: `src/protofuse/program_collection.py` (`load_collection`)
