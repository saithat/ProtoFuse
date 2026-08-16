# Evo2 paper reproduction on Modal

This collection compares ordinary Proto with ProtoFuse on the three full regulatory-design
workloads encoded from the Evo2 paper. The smoke program is an infrastructure diagnostic and must
not be presented as a paper reproduction result.

## Why the B200 service exists

The paper workflow begins with a 40,960-base prompt, designs 19,968 bases in 128-base iterations,
and scores 30 ARC or 84 non-ARC proposals per iteration. The stock service failed on H100 and H200
memory, then failed on B200 because its older CUDA/PyTorch build had no `sm_100` kernel support.

This is a known deployment class, not a ProtoFuse-only problem:

- [Arc's official Dockerfile](https://github.com/ArcInstitute/evo2/blob/53f195997257c56c00e5ef8d33a54f5baad143a6/Dockerfile) starts from
  `nvcr.io/nvidia/pytorch:25.04-py3`, installs Evo2, and recommends a persistent Hugging Face cache.
- [Arc's installation guide](https://github.com/ArcInstitute/evo2#installation) supports Vortex,
  Docker, a 7B light install, NVIDIA NIM, and Savanna/BioNeMo for very long-sequence work.
- [NVIDIA's Evo2 NIM matrix](https://docs.nvidia.com/nim/bionemo/evo2/latest/prerequisites.html)
  supports the 7B model on one H100 or H200. NIM is a different serving engine and API, so it is
  not substituted for the paper-facing Vortex path here.
- A public [Hugging Face long-context evaluation](https://github.com/huggingface/carbon/blob/main/evaluation/README.md)
  reports Vortex model parallelism on eight H100s at 32--64k context. That is useful evidence that
  long-context memory pressure is common, but it does not prove our exact workload needs eight GPUs.

The paper also states that its regulatory-design sampler kept the full attention and Hyena inference
state alongside each retained sequence and ran on one 80 GB H100. The repo-owned service in
`scripts/evo2_b200_modal_app.py` follows that retained-state design with Evo2 0.5.5/Vortex 1.1.0,
while reusing Arc's NVIDIA 25.04 base. NVIDIA documents that image as CUDA 12.9, PyTorch 2.7
development, Transformer Engine 2.2, and Blackwell-optimized. Runtime provenance records the
versions and requires compute capability 10.0 or newer before a result run.

The deployed service was validated on one NVIDIA B200 (`sm_100`) before the result campaign. Its
recorded stack is Evo2 0.5.5, Vortex 1.1.0, FlashAttention 2.8.0.post2, PyTorch
2.7.0a0+79aa17489c.nv25.04, and CUDA 12.9. Arc's official forward check passed at mean loss 0.348
and 86.38% token accuracy; its generation check passed at 89.45% nucleotide identity. A separate
real-length check bootstrapped the complete 40,960-base prompt, generated and replayed one 128-base
proposal byte-identically, and verified that a released cache handle was rejected. These are
runtime/caching validation results, not Proto-versus-ProtoFuse benchmark measurements.

## Cache policy and scientific interpretation

Every proposal is sampled independently from its retained prompt, as specified by the paper, while
the number of live caches is bounded by the retained beam width rather than the proposal count:

1. One bootstrap call processes `prompt[:-1]` and returns a full-length cache sized for the complete
   60,928-base prompt-plus-design path.
2. Proposal calls clone the immutable retained-parent cache inside the worker but return no child
   cache, so 6, 30, or 84 candidate branches are not kept alive while Enformer and Borzoi score them.
3. After selection, only the retained branch or branches are replayed with their original per-call
   seeds and asked to return caches. The continuation must be byte-identical to the scored proposal;
   any mismatch aborts the run.
4. Replaced parent caches are released through the same one-container Modal worker. This is required
   because cache handles are worker-local.

The retained beam state contains `prompt + designed suffix`, as required for generation. Immediately
before scoring, the optimizer verifies and removes exactly the frozen prompt from the transient
Target proposal. Enformer and Borzoi therefore receive the upstream genomic context once, normalize
their complete model outputs, and compute optimization loss only over the growing designed suffix.
The trace records that same suffix-only Target view. A missing or mismatched prefix aborts the run.

The one long bootstrap uses `force_prompt_threshold=3000`: Vortex 1.1's public generation helper
uses 3,000 tokens and then prompt-forces the remainder to reduce peak memory
([Vortex source](https://github.com/Zymrael/vortex/blob/8b00afebeac745d1f31e7e2788f0e0e39fa47637/vortex/model/generation.py#L291)).
The paper does not disclose this operational threshold or its generation seed. It can therefore
produce small numerical or accuracy differences from the authors' private run, but it does not
change the reviewed model, genomic prompt, temperature, top-k, proposal distribution, scoring
functions, or selection rule. Proto and ProtoFuse use the same cache path and seed policy.

## Fusion score normalization

The surrogate never changes the paper-facing objective units. Enformer and Borzoi retain their raw
L1 sums in Proto; only the linear fit and its uncertainty gate use a frozen unit-interval transform.
For each partial beam, the scale is computed from the current designed target length: one Enformer
bin per 128 bp (at most 156 bins) and one Borzoi bin per 32 bp (at most 624 bins). Training and audit
require the trace's `paper_target_bins` value to agree with that rule and fail closed on a mismatch.
Observed training minima or maxima are not used as scale parameters.

Enformer's per-bin L1 bound is 1 after global-max normalization. Borzoi is not clipped after the
paper's four-replicate `mean - population standard deviation` lower-confidence bound. For four
inputs in `[0, 1]`, that LCB can be as low as `(1 - sqrt(3)) / 4`, so the conservative per-bin L1
bound is `(3 + sqrt(3)) / 4`, approximately `1.183013`, rather than 1. This follows the
[published Evo 2 scoring definition](https://pmc.ncbi.nlm.nih.gov/articles/PMC13128491/) and is
encoded in the frozen artifact with a small upward rounding margin for float32 arithmetic over at
most 624 bins. Predictions are decoded back to raw sums before Proto applies the paper's 0.5/0.5
weights; out-of-range predictions are deferred without clipping.

### Predeclared fusion gates

The first Evo2 artifact remains unreviewed unless an independent seed trajectory meets all of
these gates on surrogate-accepted proposals:

- per-objective MAE no greater than 5% of that objective's held-out 95th-to-5th-percentile range;
- per-objective Spearman rank correlation at least 0.90;
- selective coverage at least 30%; and
- no invalid final result, contract mismatch, non-finite value, or bypass of final parent
  validation.

These exact numbers are ProtoFuse engineering gates, not thresholds reported by the Evo2 authors.
Five percent demands small error relative to the observed useful score range, 0.90 demands strong
ordering because beam selection depends on rank, and 30% ensures that a passing artifact replaces
enough calls to be meaningful in a demo. Support-distance and ensemble-disagreement cutoffs are
frozen at the calibration cohort's 99th percentile; they are then judged by the independent
risk/coverage result rather than assumed correct.

This follows the selective-prediction principle of abstaining to trade coverage for lower risk
([Geifman and El-Yaniv, 2017](https://arxiv.org/abs/1705.08500)) and uses bootstrap-ensemble spread
as an empirical uncertainty signal, with explicit OOD deferral
([Lakshminarayanan et al., 2017](https://arxiv.org/abs/1612.01474)). Training in normalized units
while decoding back to the original objective units is consistent with output-preserving target
rescaling ([van Hasselt et al., 2016](https://arxiv.org/abs/1602.07714)); unlike Pop-Art, this
experiment freezes paper-derived scales rather than adapting them from observed targets. These
papers motivate the design, not the project-specific numeric cutoffs.

## Gates and experiment order

### Three-hour complete scaled campaign

Use `design-006` when the complete teacher, independent-seed audit, and paired Proto/ProtoFuse
comparison must finish within three hours. This is a real end-to-end optimization, not the one-step
smoke diagnostic: it uses the reviewed Evo 2 7B generator and the same Enformer and four-replicate
Borzoi objectives for all 32 128-base iterations. The retained beam width is one and each iteration
scores six proposals, for 192 proposals and 384 objective rows per complete trajectory.

The controlled scale changes are a 4,096-base genomic prompt, a complete 4,096-base design, and a
128-base Morse dot. At that dot width the complete ARC pattern occupies 3,712 bases, so the run
contains every ARC pulse and gap at Enformer's smallest output resolution instead of truncating the
paper-scale pattern. Results from this variant measure ProtoFuse versus Proto under identical real
models and inputs, but must be labeled a **scaled reproduction**: they are not estimates of the
paper's 19,968-base, 384-base-dot ARC accuracy or its 30-token-per-base default search budget.

Before accepting any result:

1. `protofuse review evo2-enformer-borzoi` must print `READY FOR HANDOFF`, and `protofuse paper
   evo2-enformer-borzoi` must verify all four evidence quotes.
2. The deployed provenance call must report one B200 (`sm_100` or newer), Evo2 0.5.5, Vortex 1.1.0,
   and the NVIDIA 25.04 runtime. Arc's pinned implementation checks are forward loss
   `0.3476563 ± 0.001` and 500-base greedy identity `89.25% ± 3 percentage points`; these validate
   the runtime, not scientific success ([forward test](https://github.com/ArcInstitute/evo2/blob/53f195997257c56c00e5ef8d33a54f5baad143a6/evo2/test/test_evo2.py),
   [generation test](https://github.com/ArcInstitute/evo2/blob/53f195997257c56c00e5ef8d33a54f5baad143a6/evo2/test/test_evo2_generation.py)).
3. `design-006` must complete its real 4,096-base prompt path and all 32 optimizer stages. A failed
   call is infrastructure evidence only, never a benchmark datum. The separate 40,960-base
   cache/replay gate already passed and remains evidence that the paper-length runtime path works;
   it does not turn an incomplete paper-length trajectory into a result.
4. Proto and ProtoFuse run sequentially with the same exact `B200:1` accelerator class, one
   container per service, no retries, identical inputs/seeds, and the default excluded full/fused
   warmup pair. The three-hour minimum has one measured full-then-fused seed, so it is a single warm
   paired observation with no timing confidence interval or arm-order counterbalance. Add a second
   measured seed in fused-then-full order when the deadline permits. Modal does not guarantee the
   same physical GPU across restarts, so reports claim equal hardware class and policy, not an
   identical GPU UUID.

Run the full programs in this order:

1. `design-006` (scaled ARC, 6 tok/bp): 192 proposals, one retained beam, and all 32 budgeted
   design iterations. Complete the teacher trajectory, an independent-seed audit trajectory, and
   the paired comparison before spending the remaining budget on paper-length runs.
2. `design-005` (ARC, 6 tok/bp): 936 proposals, one retained beam, and all 156 real design
   iterations. This is one of the paper's inference-time-scaling configurations, not a smoke run.
   Use seed 0 to collect teacher traces and a different seed for the first paired Proto/ProtoFuse
   result. Trace with `--group-by-input-batch`: all six sibling proposals from one retained parent
   stay in the same split group. The 156 parent steps can support train/calibration/development
   splits without repeating the full teacher run three times, but adjacent steps belong to one
   dependent trajectory and are not an independent scientific holdout. Use a different complete
   seed trajectory for the first reported paired Proto/ProtoFuse result. Lower accuracy than the
   authors' 30 tok/bp ARC result is expected.
3. `design-002` (ARC, 30 tok/bp): 4,680 proposals. Run this next if time permits to approach the
   paper's high-accuracy compute regime and reveal how fusion behaves under a larger search budget.
4. `design-001` (EVO2, 84 tok/bp): 13,104 proposals. This is the strongest speed/memory stress test.
5. `design-003` (LO, 84 tok/bp): 13,104 proposals with another target pattern, testing whether gains
   generalize rather than fitting ARC.

Report paper inputs separately from our measured outcomes. Primary paired metrics are output
parity/fallback safety, warm wall-clock speedup (a single observation in the three-hour minimum;
bootstrap confidence intervals only after collecting enough paired seeds), tool-call reduction,
the separate Enformer and Borzoi losses plus their paper-specified equal-weight mean, and the
paper-defined mean of the separate complete-output Enformer and Borzoi AUROCs. The paper reports that sampling at
least 30 tokens per designed base produced final computational AUROC above 0.9; use that as the
paper comparison threshold, not as a new optimizer cutoff. Its 0.92--0.95 experimental Morse AUROC
is historical wet-lab evidence and is not reproduced by this computational workflow.
