# CUSTOM eGFP-lung reproduction

This is the result contract for the **full** CUSTOM eGFP-to-lung workflow. Reported
experiments use the 239-aa eGFP input, a 1,000-sequence synonymous pool, the five released
CUSTOM metrics, the seven-nucleotide homopolymer exclusion, and top-10 selection. The reduced
`design-002`/`smoke` workload is only a software diagnostic and must not appear in result tables.

The paper describes a probabilistic pool followed by selection on MFE, MFEini, CAI, CPB, and
ENC, and reports the exact directions, homopolymer cutoff, pool size, and top-10 selection [1].
Its historical random seed and full dependency environment were not reported. Therefore, exact
historical sequence identity is not a valid reproduction requirement; exact parity with the
pinned released implementation on the **same generated pool** is.

## Four evidence layers

Every result belongs to exactly one layer. Do not collapse “paper” and “released CUSTOM,” or
“Proto” and “ProtoFuse,” into a single baseline:

| Layer | Role | Valid comparison and claim |
| --- | --- | --- |
| **Paper** | Historical protocol, eight selected designs, supplementary metric rows, and wet-lab outcomes | Descriptive historical reference. The unreported RNG seed and environment prevent exact pool or sequence replay. |
| **Released CUSTOM** | Pinned executable oracle for sampling, the five raw metrics, pool-relative `Score`, filtering, and selection | On one identical ordered candidate pool, this is the golden reference for Proto adapter parity. |
| **Proto** | Exact program encoding of the released workflow | Must match released CUSTOM on candidate-pool hash, every raw metric, filter result, and ordered top ten; then serves as the paired full-model baseline. |
| **ProtoFuse** | MFE-only execution candidate with exact non-MFE objectives, parent fallback where applicable, and final parent validation | Compare only against Proto on identical new inputs, seeds, ordered candidate-pool hashes, and run conditions. Report top-10 fidelity, routes, CPU/process use, reliability, and end-to-end runtime. |

The paper reported higher tissue-matched eGFP/mCherry ratios in the intended cell line for all
four constructs, with the same primary-cell direction except one less-evident construct [2]. The
released package, Proto, and ProtoFuse do **not** measure those wet-lab endpoints. Use them as
biological motivation only; mark their cells `not measured`, never zero, and do not call them
reproduced without new assays.

The CUSTOM aggregate `Score` is min-max normalized over one complete pool. It is meaningful for
ranking candidates **within that pool**, but is not on a common scale across seeds. Do not compare
it to Proto's fixed affine constraint energies or to a final-validation energy computed only over
the selected ten. Use raw metric vectors, same-pool rank/set agreement, and paired runtime instead.

## Prospective amendment: MFE-only ProtoFuse

Development model selection rejected the learned candidates that replaced all five objectives.
That result changes only the ProtoFuse candidate, not the reproduction: released CUSTOM and Proto
still generate, score, filter, and rank with all five exact metrics [1]. The frozen external audit
and initial ten-seed paired cohorts reported below are complete; the reserved confirmation and
challenge cohorts remain unopened.

The amended comparison freezes two body-MFE candidates before confirmatory evaluation:

| Candidate | MFE path | What remains exact |
| --- | --- | --- |
| **Exact parallel** | Run the complete released CUSTOM MFE calculation in eight ordered worker processes, with exact parent fallback on execution failure | Every MFE value, all 638 body-window calculations per sequence, MFEini, CAI, CPB, ENC, homopolymer filtering, and selected-candidate metadata; no second validation stage is needed because the complete pool is already exact |
| **Sampled window** | Use the frozen stride-8, calibrated 40-nt-window estimate; an uncertainty gate routes each uncertain item to exact MFE | MFE for deferred items, MFEini, CAI, CPB, ENC, homopolymer filtering, and all final top-10 objectives |

Exact parallelism uses more CPU cores to perform the same calculations; it does **not** reduce the
scientific work. Report wall time and process/core use together. The sampled candidate is the only
calculation-reducing path, and remains subject to the unchanged accuracy, coverage, OOD, recall,
and speed gates. This narrower target is an MFE-only selective fusion, not a multi-output learned
fusion claim. Conservative model management and fallback remain necessary because optimization
can move an approximation away from its development distribution [3][4].

