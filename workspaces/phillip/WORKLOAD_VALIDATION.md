# Workload validation

Before scaling compute on a new paper→Proto binding, confirm the workload is **feasible**
at the target construct length. Empty output or fast failure usually means a **binding**
problem (how we wired constraints, init, and search), not a proto-language bug.

## Isolation ladder

Run these steps in order at the **paper target length** before tuning region passes,
pool size, or inner refinement.

| Step | Check | Pass criterion |
|------|-------|----------------|
| L0 | Bare proto MCMC at target length | Output length == target |
| L1 | + scoring constraints only (no `threshold`) | `len(output) == target_length` |
| L2 | + hard filters (`threshold=0.0`) | `len(output) == target_length` |
| L3 | Full stack (+ region solver if used) | `len(output) == target_length` |
| L4 | Runtime calibration | Only after L0–L3 pass |

Run programmatically:

```bash
uv run protofuse preflight dnachisel-num1 --length 2808
```

Or import from `protofuse.phillip.workload_preflight`.

## Attribution rules

| Observation | L0 at failing length | Classification | Action |
|-------------|----------------------|----------------|--------|
| Empty `joined_sequences` | Passes | **Binding infeasible** | Bisect constraints/init; seed sequence or soften filters during search |
| Empty `joined_sequences` | Fails | **Platform error** | Escalate proto-language issue |
| Very fast runtime + empty output | Passes | **Binding infeasible** | Do not add region passes to compensate |
| Output length matches target | — | **OK** | Proceed to runtime calibration |

**Never skip L0.** If L0 passes and L2 fails, the problem is our binding — not proto length limits.

## Agent / developer contract

1. **Observe** — note symptom (empty output, fast runtime, errors).
2. **Isolate** — bare proto control at the failing scale.
3. **Attribute** — binding vs platform vs paper mismatch.
4. **Document** — fixture README if scope is reduced.
5. **Scale** — only after output-length invariant passes.

Do not add region passes, pool size, or inner refinement to compensate for 0 bp output.

## Key invariant

Every runnable fixture must satisfy:

```python
assert len(program.constructs[0].joined_sequences[0].sequence) == segment_length_bp
```

See `tests/test_workload_preflight.py`.

## Case study: DNA Chisel NUM1 at 2808 bp

**Symptom:** Full NUM1 stack at 2808 bp returned `len(sequence) == 0`; 936 bp worked.

**Wrong diagnosis:** “2808 bp breaks proto-language.”

**Correct diagnosis:** Workload binding infeasibility with empty MCMC start + hard filters.

### Mechanism

1. `Segment(length=2808)` starts with empty `result_sequences`.
2. First MCMC step random-inits the full sequence.
3. Hard filters (`homopolymer_limit`, `bsai_site_removal` with `threshold=0.0`) reject most random DNA.
4. At 2808 bp, Monte Carlo estimate: ~0% of random sequences pass both filters (vs ~5% at 936 bp).
5. MCMC rejects the proposal and **reverts to empty** → next step random-inits again → loop.
6. Proto-language at 2808 bp with **no constraints** produces full output (L0 passes).

### Fix applied

`build_dnachisel_num1_program` seeds a filter-safe random sequence before MCMC
(`generate_filter_safe_sequence` in `sequence_init.py`).

### Scope note

Paper construct = **2808 bp** (NUM1 CDS + flanks). Executable fixture defaults to **936 bp**
(CDS only) for gene-scale benchmarking with the region-local solver. Preflight at 2808 bp
documents whether the binding supports full construct length.
