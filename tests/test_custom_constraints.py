from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

from protofuse.phillip.custom_constraints import (
    CUSTOM_METRIC_LABELS,
    EGFP_PROTEIN_SEQUENCE,
    CustomPaperPoolOptimizer,
    paper_composite_energies,
)
from protofuse.phillip.program_builders import (
    build_custom_egfp_program,
    load_fixture_spec,
    resolve_workload_params,
)


def test_full_custom_program_matches_released_pool_shape_and_prompt_contract() -> None:
    spec = load_fixture_spec("custom-egfp-lung")
    params = resolve_workload_params(spec, tier="full")

    program = build_custom_egfp_program(params)
    optimizer = program.optimizers[0]
    generator = optimizer.generators[0]

    assert len(EGFP_PROTEIN_SEQUENCE) == 239
    assert program.constructs[0].segments[0].sequence_length == 717
    assert isinstance(optimizer, CustomPaperPoolOptimizer)
    assert optimizer.config.num_samples == 1000
    assert optimizer.config.proposal_batch_size == 1000
    assert optimizer.config.tracking_interval == 1000
    assert optimizer.config.num_results == 10
    assert generator.config.prompts == [EGFP_PROTEIN_SEQUENCE]
    assert generator.prompts == [EGFP_PROTEIN_SEQUENCE]
    assert generator.batch_size == 1000
    assert [constraint.label for constraint in optimizer.constraints] == [
        *CUSTOM_METRIC_LABELS,
        "homopolymer_filter",
    ]


def test_paper_composite_matches_custom_score_and_ignores_constant_metric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from custom import TissueOptimizer

    raw_metrics = [
        [-10.0, -20.0, -15.0],  # MFE: minimize
        [-2.0, -1.0, -3.0],  # initial MFE: maximize
        [0.70, 0.80, 0.75],  # CAI: maximize
        [0.10, 0.20, 0.15],  # CPB: maximize
        [40.0, 40.0, 40.0],  # ENC: constant in this pool
    ]
    minimize = (True, False, False, False, True)
    metric_names = ("MFE", "MFEini", "CAI", "CPB", "ENC")
    candidates = ["candidate-0", "candidate-1", "candidate-2"]
    reference = TissueOptimizer("Lung", n_pool=len(candidates))
    reference.pool = candidates
    for name, values in zip(metric_names, raw_metrics, strict=True):
        monkeypatch.setattr(reference, name, lambda values=values: values)

    with pytest.warns(RuntimeWarning, match="invalid value"):
        selected = reference.select_best(
            by={
                "MFE": "min",
                "MFEini": "max",
                "CAI": "max",
                "CPB": "max",
                "ENC": "min",
            },
            top=len(candidates),
        )
    expected_scores = dict(zip(selected["Sequence"], selected["Score"], strict=True))

    # Proto constraints use lower-is-better energies. Affine scaling does not change
    # per-pool min-max ranks, so direction reversal is sufficient for this parity check.
    constraint_energies = [
        values if should_minimize else [-value for value in values]
        for values, should_minimize in zip(raw_metrics, minimize, strict=True)
    ]

    actual_energies = paper_composite_energies(constraint_energies)

    assert actual_energies == pytest.approx(
        [1.0 - expected_scores[candidate] for candidate in candidates],
        abs=1e-12,
    )
    ranked_candidates = [
        candidates[index]
        for index in sorted(range(3), key=actual_energies.__getitem__)
    ]
    assert ranked_candidates == list(selected["Sequence"])


def test_reference_parity_report_uses_one_seeded_real_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from protofuse.phillip import program_builders

    params = resolve_workload_params(load_fixture_spec("custom-egfp-lung"), tier="full")
    params = {**params, "n_pool": 20, "top_k": 5, "num_results": 5}
    monkeypatch.setattr(
        program_builders,
        "resolve_workload_params",
        lambda _spec, *, tier: params,
    )

    report = program_builders.run_custom_reference_parity(seed=20260816, tier="full")

    assert report["status"] == "pass"
    assert report["passed"] is True
    assert report["reference_package"] == "custom-optimizer==0.0.1"
    assert report["seed"] == 20260816
    assert isinstance(report["derived_generator_seed"], int)
    assert report["pool_size"] == report["expected_pool_size"] == 20
    assert report["top_k"] == 5
    assert len(report["pool_sha256"]) == 64
    assert report["per_metric_max_abs_delta"] == pytest.approx(
        {metric: 0.0 for metric in ("MFE", "MFEini", "CAI", "CPB", "ENC")},
        abs=1e-12,
    )
    assert all(report["metric_agreement"].values())
    assert report["filter_agreement"] is True
    assert report["filter_disagreement_count"] == 0
    assert report["ordered_top_k_identity"] is True
    assert report["tolerances"] == {
        "raw_metric_atol": 1e-9,
        "raw_metric_rtol": 1e-9,
        "filter_agreement_required": True,
        "ordered_top_k_identity_required": True,
    }


def test_custom_reference_parity_cli_emits_structured_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from protofuse import cli
    from protofuse.phillip import program_builders

    report = {"status": "pass", "passed": True, "seed": 17}
    monkeypatch.setattr(
        program_builders,
        "run_custom_reference_parity",
        lambda *, seed, tier: {**report, "seed": seed, "tier": tier},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["protofuse", "custom-reference-parity", "--seed", "17", "--tier", "full"],
    )

    cli.main()

    assert json.loads(capsys.readouterr().out) == {**report, "tier": "full"}


def test_custom_reference_parity_cli_writes_atomic_artifact(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    from protofuse import cli
    from protofuse.phillip import program_builders

    report = {"status": "pass", "passed": True, "seed": 17, "tier": "full"}
    output = tmp_path / "parity.json"
    monkeypatch.setattr(
        program_builders,
        "run_custom_reference_parity",
        lambda *, seed, tier: {**report, "seed": seed, "tier": tier},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "protofuse",
            "custom-reference-parity",
            "--seed",
            "17",
            "--tier",
            "full",
            "--out",
            str(output),
        ],
    )

    cli.main()

    assert json.loads(output.read_text()) == report
    assert capsys.readouterr().out.strip() == f"parity={output}"


@pytest.mark.parametrize(
    "metrics",
    [
        [],
        [[]],
        [[0.0, 1.0], [0.0]],
        [[0.0, math.nan]],
        [[0.0, math.inf]],
        [[1.0, 1.0], [2.0, 2.0]],
    ],
)
def test_paper_composite_fails_closed_on_invalid_or_unrankable_input(
    metrics: list[list[float]],
) -> None:
    with pytest.raises(ValueError):
        paper_composite_energies(metrics)