For sampled-window ProtoFuse, final validation recomputes all five metrics and the filter exactly
on the selected top ten, but it
cannot recover a candidate excluded earlier by approximate MFE ranking. Therefore top-10 recall
against same-pool Proto is a required gate, even when every delivered candidate has exact final
metadata.

One published eGFP-lung row is exposed verbatim by the paper's parsed supplementary Metrics sheet
and is the initial historical checkpoint [1]:

| Published variant | MFE | MFEini | CAI | CPB | ENC |
| --- | ---: | ---: | ---: | ---: | ---: |
| `eGFP_lung_827_set1` (`mCKeGL1`) | -4.01379309923951 | -0.600000023841857 | 0.719807459612008 | 0.033500390510054 | 40.0143280686847 |

Place this row beside the Proto and ProtoFuse selected-candidate distributions, not beside a
single allegedly matching regenerated sequence. For each new arm report top-10 median, minimum,
maximum, and all ten raw rows. `fusion evaluate-custom-mfe` records exact final metadata for
both arms under each run's `full_result_metadata` and `fused_result_metadata`; the CUSTOM values
are nested under the `egfp_cds` segment and the five `custom_*` constraint labels. Label the paper
row `historical, unpaired` and every same-seed Proto/ProtoFuse comparison `paired`.

## Completed initial results

The canonical compact artifact is
`data/analysis/custom-egfp-lung/results-summary.json`; it records SHA-256 hashes for the parity,
external-audit, and paired reports. Raw reports remain ignored under `data/`.

| Result | Evidence | Outcome |
| --- | --- | --- |
| Released CUSTOM ↔ Proto parity | One identical ordered 1,000-candidate pool, seed 0 | Pass: all five maximum absolute metric deltas `0.0`, zero filter disagreements, ordered top-10 identity |
| Sampled-MFE frozen audit | 4 untouched groups / 4,000 candidates, seeds 44–47 | Pass: 99.075% coverage, 37 exact fallbacks, accepted MAE 4.205% of q95–q05, accepted Spearman 0.9835 |
| Proto ↔ exact-parallel ProtoFuse | 10 counterbalanced same-host pairs / 10,000 candidates, seeds 100–109 | Pass: 10/10 matching pool hashes and ordered top tens; 5.79× net speedup, bootstrap 95% CI 5.77–5.82×; zero fallback |
| Proto ↔ sampled-window ProtoFuse | 10 counterbalanced same-host pairs / 10,000 candidates, seeds 100–109 | Pass: 10/10 matching pool hashes; mean top-10 recall 0.91, minimum 0.80; 12.26× net speedup, bootstrap 95% CI 12.00–12.52×; 98.81% coverage and 119 exact fallbacks |

Every local computation in this reported campaign—released-CUSTOM parity, development trace
collection and model selection, the frozen external audit, and both paired cohorts—ran CPU-only
on one AMD Ryzen 9 7950X3D host with 16 physical cores / 32 hardware threads and 64 GiB installed
memory (61.9 GiB visible to Linux). No GPU contributed to these results. Both arms of every paired
comparison ran sequentially in one local process on that host, with arm order counterbalanced by
seed. Exact parallel and the sampled-window audit/evaluation were capped at eight worker
processes, so exact-parallel speedup is a wall-time-for-cores trade rather than avoided scientific
calculation.

The table below compares the single historical paper row with medians and ranges across the 100
exactly rescored selected candidates from the ten paired seeds. It is descriptive and unpaired;
the exact-parallel ProtoFuse vectors equal Proto's vectors, while sampled-window selection changes
some members of the top ten.

