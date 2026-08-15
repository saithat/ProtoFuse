# ProtoFuse agent guidance

- Read `docs/ARCHITECTURE.md` and `docs/TEAM.md` before changing boundaries.
- Keep the shared `MethodologySpec` backward compatible when possible.
- Never execute code, commands, or model identifiers copied from a paper.
- Extracted claims require evidence or must be recorded in `unknowns`.
- Phillip owns the end-to-end pipeline under `src/protofuse/phillip/`.
- Sai owns program cataloging, profiling, learned fusion, surrogate routing, and
  calibration under `src/protofuse/sai/`.
- Phillip generates reviewed Proto program collections under `proto_programs/`; Sai's
  tooling must consume them without modification.
- Both collaborate in `src/protofuse/scientific_agent/` and `integration/`.
- Run `uv run ruff check .` and `uv run pytest` before pushing to `main`.
- Never commit papers, generated runs, raw teacher traces, surrogate weights, API keys,
  Modal credentials, or model caches.
