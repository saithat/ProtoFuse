from __future__ import annotations

import json
from itertools import product
from pathlib import Path

from protofuse.sai.model_comparison import compare_model_families
from protofuse.sai.training import TeacherSample


def test_model_family_comparison_uses_one_grouped_vector_output_split(tmp_path: Path) -> None:
    sequences = ("".join(symbols) for symbols in product("ACGT", repeat=3))
    samples = tuple(
        TeacherSample(
            sequences=(sequence,),
            outputs=(
                sum(base in "GC" for base in sequence) / len(sequence),
                float(sequence[0] == sequence[-1]),
            ),
            group_id=f"group-{index}",
        )
        for index, sequence in enumerate(sequences)
        if index < 30
    )
    trace_path = tmp_path / "trace.jsonl"
    trace_path.write_text("synthetic comparison provenance\n")

    report = compare_model_families(
        samples,
        output_labels=("composition", "terminal_match"),
        trace_paths=(trace_path,),
        seed=7,
        linear_ensemble_size=2,
        tree_count=4,
        mlp_ensemble_size=2,
        mlp_hidden_width=4,
        mlp_max_iter=5,
        latency_repeats=2,
    )

    assert report["experiment"]["same_grouped_split"] is True
    assert report["experiment"]["scalarized_objective"] is False
    assert report["experiment"]["automatic_winner"] is None
    assert set(report["models"]) == {
        "linear_ensemble",
        "extra_trees",
        "small_mlp_ensemble",
    }
    assert report["dataset"]["output_labels"] == ["composition", "terminal_match"]
    assert all(
        len(model["audit"]["mae"]) == 2 for model in report["models"].values()
    )
    assert all(
        len(model["audit"]["accepted_error"]["mae_q95_q05_fraction"]) == 2
        for model in report["models"].values()
    )
    json.dumps(report, allow_nan=False)