| Source | MFE ↓ | MFEini ↑ | CAI ↑ | CPB ↑ | ENC ↓ |
| --- | ---: | ---: | ---: | ---: | ---: |
| Paper `mCKeGL1` [1] | -4.0138 | -0.6000 | 0.7198 | 0.0335 | 40.0143 |
| Proto / exact-parallel ProtoFuse, median [min, max] | -3.9639 [-4.8386, -3.1458] | -2.8000 [-7.5000, -0.2000] | 0.7337 [0.7157, 0.7582] | 0.0371 [-0.0093, 0.1229] | 45.4824 [39.8650, 56.3239] |
| Sampled-window ProtoFuse, median [min, max] | -4.0136 [-4.8386, -3.1458] | -2.8000 [-7.5000, -0.2000] | 0.7338 [0.7142, 0.7582] | 0.0347 [-0.0093, 0.1229] | 45.5935 [39.8650, 56.3239] |

Do not interpret closeness to one paper row as historical sequence reproduction. The unreported
paper seed prevents pairing, and the published row is one selected design rather than a target
value or population mean.

## Experiment order

### Compute order

This order protects the evidence from leakage. Stop at a failed gate and report the weakness
before spending on dependent work.

1. **Released CUSTOM ↔ Proto parity, one full pool.** Run the full parity command below. It
   compares both paths on the exact same ordered 1,000 candidates and requires identical pool
   hashes before comparing metrics or selection.
2. **Full Proto baseline and profile.** Save the top ten and raw five-metric rows; verify that body
   MFE is the target worth accelerating and report its share of exact runtime.
3. **Development decision.** Use only the predeclared 12 training, 4 calibration, and 4
   model-selection groups to reject the all-five learned candidates and freeze the two MFE-only
   candidates: exact eight-process execution and calibrated stride-8 sampling with an uncertainty
   gate. Retain the rejected candidates in the development record.
4. **Frozen external audit.** Audit the sampled-window candidate on at least 4 additional full-pool
   groups. Never use them to refit calibration or the uncertainty gate. If the audit fails, report
   failure; do not tune and reuse it. The exact-parallel candidate instead requires bit-identical
   MFE and ordered-selection parity.
5. **OOD and failure safety.** On separately declared full-pool challenges, require parent fallback
   for unsupported, non-finite, or shifted inputs before studying finer coverage trade-offs.
   Surrogate-assisted optimization is vulnerable to distribution shift, so model management and
   real-objective evaluation remain necessary [3][4].
6. **Boundary/uncertainty trade-off.** Run full pools near support and uncertainty boundaries and
   plot accepted-only error against coverage and deferral reason.
7. **In-domain paired runs.** Only after the audit and safety checks, compare Proto separately with
   exact-parallel and sampled-window MFE on new full-pool seeds with counterbalanced arm order.
   Candidate-pool hashes must match for every pair or that pair is invalid.
8. **Fallback-heavy control.** Run a full cohort designed to defer often and report the slowdown or
   break-even point including routing, fallback, and final-validation overhead.

If the first 10 paired seeds clearly fail fidelity or speed, stop and present that result. For a
stronger claim, freeze all choices and run 20 additional untouched paired seeds as a separate
confirmation cohort; never relabel development or initial paired seeds as confirmatory.

### Slide order

Presentation order should foreground the useful result without pretending it was computed first:

1. the paper objective and released CUSTOM ↔ Proto exact parity;
2. the prospective amendment: all-five learned candidates rejected during development;
3. exact eight-process MFE: exactness and wall time beside its higher core use;
4. sampled stride-8 MFE: only measured audit/paired fidelity, coverage, fallback, and speed;
5. OOD/failure fallback, then boundary risk-versus-coverage behavior;
6. top-10 recall misses, fallback-heavy overhead, and resource costs (the weaknesses);
7. the published wet-lab direction, explicitly `historical, unpaired / not measured here`.

## Predeclared gates

These are pragmatic hackathon gates, not thresholds reported by the CUSTOM paper. Exact
biological invariants are strict; approximation and performance gates are deliberately useful
effect sizes rather than claims of universal statistical validity.

