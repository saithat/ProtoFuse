# Generated CXCR4 miniprotein binder collection for Sai profiling.

Paper: Muratspahić et al., Nature 2026, `10.1038/s41586-026-10656-8`.

- `design_001.py` — full tier (70 aa, 10 rejection samples)
- `design_002.py` — smoke tier (50 aa, 2 rejection samples)

Validate: `uv run protofuse collection validate gpcr-cxcr4-miniprotein`

Requires Modal GPU for execution (`rfdiffusion3-design`, `proteinmpnn-sample`, `boltz2-prediction`).
