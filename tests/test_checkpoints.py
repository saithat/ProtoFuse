from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from proto_language.constraint import gc_content_constraint
from proto_language.core import Constraint, Construct, Program, Segment
from proto_language.generator import (
    RandomNucleotideGenerator,
    RandomNucleotideGeneratorConfig,
)
from proto_language.optimizer import (
    CyclingOptimizer,
    CyclingOptimizerConfig,
    MCMCOptimizer,
    MCMCOptimizerConfig,
    RejectionSamplingOptimizer,
    RejectionSamplingOptimizerConfig,
)
from proto_tools.transforms.masking import MaskingStrategy

from protofuse import run_with_checkpoints
from protofuse.checkpoints import CheckpointCompatibilityError


def _parts() -> tuple[Segment, Construct, Constraint]:
    segment = Segment(sequence="ATGCATGCATGC", sequence_type="dna", label="dna")
    construct = Construct([segment])
    constraint = Constraint(
        inputs=[segment],
        function=gc_content_constraint,
        function_config={"min_gc": 25, "max_gc": 75},
        label="gc_content",
    )
    return segment, construct, constraint


def _generator(
    segment: Segment,
) -> RandomNucleotideGenerator:
    generator = RandomNucleotideGenerator(
        RandomNucleotideGeneratorConfig(
            masking_strategy=MaskingStrategy(num_mutations=1),
        )
    )
    generator.assign(segment)
    return generator


def _mcmc_program(*, num_steps: int = 5) -> Program:
    segment, construct, constraint = _parts()
    optimizer = MCMCOptimizer(
        constructs=[construct],
        generators=[_generator(segment)],
        constraints=[constraint],
        config=MCMCOptimizerConfig(
            num_steps=num_steps,
            num_results=1,
            proposals_per_result=1,
            seed=9,
        ),
    )
    return Program(optimizers=[optimizer], num_results=1)


def _rejection_program() -> Program:
    segment, construct, constraint = _parts()
    optimizer = RejectionSamplingOptimizer(
        constructs=[construct],
        generators=[_generator(segment)],
        constraints=[constraint],
        config=RejectionSamplingOptimizerConfig(
            num_samples=6,
            num_results=1,
            proposal_batch_size=2,
            seed=9,
        ),
    )
    return Program(optimizers=[optimizer], num_results=1)


