from __future__ import annotations

import numpy as np
import pytest

from protofuse.phillip.evo2_paper_constraints import (
    _binary_auroc,
    _l1_output,
    _normalization_denom,
)
from protofuse.sai.model import BORZOI_LCB_MAXIMUM_L1_PER_BIN


def test_binary_auroc_is_tie_aware_and_handles_one_class_prefixes() -> None:
    labels = np.asarray([1, 0, 1, 0])
    tied_scores = np.asarray([0.8, 0.8, 0.4, 0.1])

    assert _binary_auroc(labels, tied_scores) == 0.625
    assert _binary_auroc(np.ones(4), tied_scores) is None


def test_paper_l1_output_carries_post_hoc_auroc_without_changing_score() -> None:
    output = _l1_output(
        model_name="enformer",
        normalized_signal=np.asarray([1.0, 0.95, 0.9, 0.1, 0.8, 0.7]),
        target_start=2,
        target_end=4,
        output_start=0,
        resolution=1.0,
        highs=[(0, 1)],
        normalization_denom=3.0,
    )

    assert output.score == pytest.approx(0.2)
    assert output.metadata["paper_auroc"] == pytest.approx(0.6)
    assert output.metadata["paper_auroc_defined"] is True
    assert output.metadata["paper_auroc_scope"] == "complete_model_output"


def test_paper_l1_output_leaves_one_class_auroc_undefined() -> None:
    output = _l1_output(
        model_name="borzoi",
        normalized_signal=np.asarray([0.5, 0.4]),
        target_start=0,
        target_end=2,
        output_start=0,
        resolution=1.0,
        highs=[(0, 2)],
        normalization_denom=1.0,
    )

    assert output.score == pytest.approx(1.1)
    assert output.metadata["paper_auroc"] is None
    assert output.metadata["paper_auroc_defined"] is False


def test_borzoi_lcb_normalization_uses_theoretical_four_replicate_bound() -> None:
    replicates = np.asarray([0.0, 0.0, 0.0, 1.0])
    minimum_lcb = float(replicates.mean() - replicates.std())

    assert minimum_lcb == pytest.approx((1.0 - np.sqrt(3.0)) / 4.0)
    assert 1.0 - minimum_lcb <= BORZOI_LCB_MAXIMUM_L1_PER_BIN
    assert BORZOI_LCB_MAXIMUM_L1_PER_BIN > 1.0

    float32_replicates = np.asarray([0.0, 0.0, 0.0, 1.0], dtype=np.float32)
    worst_bin = np.float32(1.0) - (
        float32_replicates.mean() - float32_replicates.std()
    )
    worst_sum = float(np.sum(np.full(624, worst_bin, dtype=np.float32)))
    assert worst_sum <= 624 * BORZOI_LCB_MAXIMUM_L1_PER_BIN


@pytest.mark.parametrize("value", [np.nan, np.inf, -0.1])
def test_paper_normalization_rejects_invalid_model_signals(value: float) -> None:
    with pytest.raises(ValueError, match="non-finite|negative"):
        _normalization_denom("model", np.asarray([value], dtype=np.float32))
