# boltz2-state-sweep fixture

Recover the **alternative conformational state** of a two-state protein by sweeping
Boltz-2 inference controls on a **fixed sequence**, then scoring each draw against both
experimental reference structures.

## Benchmark target

| Tier | Protein | Dominant PDB | Alternative PDB | Length | Samples |
| --- | --- | --- | --- | --- | --- |
| full | XylE (IOMemP) | 4GBY (inward) | 4GBZ (outward) | 491 aa | 55 |
| smoke | Adenylate kinase | 4AKE (open) | 1AKE (closed) | 214 aa | 6 |

## Sai fusion target

`boltz2-prediction` on every rejection-sampling draw — identical sequence and MSA inputs,
varying only inference knobs (`subsample_msa`, `max_msa_seqs`, stochastic seed). Teacher
labels are RMSD to two deposited PDB structures (exact, no wet lab).

## References

- Suzuki & Amagasa, bioRxiv 2026 — pair representation scaling benchmark (86 two-state proteins)
- Xie & Huang, *J. Chem. Inf. Model.* 2024 — IOMemP inward/outward transporter set

## Commands

```bash
uv run protofuse preflight boltz2-state-sweep --length 214
uv run python scripts/run_handoff_pipeline.py boltz2-state-sweep
uv run protofuse review boltz2-state-sweep
```

**Handoff collection:** `proto_programs/generated/boltz2-state-sweep/`
