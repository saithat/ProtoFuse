# Phillip and Sai work split

## Phillip: paper to Proto and final E2E

Phillip owns `src/protofuse/phillip/`, `src/protofuse/contracts.py`, and:

- extracts and reviews the methodology;
- binds only approved Proto components;
- generates readable executable programs;
- saves each frozen collection under `proto_programs/generated/<collection_id>/`;
- runs the final baseline-versus-fusion workflow end to end.

Phillip does not need to create graph/profile handoff files or choose Sai's hot path.

## Sai: learned fusion

Sai owns `src/protofuse/sai/` and:

- reads but does not edit frozen generated programs;
- profiles and finds recurring expensive model-step groups;
- distinguishes exact caching/batching from approximate learned fusion;
- trains a multi-output surrogate for one selected group;
- detects uncertainty and out-of-domain inputs and defers them to the full models;
- exposes one callable for Phillip's final E2E run.

## Four check-ins

1. Both review the extracted methodology.
2. Phillip freezes a generated collection and tells Sai its path.
3. Both choose the fusion target, outputs, thresholds, and error costs after Sai profiles
   the collection.
4. Both accept, reject, or revise the surrogate after reviewing risk versus coverage and
   Phillip's final E2E results.