| Gate | Threshold | Reason |
| --- | ---: | --- |
| Full-pool construction | Exactly 1,000 sequences; every sequence 717 bp and translates exactly to the fixture eGFP protein | These are deterministic protocol invariants, so tolerance would hide an implementation error. |
| Candidate-pool identity | Ordered candidate-pool SHA-256 is identical for released CUSTOM ↔ Proto parity and for every paired Proto ↔ ProtoFuse seed | Metric, rank, and timing comparisons are not paired evidence if generation produced different candidates. Hash the ordered pool, not an unordered set. |
| Reference raw metrics | Per-candidate MFE, MFEini, CAI, CPB, and ENC agree with the pinned released implementation at `atol=1e-9, rtol=1e-9` on the same pool | Both paths call the same pinned numerical implementation. Any larger mismatch needs explanation before approximation is studied. |
| Reference selection | Ordered top-10 identity = 100%; homopolymer violations = 0 | This validates the adapter's score-entire-pool → filter → select semantics. |
| Exact-parallel MFE | Per-candidate MFE and ordered top ten are identical to Proto; execution failures fall back exactly | Parallel scheduling may change wall time, never values or the number of folding calculations. |
| Historical paper concordance | Descriptive only; report published rows beside current raw distributions, with no sequence-identity pass/fail gate | The paper did not provide the RNG seed or a fully pinned environment, so an exact historical pool cannot be regenerated. |
| Sampled-MFE frozen audit | Accepted-only MFE MAE ≤5% of the external-audit MFE `(q95-q05)` raw range; **accepted-only** Spearman rank correlation ≥0.90 | The other four objectives are exact. A zero MFE range is non-informative and fails rather than passing silently. |
| In-domain coverage | ≥30% with the accuracy gate still satisfied | Below 30%, there is too little avoided work to make a useful narrow-workload demo unless the parent metric is exceptionally expensive. This is an engineering floor, not a safety target. |
| Paired selection fidelity | Identical pool hash; exact-parallel recall =1.00; sampled mean top-10 set recall ≥0.80 with no seed <0.60; delivered translation and homopolymer validity =100% | Exact final validation cannot restore candidates removed before it. Show ordered agreement separately, but do not use pool-relative energy regret. |
| OOD/failure behavior | ≥95% challenge deferral; zero invalid delivered results; zero uncaught/non-finite run failures | Fail-closed routing is a safety invariant. The 95% routing target allows a small number of demonstrably safe in-support challenges without weakening delivered-output validity. |
| Reliability | 100% paired arms complete with comparable outputs | Failed or non-finite pairs are categorical failures, never numeric zeros and never excluded without a count. |
| Useful speedup | Total-time net speedup ≥1.25× and bootstrap 95% CI lower bound >1.0 | A 25% improvement is large enough to matter in a demo; excluding 1.0 prevents ordinary timing noise from being called a speedup. Always report the complete interval and seed-level distribution. |

Report threshold misses; do not change a threshold after seeing the audit or paired result. Raw
values, denominators, seed/group counts, hashes, and `null` measurements must accompany every
pass/fail summary.

The development key `audit_accepted_mae_q95_q05_fraction` and sampled-audit key
`accepted_mae_q95_q05_fraction` divide accepted-only MFE MAE by the audit MFE q95–q05 range. The
CUSTOM affine scale factor cancels, so the ratio equals raw-unit normalized MAE. The 0.90 rank gate
likewise uses accepted samples only (`accepted_spearman`), never all-proposal correlation.

ENC's biological interpretation is conventionally 20–61, but CUSTOM's finite-sequence estimator
can return slightly larger values (the fixed-seed full-pool validation reached 61.058). Proto uses
a deliberately broad 0–100 affine transport envelope so it neither clips that estimator nor
changes within-pool ordering. This is not a widened biological acceptance threshold: the raw ENC
is always reported, and the same-pool released-implementation parity gate remains exact.

## Commands

Use the paper review sheet for the human scientific judgement:

```bash
uv run protofuse paper custom-egfp-lung
```

After acceptance, finalize the collection manifest as `reviewed=true`, then run the mechanical
gate. It must end in `READY FOR HANDOFF` before result collection:

```bash
uv run protofuse review custom-egfp-lung
```

First run the focused same-pool released-CUSTOM ↔ Proto parity check:

```bash
uv run protofuse custom-reference-parity --seed 0 --tier full \
  --out data/analysis/custom-egfp-lung/reference-parity-seed-000.json
```

