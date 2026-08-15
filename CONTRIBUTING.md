# Contributing directly to main

This is a two-person trunk-based project.

1. Work in your owned directory and coordinate changes to the scientific agent or shared
   contract.
2. Keep commits small and pull before pushing.
3. Treat `proto_programs/generated/<collection_id>/` as frozen once Sai starts using it;
   create a new collection ID instead of silently changing it.
4. Run the checks below, then push directly to `main`. Never force-push `main`.

```bash
uv run ruff check .
uv run pytest
```

Do not commit raw papers, generated runs, teacher traces, calibration datasets, model
weights, credentials, or model caches.
