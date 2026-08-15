# Phillip and Sai work split

## One-time GitHub access

The repository owner must add Phillip's GitHub account as a collaborator with Write
access. Keep `main` free of a "pull request required" rule during the hackathon, while
retaining the CI check as the shared safety net. Neither teammate should force-push or
rewrite `main` history.

## Shared scientific agent

Both Phillip and Sai work in `src/protofuse/scientific_agent/` and jointly own:

- evidence-grounded method extraction;
- prompt and schema evaluation;
- paper parsing and Paperclip adapters;
- extraction quality fixtures.

Coordinate before changing `contracts.py`, because both tracks consume it.

## Phillip

Primary directory: `src/protofuse/phillip/`

- Paper ingestion through final plan orchestration.
- Reliability and provenance between each stage.
- A focused friction point, if one dominates the end-to-end path.
- Integration of the chosen topology and the approved Proto bindings.

Use `workspaces/phillip/` for disposable marimo notebooks or experiments before
promoting stable code into `src/`.

## Sai

Primary directory: `src/protofuse/sai/`

- Catalog common Proto workflow topologies.
- Rank topology fits for an extracted methodology.
- Optimize ordering, branching, iteration, stopping, and selection policies.
- Prototype ProtoStage prepared-state transforms over Phillip's typed graph handoffs:
  fixed-context preparation, shared generator prefixes, and mutation-delta updates.
- Benchmark topology choices against shared methodology fixtures.

Use `workspaces/sai/` for disposable experiments before promoting stable code into
`src/`.

Register paper and workflow scenarios under `philip-sai-integrations/v1/sai/` when Sai
selects them independently. The owner adds workflows under
`philip-sai-integrations/v1/contributed/`. Joint scenarios go in
`philip-sai-integrations/v1/mixed/`. Every scenario is versioned through
`manifest.json` and indexed in `philip-sai-integrations/v1/catalog.json`.

## Daily integration habit

At each handoff, save one synthetic or redistributable `MethodologySpec`, run both
tracks against it, and keep the end-to-end tests green. Versioned scenarios under
`philip-sai-integrations/` record mixed Sai and owner contributions by lane. Push small
commits to `main` after rebasing; do not force-push.
