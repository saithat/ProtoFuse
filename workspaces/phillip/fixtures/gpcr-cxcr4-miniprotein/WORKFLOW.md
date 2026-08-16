# GPCR CXCR4 miniprotein binder — Phillip workflow

Paper: Muratspahić et al., *De novo design of miniproteins targeting GPCRs*
(DOI [`10.1038/s41586-026-10656-8`](https://doi.org/10.1038/s41586-026-10656-8)).

This fixture scopes the **computational in-silico design loop** for the CXCR4 antagonist
**dCX1_001** case study. Wet-lab screening (OPS-RD, yeast display, pharmacology, cryo-EM,
in vivo HSPC mobilization) is documented as out-of-scope `unknowns`.

## Paper → Proto mapping

| Paper stage | Proto component | Notes |
| --- | --- | --- |
| Motif-directed / scaffold-guided RFdiffusion backbones | `rfdiffusion-mpnn-binder` | RFdiffusion **v3** substitutes paper's RFdiffusion v1.0 |
| ProteinMPNN sequence design | bundled in `rfdiffusion-mpnn-binder` | 10 seqs/backbone in paper → generator default |
| AF2 initial-guess filtering | `structure-iptm` (Boltz-2) | Paper pAE/pLDDT gates → ipTM threshold |
| Binding quality | `boltz2-binding-strength` | Proxy for Rosetta ddG / interface metrics |
| Binder length 65–75 aa | `protein-length` | Paper CXCR4 design range |
| Iterative partial diffusion (10×) | `rejection-sampling` | v1: independent design batches, not partial-T loop |
| OPS-RD / yeast / pharmacology | — | Out of scope |

## Target

- **Receptor:** CXCR4 (class A GPCR)
- **Structure:** PDB `4RWS`, chain `A`
- **Hotspots:** W94, I259, I284 (orthosteric pocket; paper Methods)
- **Design:** antagonist miniprotein binder, ~70 aa full tier / 50 aa smoke tier

## Collection handoff

```text
proto_programs/generated/gpcr-cxcr4-miniprotein/
├── collection.json
├── design_001.py   # full tier
└── design_002.py   # smoke tier
```

The numeric suffixes are stable ordinals, not tier names. This two-program collection uses
`001` for full and `002` for smoke; the module docstrings remain the authority.

Sai fusion targets: `boltz2-prediction` and `structure-iptm` on every rejection-sampling draw.
