# Pipeline timing — GPCR CXCR4 miniprotein

**Paper:** Muratspahić et al., *De novo design of miniproteins targeting GPCRs*  
**DOI:** [10.1038/s41586-026-10656-8](https://doi.org/10.1038/s41586-026-10656-8)  
**Collection ID for Sai:** `gpcr-cxcr4-miniprotein`

## End-to-end agent run (this session)

| Phase | Duration | Notes |
| --- | --- | --- |
| Paper review + repo recon | ~90 s | Nature abstract, bioRxiv methods, Proto inventory check |
| Paperclip attempt | ~5 s | CLI not installed; REST endpoint unreachable; used local preprint text |
| Fixture + builder implementation | ~100 s | methodology.json, program_builders, registries, paper_ingest |
| Generate + finalize collection | **7 ms** | `scripts/run_gpcr_cxcr4_pipeline.py` (warm) |
| Tests + validation | ~3 s | `pytest tests/test_generator.py`, `protofuse collection validate` |
| **Total (agent wall clock)** | **~213 s (~3.5 min)** | Excludes user response wait time |

Start epoch: `1786836721.023` · End epoch: `1786836934.408`

## Pipeline stages (script timer)

Recorded in [`TIMING_gpcr-cxcr4-miniprotein.json`](TIMING_gpcr-cxcr4-miniprotein.json):

1. `paper_ingest` — local fallback (`data/papers/gpcr-miniprotein.txt`)
2. `methodology_fixture` — reviewed `workspaces/phillip/fixtures/gpcr-cxcr4-miniprotein/`
3. `compile_proto_plan` — all bindings resolved via `gpcr-cxcr4` registry
4. `generate_program_sources` — `design_001.py` (full), `design_002.py` (smoke)
5. `finalize_collection` — `collection.json` with SHA-256 hashes, `reviewed=true`

Re-run:

```bash
uv run python scripts/run_gpcr_cxcr4_pipeline.py
uv run protofuse collection validate gpcr-cxcr4-miniprotein
```

## Sai handoff

```text
proto_programs/generated/gpcr-cxcr4-miniprotein/
├── collection.json
├── design_001.py   # full: 70 aa binder, 10 rejection samples
└── design_002.py   # smoke: 50 aa binder, 2 rejection samples
```

**Fusion targets:** `boltz2-prediction`, `structure-iptm` (every rejection-sampling draw).

## Paperclip status

- `PAPERCLIP_API_KEY` present in `.env`
- Paperclip CLI not on PATH in this environment
- Ingestion module tries Paperclip CLI → local file → HTTP; conventional run should install CLI per [`docs/SETUP.md`](../../docs/SETUP.md)
