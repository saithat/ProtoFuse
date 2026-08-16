# Contributing directly to main

This is a two-person trunk-based project.

1. Work in `src/protofuse/phillip/` or `src/protofuse/sai/` according to ownership.
2. Coordinate changes to `program_collection.py`, `runtime.py`, and public APIs.
3. Treat `proto_programs/generated/<collection_id>/` as frozen once Sai starts using it;
   create a new collection ID instead of changing it silently.
4. Never hand-edit `design_*.py`; update the builder or workload profile and regenerate so
   the source-drift gate remains meaningful.
5. When implementation status changes, update the relevant README, architecture/setup
   guide, and owner TODO. Keep “code implemented” separate from “real traces collected,”
   “paired run completed,” and “artifact reviewed.”
6. Keep commits small, pull before pushing, and never force-push `main`.
7. Run:

```bash
uv run ruff check .
uv run mypy src/protofuse
uv run pytest
```

Tests must exercise real deterministic code paths. Do not add mocked E2E flows or smoke
scripts. Never commit papers, generated runs, teacher traces, calibration datasets,
model weights, credentials, or model caches.
