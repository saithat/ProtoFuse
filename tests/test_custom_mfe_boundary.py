from __future__ import annotations

import numpy as np

from protofuse.sai.custom_mfe_boundary import (
    ApproximateMfe,
    BoundaryGates,
    CustomPool,
    aggregate_boundary_runs,
    simulate_adaptive_pool,
)


def _pool() -> CustomPool:
    exact_mfe = np.asarray([0.0, 0.1, 0.2, 0.3, 0.4, 0.5])
    metric_scores = np.vstack((exact_mfe, *[np.zeros(6) for _ in range(4)]))
    return CustomPool(
        group_id="pool",
        input_hashes=tuple(f"hash-{index}" for index in range(6)),
        metric_scores=metric_scores,
        filter_pass=np.ones(6, dtype=np.bool_),
    )


def test_adaptive_boundary_recovers_exact_top_k_and_closes_selected_candidates() -> None:
    pool = _pool()
    predicted = [0.1, 0.2, 0.0, 0.3, 0.4, 0.5]
    approximation = ApproximateMfe(
        source="sampled",
        scores_by_hash=dict(zip(pool.input_hashes, predicted, strict=True)),
        accepted_by_hash={value: True for value in pool.input_hashes},
        rejection_reason_by_hash={},
    )

    report = simulate_adaptive_pool(pool, approximation, boundary_budget=4, top_k=2)

    assert report["top10_recall"] == 1.0
    assert report["selected_indexes"] == report["exact_selected_indexes"] == [0, 1]
    assert report["exact_mfe_candidates"] >= 4
    assert report["closure_iterations"] >= 1


def test_adaptive_boundary_counts_gate_fallbacks_as_exact_work() -> None:
    pool = _pool()
    approximation = ApproximateMfe(
        source="ridge_residual",
        scores_by_hash=dict(zip(pool.input_hashes, pool.metric_scores[0], strict=True)),
        accepted_by_hash={
            value: index != 5 for index, value in enumerate(pool.input_hashes)
        },
        rejection_reason_by_hash={"hash-5": "residual_mfe_out_of_domain"},
    )

    report = simulate_adaptive_pool(pool, approximation, boundary_budget=2, top_k=2)

    assert report["initial_gate_fallbacks"] == 1
    assert report["exact_mfe_candidates"] == 3
    assert report["rejection_reasons"] == {"residual_mfe_out_of_domain": 1}


def test_boundary_aggregate_enforces_recall_and_work_gates() -> None:
    run = {
        "source": "sampled",
        "boundary_budget": 20,
        "exact_mfe_extrema_closure": False,
        "mfe_tail_budget": 0,
        "top10_recall": 1.0,
        "ordered_top10_identical": True,
        "exact_mfe_candidates": 20,
        "mfe_work_avoided_fraction": 0.75,
        "theoretical_mfe_speedup": 4.0,
    }

    report = aggregate_boundary_runs(
        [run],
        gates=BoundaryGates(
            min_mean_top10_recall=1.0,
            min_seed_top10_recall=1.0,
            min_mfe_work_avoided_fraction=0.5,
        ),
    )

    assert report["passed"] is True
    assert all(report["checks"].values())
