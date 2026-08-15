# Generated Proto program collection

Phillip saves each reviewed collection at:

```text
proto_programs/generated/<collection_id>/
├── collection.json
├── design_001.py
└── design_002.py
```

Every design exposes one synchronous `build_program()` and performs no execution,
network access, or model loading during import. Phillip's `finalize_collection()` checks
the declaration using Python's syntax tree and writes `collection.json` without importing
the programs.

The manifest contains:

- schema and collection IDs;
- source methodology ID or hash;
- pinned Proto and component-registry versions;
- seed policy and review status;
- program IDs, relative paths, `build_program` entry points, and SHA-256 hashes.

Sai calls `load_collection()` before analysis. It rejects unreviewed collections,
absolute or escaping paths, symlinked programs, missing files, duplicate entries, and
hash mismatches. Loading the manifest does not execute generated code.

Once Sai begins analysis, the collection is read-only. Phillip creates a new collection
ID for any change. Sai keeps profiles, traces, calibration data, and reports in
`data/analysis/<collection_id>/`, and weights under `data/models/`. There is no return
handoff folder: accepted fusions become registered runtime bundles in Sai's code.