It atomically writes structured JSON containing the pool hash and size, seeds, five metric deltas,
filter and top-k agreement, and tolerances; it exits nonzero on failure. Do not substitute two
independently generated pools.

After parity passes, run the exact full baseline:

```bash
uv run protofuse run custom-egfp-lung --tier full
```

One trace invocation is one independent full-pool seed group. Repeat with a new seed and matching
`run-id`/`group-id`; the repository does not yet provide a resumable multi-seed campaign runner.
Write development and frozen-audit traces to different files. Only the development file may enter
model comparison or calibration.

```bash
uv run protofuse trace \
  proto_programs/generated/custom-egfp-lung design-001 \
  --out data/analysis/custom-egfp-lung/teacher-development.jsonl \
  --run-id full-seed-000 --group-id full-seed-000 \
  --seed 0 --tier full

uv run protofuse fusion profile \
  --trace data/analysis/custom-egfp-lung/teacher-development.jsonl \
  --out data/analysis/custom-egfp-lung/profile.json

uv run protofuse fusion compare-models \
  --trace data/analysis/custom-egfp-lung/teacher-development.jsonl \
  --optimizer-index 0 \
  --constraint custom_mfe --constraint custom_mfe_init \
  --constraint custom_cai --constraint custom_cpb --constraint custom_enc \
  --seed 0 --out data/analysis/custom-egfp-lung/model-comparison.json
```

The all-five learned-model report is retained as development evidence, but none of those models is
eligible for training or promotion. Audit the frozen sampled-MFE specification on at least four
independent traces, disjoint by content hash and group ID from development:

```bash
uv run protofuse fusion audit-custom-mfe-sampled \
  --trace data/analysis/custom-egfp-lung/frozen-audit/teacher-frozen-audit-seed-044.jsonl \
  --trace data/analysis/custom-egfp-lung/frozen-audit/teacher-frozen-audit-seed-045.jsonl \
  --trace data/analysis/custom-egfp-lung/frozen-audit/teacher-frozen-audit-seed-046.jsonl \
  --trace data/analysis/custom-egfp-lung/frozen-audit/teacher-frozen-audit-seed-047.jsonl \
  --development-report data/analysis/custom-egfp-lung/model-comparison-mfe-only.json \
  --workers 8 \
  --out data/analysis/custom-egfp-lung/frozen-sampled-mfe-audit-v2.json
```

This writes the complete report and exits nonzero on a failed gate. Do not interpret or run the
sampled paired arm unless it passes. The two paired commands are intentionally separate:

```bash
uv run protofuse fusion evaluate-custom-mfe \
  proto_programs/generated/custom-egfp-lung design-001 \
  --mode exact-parallel --workers 8 \
  --seed 100 --seed 101 --seed 102 --seed 103 --seed 104 \
  --seed 105 --seed 106 --seed 107 --seed 108 --seed 109 \
  --allow-unreviewed \
  --out data/analysis/custom-egfp-lung/paired-exact-parallel.json

uv run protofuse fusion evaluate-custom-mfe \
  proto_programs/generated/custom-egfp-lung design-001 \
  --mode sampled-window --workers 8 \
  --audit-report data/analysis/custom-egfp-lung/frozen-sampled-mfe-audit-v2.json \
  --seed 100 --seed 101 --seed 102 --seed 103 --seed 104 \
  --seed 105 --seed 106 --seed 107 --seed 108 --seed 109 \
  --allow-unreviewed \
  --out data/analysis/custom-egfp-lung/paired-sampled-window.json
```

`--allow-unreviewed` is for the local experiment only. Neither this guide nor a successful run
authorizes promotion. Keep raw pools, traces, runs, reports, and candidate state under ignored
`data/` paths.

Before claiming all eight experiment stages are runnable, close or explicitly disclose the
remaining tooling gaps: no resumable multi-seed trace campaign and no dedicated full-pool
challenge runner. Manual single-seed tracing and the frozen audit command are valid; improvised
challenge cohorts or silently substituted development results are not.

