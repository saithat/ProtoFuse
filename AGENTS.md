# ProtoFuse agent guidance

- Read `docs/ARCHITECTURE.md` and `docs/TEAM.md` before changing boundaries.
- Keep the shared `MethodologySpec` backward compatible when possible.
- Never execute code, commands, or model identifiers copied from a paper.
- Extracted claims require evidence or must be recorded in `unknowns`.
- Phillip owns the end-to-end pipeline under `src/protofuse/phillip/`.
- Sai owns reusable topology work under `src/protofuse/sai/`.
- Both collaborate in `src/protofuse/scientific_agent/` and `integration/`.
- Run `uv run ruff check .` and `uv run pytest` before pushing to `main`.
- Never commit papers, generated runs, API keys, Modal credentials, or model caches.
