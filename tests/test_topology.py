from protofuse.phillip import recommend_topologies
from protofuse.phillip.contracts import MethodologySpec, TopologyKind


def test_multiobjective_topology_ranks_first(example_spec: MethodologySpec) -> None:
    recommendations = recommend_topologies(example_spec)

    assert recommendations[0].topology == TopologyKind.MULTIOBJECTIVE_SEARCH
    assert {item.topology for item in recommendations} >= {
        TopologyKind.PROPOSE_SCORE_SELECT,
        TopologyKind.ITERATIVE_REFINEMENT,
        TopologyKind.STAGED_FILTER,
    }