The current `reports/protofuse-evaluation.html` is a **retired legacy smoke report**. It reflects
the former reduced, two-objective workflow and must not be refreshed, cited, or shown as evidence
for this reproduction. Canonical evidence is the same-pool parity artifact, frozen external audit,
and paired JSON. A replacement presentation report is valid only after it consumes those exact
full-pool artifacts and preserves the four evidence layers.

## Human scientific-fairness review

The reviewer decides only whether the encoding is a fair reading of the paper. Before approving
the collection, confirm:

- [ ] The fixture protein is the intended full eGFP sequence (239 aa/717 bp), target is `Lung`,
      optimization degree is 0.5, and the released CUSTOM version is an acceptable reference.
- [ ] A run generates one complete pool of 1,000 synonymous sequences before any ranking or
      filtering; the diagnostic reduced pool is not represented as a reproduction.
- [ ] MFE is minimized; MFEini, CAI, and CPB are maximized; ENC is minimized; all five contribute
      equally after full-pool min-max normalization.
- [ ] Candidates with homopolymers of length ≥7 are removed **after full-pool scoring**, then the
      top ten remaining candidates are retained.
- [ ] Constant metric-column behavior and ties match the released implementation, or any
      difference is explicitly recorded in `unknowns`.
- [ ] Released CUSTOM and Proto parity use one identical ordered pool, and every Proto/ProtoFuse
      pair records matching ordered candidate-pool hashes before its metrics are accepted.
- [ ] Missing historical seeds and dependency versions are disclosed, and historical selected
      variants are treated as descriptive checkpoints rather than an exact seeded golden set.
- [ ] Development train/calibration/model-selection groups and the frozen external audit are
      separate by seed manifest and file; the external audit was not used to choose or tune.
- [ ] The amendment records that all-five learned candidates were rejected during development;
      neither candidate is presented as a multi-output learned fusion.
- [ ] Exact parallel evaluates every released MFE window and reports its eight-process/core cost;
      sampled MFE alone uses frozen stride-8 calibration, uncertainty routing, and exact fallback.
- [ ] MFEini, CAI, CPB, ENC, and the homopolymer filter remain exact for the full pool, while final
      exact top-10 validation is not claimed to recover candidates excluded earlier.
- [ ] Pool-relative `Score` is never compared across seeds or relabeled as a globally comparable
      Proto/ProtoFuse energy.
- [ ] Slides and reports keep computational outcomes separate from the paper's wet-lab expression
      measurements, with Proto and ProtoFuse wet-lab cells marked `not measured`.
- [ ] The legacy smoke HTML is retired; any replacement reads only the exact full-pool parity,
      external-audit, and paired artifacts described here.

After this judgement, rerun `protofuse paper` and `protofuse review`; do not manually re-check
hashes, source drift, imports, bindings, or quote presence that those commands already prove.

--------
REFERENCES

[1] Hernandez-Alias X, Benisty H, Radusky LG, Serrano L, Schaefer MH. “Using protein-per-mRNA differences among human tissues in codon optimization.” *Genome Biology* 24 (2023). doi:10.1186/s13059-023-02868-2
    https://paperclip.gxl.ai/citations/papers/PMC9951436#L43,L57,L66,L75,L1303-L1310

[2] Hernandez-Alias X, Benisty H, Radusky LG, Serrano L, Schaefer MH. “Using protein-per-mRNA differences among human tissues in codon optimization.” *Genome Biology* 24 (2023). doi:10.1186/s13059-023-02868-2
    https://paperclip.gxl.ai/citations/papers/PMC9951436#L44-L47

[3] Jin Y. “Surrogate-assisted evolutionary computation: Recent advances and future challenges.” *Swarm and Evolutionary Computation* 1, 61–70 (2011). doi:10.1016/j.swevo.2011.05.001
    https://doi.org/10.1016/j.swevo.2011.05.001

[4] Fannjiang C, Listgarten J. “Autofocused oracles for model-based design.” *Advances in Neural Information Processing Systems* 33 (2020).
    https://proceedings.neurips.cc/paper/2020/hash/972cda1e62b72640cb7ac702714a115f-Abstract.html
