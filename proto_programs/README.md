# Generated Proto program collections

Phillip's generator writes collections to `generated/<collection_id>/`. Each collection
contains an automatically generated `collection.json` and one or more inert Python files
that expose `build_program()`.

```text
proto_programs/
├── generated/<collection_id>/
│   ├── collection.json
│   ├── design_001.py
│   └── design_002.py
└── fixtures/<collection_id>/
    ├── collection.json
    └── design_001.py
```

`fixtures/` is for small synthetic or redistributable collections used by tests.
Generated program files must not contain raw paper text, confidential sequences,
credentials, dynamic imports, or executable instructions copied from a paper.
