from dataclasses import dataclass

from protofuse import optimize_with_report
from protofuse.sai import FusionBundle, FusionRegistry


@dataclass(frozen=True)
class Program:
    steps: tuple[str, ...]


def test_runtime_applies_registered_compatible_fusion() -> None:
    registry: FusionRegistry[Program] = FusionRegistry()
    registry.register(
        FusionBundle(
            fusion_id="structure-and-score",
            version="1",
            matches=lambda program: program.steps == ("structure", "score"),
            apply=lambda program: Program(("selective_fusion",)),
        )
    )

    result = optimize_with_report(Program(("structure", "score")), registry=registry)

    assert result.program.steps == ("selective_fusion",)
    assert result.applied_fusions == ("structure-and-score@1",)


def test_runtime_leaves_unmatched_program_unchanged() -> None:
    program = Program(("experiment",))
    registry: FusionRegistry[Program] = FusionRegistry()

    result = optimize_with_report(program, registry=registry)

    assert result.program is program
    assert result.diagnostics == ("no_compatible_fusion",)


def test_runtime_leaves_program_unchanged_when_fusion_fails() -> None:
    program = Program(("structure", "score"))
    registry: FusionRegistry[Program] = FusionRegistry()

    def fail(_program: Program) -> Program:
        raise RuntimeError("bundle unavailable")

    registry.register(
        FusionBundle(
            fusion_id="structure-and-score",
            version="1",
            matches=lambda _program: True,
            apply=fail,
        )
    )

    result = optimize_with_report(program, registry=registry)

    assert result.program is program
    assert result.applied_fusions == ()
    assert result.diagnostics == ("apply_failed:structure-and-score@1:RuntimeError",)
