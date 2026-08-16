# Phillip and Sai work split

## Phillip: paper to ordinary Proto

Phillip owns `src/protofuse/phillip/` and:

- extracts and reviews `MethodologySpec`;
- binds only approved Proto components;
- generates readable ordinary Proto programs;
- finalizes frozen collections under `proto_programs/generated/<collection_id>/`;
- performs the end-to-end scientific validation used to accept a fusion.

Phillip does not produce graph/profile handoffs, select Sai's hot path, train the
surrogate, or modify the fusion gate.

## Sai: automatic learned fusion

Sai owns `src/protofuse/sai/` and:

- reads frozen collections without modifying them;
- derives step signatures and profiles recurring expensive groups;
- applies exact caching/batching opportunities before approximate fusion;
- trains a multi-output surrogate group and calibrates applicability/uncertainty;
- packages accepted work as a registered `FusionBundle`;
- guarantees per-input full-model fallback through `SelectiveRouter`.

Sai does not require Phillip's paper text, methodology extraction internals, graph dumps,
or benchmark directories.

“Multi-output” currently means that aligned objective scores share one artifact, inference call,
and fail-closed routing decision. It does not mean that objectives are scalarized or that the
linear baseline models cross-objective covariance.

## Shared code decisions

Both coordinate changes to `program_collection.py` and `runtime.py`. These are thin,
stable contracts; owner-specific implementation stays in the owner packages.

## Implementation status

The shared collection contract and Sai's analyzer, signature, trace/profile, grouped
training, artifact, matching, transformation, routing, and paired-evaluation code are
implemented. That means the software path is ready for a reviewed experiment; it does not
mean a learned fusion has been scientifically accepted. No checked-in artifact is currently
marked `reviewed=true`. Real campaign traces, target-specific thresholds, paired runs, and
human acceptance remain the next scientific work.

## Four check-ins

1. Review the scientific methodology and intended Proto program behavior.
2. Freeze a generated collection for Sai.
3. Choose the recurring fusion target, outputs, applicability domain, thresholds, and
   asymmetric error costs after real profiling.
4. Accept, reject, or revise the fusion after risk-coverage analysis and Phillip's E2E
   scientific validation.
