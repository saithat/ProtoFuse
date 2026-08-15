"""ProtoStage candidate program builder (Sai-owned surface)."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from proto_language.core import Constraint, Program


def build_candidate_program(
    baseline_program: Program,
    *,
    decision_id: str,
    handoff_root: Path,
) -> tuple[Program, dict[str, int]]:
    """Apply Sai's prepared-state patch and return a candidate program plus cache stats."""

    sai_dir = handoff_root / "sai_to_phillip" / decision_id
    prepared = json.loads((sai_dir / "prepared_module_plan.json").read_text())
    graph_patch = json.loads((sai_dir / "graph_patch.json").read_text())

    program = deepcopy(baseline_program)
    target_node_id = prepared["target_node_id"]
    cache_stats: dict[str, int] = {target_node_id: 0}
    memo: dict[tuple[str, str], Any] = {}

    for optimizer in program.optimizers:
        rebuilt: list[Constraint] = []
        for constraint in optimizer.constraints:
            if getattr(constraint, "label", None) != "windowed_gc_content":
                rebuilt.append(constraint)
                continue
            original_fn = constraint.function

            def make_wrapped(fn: Any = original_fn) -> Any:
                def wrapped(
                    input_sequences: list[tuple[Any, ...]],
                    config: Any,
                ) -> Any:
                    sequence = input_sequences[0][0]
                    key = (sequence.sequence, json.dumps(config.model_dump(), sort_keys=True))
                    if key in memo:
                        cache_stats[target_node_id] += 1
                        return memo[key]
                    result = fn(input_sequences, config)
                    memo[key] = result
                    return result

                return wrapped

            rebuilt.append(
                Constraint(
                    inputs=list(constraint.inputs),
                    function=make_wrapped(),
                    function_config=constraint.function_config,
                    label=constraint.label,
                    threshold=constraint.threshold,
                    weight=constraint.weight,
                )
            )
        optimizer.constraints = rebuilt

    program._protofuse_candidate_meta = {  # type: ignore[attr-defined]
        "decision_id": decision_id,
        "target_node_id": target_node_id,
        "graph_patch_operations": [change["operation"] for change in graph_patch["changes"]],
    }
    return program, cache_stats
