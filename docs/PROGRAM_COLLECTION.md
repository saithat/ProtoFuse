# Generated Proto program folder

Phillip saves each reviewed collection here:

```text
proto_programs/generated/<collection_id>/
├── collection.json
├── design_001.py
└── design_002.py
```

Every design file must expose `build_program()` and do no work, network access, or model
loading on import. Files use only reviewed imports and registry symbols.

`collection.json` is generated automatically and contains only what Sai needs to load
the folder safely:

- collection ID;
- program filenames, entry points, and hashes;
- pinned Proto and registry versions;
- source `MethodologySpec` ID or hash;
- review status and seed policy.

Once Sai begins an analysis, the collection is read-only. Phillip creates a new
collection ID for any change.

Sai keeps profiles, teacher traces, calibration data, and reports under ignored
`data/analysis/<collection_id>/`, and model weights under `data/models/`. Stable learned
fusion code is promoted to `src/protofuse/sai/`. No second handoff folder is required.