def _cycling_program() -> Program:
    segment, construct, _constraint = _parts()
    generator = _generator(segment)
    random_sample = generator.sample

    def ignore_conditioning(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        random_sample()

    generator.sample = ignore_conditioning  # type: ignore[method-assign]
    optimizer = CyclingOptimizer(
        target_segment=segment,
        constructs=[construct],
        generators=[generator],
        constraints=[],
        config=CyclingOptimizerConfig(num_steps=5, num_results=1, seed=9),
        conditioning_fn=lambda sequences: [None for _ in sequences],
    )
    return Program(optimizers=[optimizer], num_results=1)


def _program_record(root: Path, run_id: str) -> dict[str, Any]:
    return json.loads((root / run_id / "test" / "program-0000.json").read_text())


def _events(root: Path, run_id: str) -> list[dict[str, Any]]:
    path = root / run_id / "test" / "events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.mark.parametrize(
    ("run_id", "builder", "saved_units", "resumed_calls", "trace_units"),
    [
        ("mcmc", _mcmc_program, 2, 3, [1, 2, 3, 4, 5]),
        ("cycling", _cycling_program, 2, 3, [1, 2, 3, 4, 5]),
        ("rejection", _rejection_program, 4, 1, [2, 4, 6]),
    ],
)
def test_run_resumes_after_credit_error_without_repeating_completed_units(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run_id: str,
    builder: Callable[[], Program],
    saved_units: int,
    resumed_calls: int,
    trace_units: list[int],
) -> None:
    interrupted = builder()
    first_generator = interrupted.optimizers[0].generators[0]
    first_sample = first_generator.sample
    first_calls = 0

    def fail_on_third_call(*args: Any, **kwargs: Any) -> None:
        nonlocal first_calls
        first_calls += 1
        if first_calls == 3:
            raise RuntimeError(
                "model credits exhausted api_key=must-not-be-saved "
                "Authorization: Bearer must-also-not-be-saved"
            )
        first_sample(*args, **kwargs)

    monkeypatch.setattr(first_generator, "sample", fail_on_third_call)

    with pytest.raises(RuntimeError):
        run_with_checkpoints(
            interrupted,
            checkpoint_dir=tmp_path,
            run_id=run_id,
            tier="test",
        )

    interrupted_record = _program_record(tmp_path, run_id)
    assert interrupted_record["stages"]["0"]["completed_units"] == saved_units
    assert "must-not-be-saved" not in interrupted_record["failure"]["message"]

    resumed = builder()
    resumed_generator = resumed.optimizers[0].generators[0]
    resumed_sample = resumed_generator.sample
    observed_resumed_calls = 0

    def count_resumed_calls(*args: Any, **kwargs: Any) -> None:
        nonlocal observed_resumed_calls
        observed_resumed_calls += 1
        resumed_sample(*args, **kwargs)

    monkeypatch.setattr(resumed_generator, "sample", count_resumed_calls)
    run_with_checkpoints(
        resumed,
        checkpoint_dir=tmp_path,
        run_id=run_id,
        tier="test",
    )

    completed_record = _program_record(tmp_path, run_id)
    manifest = json.loads((tmp_path / run_id / "test" / "manifest.json").read_text())
    assert observed_resumed_calls == resumed_calls
    assert completed_record["status"] == "completed"
    assert completed_record["stages"]["0"]["completed_units"] == trace_units[-1]
    assert (
        completed_record["stages"]["0"]["resume_events"][0]["completed_units"]
        == saved_units
    )
    assert manifest["resume_count"] == 1
    assert [attempt["status"] for attempt in manifest["attempts"]] == [
        "interrupted",
        "completed",
    ]
    assert manifest["cumulative_wall_time_seconds"] > 0
    assert resumed.current_stage == 1
    assert resumed.get_stage_results(0)["results"]

    trace_path = tmp_path / run_id / "test" / "program-0000.trace.jsonl"
    trace = [json.loads(line) for line in trace_path.read_text().splitlines()]
    assert [row["completed_units"] for row in trace] == trace_units

    events = _events(tmp_path, run_id)
    assert [event["sequence"] for event in events] == list(range(len(events)))
    assert [event["event"] for event in events].count("run_started") == 2
    assert [event["event"] for event in events].count("run_interrupted") == 1
    assert [event["event"] for event in events].count("run_completed") == 1
    assert [
        event["details"]["completed_units"]
        for event in events
        if event["event"] == "optimizer_progress"
        and event["details"]["checkpoint_saved"]
    ] == trace_units
    serialized_events = "\n".join(json.dumps(event) for event in events)
    assert "must-not-be-saved" not in serialized_events
    assert "must-also-not-be-saved" not in serialized_events

    restored = builder()
    restored_generator = restored.optimizers[0].generators[0]

    def unexpected_model_call(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise AssertionError("completed checkpoint should not call the model")

    monkeypatch.setattr(restored_generator, "sample", unexpected_model_call)
    run_with_checkpoints(
        restored,
        checkpoint_dir=tmp_path,
        run_id=run_id,
        tier="test",
    )
    assert restored.current_stage == 1
    assert restored.get_stage_results(0)["results"]

    restored_events = _events(tmp_path, run_id)
    assert restored_events[-2]["event"] == "program_restored"
    assert restored_events[-1]["event"] == "run_completed"


def test_changed_program_fails_closed_unless_restart_is_explicit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    interrupted = _mcmc_program()
    generator = interrupted.optimizers[0].generators[0]

    def fail_immediately(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise RuntimeError("credits exhausted")

    monkeypatch.setattr(generator, "sample", fail_immediately)
    with pytest.raises(RuntimeError, match="credits exhausted"):
        run_with_checkpoints(
            interrupted,
            checkpoint_dir=tmp_path,
            run_id="changed",
            tier="test",
        )

    changed = _mcmc_program(num_steps=6)
    with pytest.raises(CheckpointCompatibilityError, match="no longer matches"):
        run_with_checkpoints(
            changed,
            checkpoint_dir=tmp_path,
            run_id="changed",
            tier="test",
        )

    run_with_checkpoints(
        changed,
        checkpoint_dir=tmp_path,
        run_id="changed",
        tier="test",
        restart=True,
    )
    archived = list((tmp_path / "changed").glob("test.archived-*"))
    assert len(archived) == 1
    assert _program_record(tmp_path, "changed")["status"] == "completed"
