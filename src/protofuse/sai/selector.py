"""Deterministic baseline for matching extracted methods to common topologies."""

from protofuse.contracts import MethodologySpec, TopologyKind, TopologyRecommendation


def recommend_topologies(spec: MethodologySpec) -> list[TopologyRecommendation]:
    """Rank transparent baseline templates; learned selection can replace this later."""

    candidates: list[TopologyRecommendation] = []
    components = len(spec.generators) + len(spec.constraints) + len(spec.optimizers)

    base_score = round(min(0.55 + 0.05 * components, 0.85), 3)
    candidates.append(
        TopologyRecommendation(
            topology=TopologyKind.PROPOSE_SCORE_SELECT,
            score=base_score,
            reasons=["Proto's common generator -> constraint scoring -> selection loop applies"],
        )
    )

    if spec.optimizers:
        candidates.append(
            TopologyRecommendation(
                topology=TopologyKind.ITERATIVE_REFINEMENT,
                score=round(min(0.65 + 0.05 * len(spec.optimizers), 0.9), 3),
                reasons=["The paper names an optimizer or refinement strategy"],
            )
        )

    if len(spec.selection_thresholds) >= 2:
        candidates.append(
            TopologyRecommendation(
                topology=TopologyKind.STAGED_FILTER,
                score=round(min(0.6 + 0.05 * len(spec.selection_thresholds), 0.9), 3),
                reasons=["Multiple explicit thresholds can form sequential gates"],
            )
        )

    if len(spec.constraints) >= 2:
        candidates.append(
            TopologyRecommendation(
                topology=TopologyKind.MULTIOBJECTIVE_SEARCH,
                score=round(min(0.7 + 0.05 * len(spec.constraints), 0.95), 3),
                reasons=["Multiple scored constraints require an aggregation or Pareto policy"],
            )
        )

    feedback = [m for m in spec.experimental_measurements if m.role == "feedback"]
    if feedback:
        candidates.append(
            TopologyRecommendation(
                topology=TopologyKind.CLOSED_LOOP_EXPERIMENT,
                score=round(min(0.75 + 0.05 * len(feedback), 0.95), 3),
                reasons=["Experimental measurements feed back into candidate selection"],
            )
        )

    return sorted(candidates, key=lambda item: item.score, reverse=True)
