"""Preflight checks for paper→Proto workload bindings before scaling compute."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from proto_language.constraint import gc_content_constraint, max_homopolymer_constraint
from proto_language.core import Constraint, Construct, Program, Segment
from proto_language.generator import RandomNucleotideGenerator, RandomNucleotideGeneratorConfig
from proto_language.optimizer import MCMCOptimizer, MCMCOptimizerConfig
from proto_tools.transforms.masking import MaskingStrategy

from protofuse.phillip.dnachisel_constraints import (
    codon_usage_constraint,
    kmer_uniqueness_constraint,
    pattern_avoidance_constraint,
    reference_homology_constraint,
    sliding_window_gc_constraint,
)
from protofuse.phillip.program_builders import (
    build_antibody_cdr_maturation_program,
    build_dnachisel_num1_program,
    build_esm2_protein_maturation_program,
    load_fixture_spec,
    resolve_workload_params,
)
from protofuse.phillip.sequence_init import estimate_filter_pass_rate, generate_filter_safe_sequence

logger = logging.getLogger(__name__)

PreflightClassification = Literal["ok", "binding_infeasible", "platform_error"]

PREFLIGHT_NUM_STEPS = 50
PREFLIGHT_MCMC_DEFAULTS: dict[str, Any] = {
    "num_steps": PREFLIGHT_NUM_STEPS,
    "proposals_per_result": 1,
    "max_temperature": 1.0,
    "mutations_per_step": 3,
}


@dataclass(frozen=True)
class LadderStepResult:
    level: str
    output_length: int
    expected_length: int
    passed: bool
    detail: str = ""


@dataclass
class PreflightReport:
    fixture_id: str
    target_length: int
    filter_pass_rate: float
    ladder_steps: list[LadderStepResult] = field(default_factory=list)
    classification: PreflightClassification = "binding_infeasible"
    mcmc_accepted_any: bool = False
    filter_pass_samples: int = 500

    @property
    def output_length(self) -> int:
        if not self.ladder_steps:
            return 0
        return self.ladder_steps[-1].output_length

    def summary(self) -> str:
        lines = [
            f"fixture={self.fixture_id} length={self.target_length}",
            f"classification={self.classification}",
            f"filter_pass_rate={self.filter_pass_rate:.2%} (n={self.filter_pass_samples})",
            f"mcmc_accepted_any={self.mcmc_accepted_any}",
        ]
        for step in self.ladder_steps:
            status = "PASS" if step.passed else "FAIL"
            lines.append(f"  {step.level}: {status} output={step.output_length} {step.detail}".rstrip())
        return "\n".join(lines)


def _l0_passthrough_constraints(segment: Segment) -> list[Constraint]:
    """Wide-open GC range so L0 verifies proto MCMC + generator only."""

    return [
        Constraint(
            inputs=[segment],
            function=gc_content_constraint,
            function_config={"min_gc": 0, "max_gc": 100},
            weight=1.0,
            label="l0_passthrough_gc",
        )
    ]


def _run_program_output_length(program: Program) -> int:
    program.run()
    joined = program.constructs[0].joined_sequences
    if not joined:
        return 0
    return len(joined[0].sequence)


def _mcmc_program_from_segment(
    segment: Segment,
    constraints: list[Constraint],
    *,
    num_steps: int = PREFLIGHT_NUM_STEPS,
    mutations_per_step: int = 3,
) -> Program:
    construct = Construct([segment])
    generator = RandomNucleotideGenerator(
        RandomNucleotideGeneratorConfig(
            masking_strategy=MaskingStrategy(num_mutations=mutations_per_step),
        )
    )
    generator.assign(segment)
    optimizer = MCMCOptimizer(
        constructs=[construct],
        generators=[generator],
        constraints=constraints,
        config=MCMCOptimizerConfig(
            num_results=1,
            proposals_per_result=1,
            num_steps=num_steps,
            max_temperature=1.0,
        ),
    )
    return Program(optimizers=[optimizer], num_results=1)


def _make_segment(length: int, seed_sequence: str | None) -> Segment:
    if seed_sequence is not None:
        return Segment(sequence=seed_sequence, sequence_type="dna")
    return Segment(length=length, sequence_type="dna")


def _run_ladder_step(
    length: int,
    constraint_builder: Callable[[Segment], list[Constraint]],
    *,
    seed_sequence: str | None = None,
    num_steps: int = PREFLIGHT_NUM_STEPS,
) -> int:
    segment = _make_segment(length, seed_sequence)
    program = _mcmc_program_from_segment(
        segment,
        constraint_builder(segment),
        num_steps=num_steps,
    )
    return _run_program_output_length(program)


def _dnachisel_scoring_constraints(segment: Segment) -> list[Constraint]:
    return [
        Constraint(
            inputs=[segment],
            function=sliding_window_gc_constraint,
            function_config={"min_gc": 40, "max_gc": 60, "window_bp": 100},
            weight=1.0,
            label="windowed_gc_content",
        ),
        Constraint(
            inputs=[segment],
            function=kmer_uniqueness_constraint,
            function_config={"k": 6, "max_frequency": 0.015},
            weight=0.5,
            label="kmer_uniqueness_6",
        ),
        Constraint(
            inputs=[segment],
            function=kmer_uniqueness_constraint,
            function_config={"k": 7, "max_frequency": 0.012},
            weight=0.5,
            label="kmer_uniqueness_7",
        ),
        Constraint(
            inputs=[segment],
            function=reference_homology_constraint,
            function_config={
                "k": 6,
                "reference_length_bp": 50000,
                "max_homology_hits": 2,
                "reference_seed": 42,
            },
            weight=0.75,
            label="reference_homology_6",
        ),
        Constraint(
            inputs=[segment],
            function=reference_homology_constraint,
            function_config={
                "k": 8,
                "reference_length_bp": 50000,
                "max_homology_hits": 0,
                "reference_seed": 42,
            },
            weight=0.75,
            label="reference_homology_8",
        ),
        Constraint(
            inputs=[segment],
            function=codon_usage_constraint,
            function_config={"target_organism": "escherichia_coli"},
            weight=0.5,
            label="codon_optimization",
        ),
    ]


def _dnachisel_filter_constraints(segment: Segment) -> list[Constraint]:
    return [
        Constraint(
            inputs=[segment],
            function=pattern_avoidance_constraint,
            function_config={"pattern": "GGTCTC", "max_occurrences": 0},
            threshold=0.0,
            label="bsai_site_removal",
        ),
        Constraint(
            inputs=[segment],
            function=max_homopolymer_constraint,
            function_config={"max_length": 4},
            threshold=0.0,
            label="homopolymer_limit",
        ),
    ]


def run_isolation_ladder(
    target_length: int,
    *,
    build_full_program: Callable[[dict[str, Any]], Program] | None = None,
    num_steps: int = PREFLIGHT_NUM_STEPS,
    seed_sequence: str | None = None,
    use_seed_for_l2: bool = True,
) -> list[LadderStepResult]:
    """Run L0–L3 isolation steps at target_length."""

    results: list[LadderStepResult] = []

    l0_len = _run_ladder_step(
        target_length,
        _l0_passthrough_constraints,
        num_steps=num_steps,
    )
    results.append(
        LadderStepResult(
            level="L0",
            output_length=l0_len,
            expected_length=target_length,
            passed=l0_len == target_length,
            detail="bare MCMC, passthrough GC constraint",
        )
    )

    l1_len = _run_ladder_step(
        target_length,
        _dnachisel_scoring_constraints,
        seed_sequence=seed_sequence,
        num_steps=num_steps,
    )
    results.append(
        LadderStepResult(
            level="L1",
            output_length=l1_len,
            expected_length=target_length,
            passed=l1_len == target_length,
            detail="scoring constraints only",
        )
    )

    l2_seed = seed_sequence
    if use_seed_for_l2 and l2_seed is None:
        try:
            l2_seed = generate_filter_safe_sequence(target_length, seed=target_length)
        except RuntimeError:
            l2_seed = None

    def l2_constraints(segment: Segment) -> list[Constraint]:
        return _dnachisel_scoring_constraints(segment) + _dnachisel_filter_constraints(segment)

    l2_len = _run_ladder_step(
        target_length,
        l2_constraints,
        seed_sequence=l2_seed,
        num_steps=num_steps,
    )
    results.append(
        LadderStepResult(
            level="L2",
            output_length=l2_len,
            expected_length=target_length,
            passed=l2_len == target_length,
            detail="scoring + hard filters",
        )
    )

    if build_full_program is not None:
        params = {**PREFLIGHT_MCMC_DEFAULTS, "segment_length_bp": target_length}
        l3 = build_full_program(params)
        l3_len = _run_program_output_length(l3)
        results.append(
            LadderStepResult(
                level="L3",
                output_length=l3_len,
                expected_length=target_length,
                passed=l3_len == target_length,
                detail="full NUM1 stack",
            )
        )

    return results


def classify_report(ladder_steps: list[LadderStepResult]) -> PreflightClassification:
    if not ladder_steps:
        return "binding_infeasible"
    l0 = next((s for s in ladder_steps if s.level == "L0"), None)
    if l0 is not None and not l0.passed:
        return "platform_error"
    if all(step.passed for step in ladder_steps):
        return "ok"
    return "binding_infeasible"


def run_preflight(
    fixture_id: str,
    *,
    target_length: int | None = None,
    filter_samples: int = 500,
    num_steps: int = PREFLIGHT_NUM_STEPS,
    quiet: bool = True,
) -> PreflightReport:
    """Run preflight for a supported fixture at target_length."""

    if quiet:
        logging.disable(logging.CRITICAL)

    spec = load_fixture_spec(fixture_id)
    workload = spec.global_parameters.get("workload")
    if workload in {"esm2_protein_maturation", "antibody_cdr_maturation"}:
        if workload == "esm2_protein_maturation":
            length = target_length or int(spec.global_parameters.get("segment_length_aa", 80))
            params = resolve_workload_params(spec, tier="smoke")
            if target_length is not None:
                params["segment_length_aa"] = target_length
                params["seed_sequence"] = str(params["seed_sequence"])[:target_length]
            program = build_esm2_protein_maturation_program(params)
            built_length = program.constructs[0].segments[0].sequence_length
        else:
            length = target_length or len(str(spec.global_parameters.get("framework_sequence", "")))
            params = resolve_workload_params(spec, tier="smoke")
            program = build_antibody_cdr_maturation_program(params, region_pass=0)
            built_length = program.constructs[0].segments[0].sequence_length
        ladder = [
            LadderStepResult(
                level="L0",
                output_length=built_length,
                expected_length=length,
                passed=built_length == length,
                detail="build-only preflight (GPU constraints skipped)",
            )
        ]
        return PreflightReport(
            fixture_id=fixture_id,
            target_length=length,
            filter_pass_rate=1.0,
            ladder_steps=ladder,
            classification=classify_report(ladder),
            mcmc_accepted_any=False,
            filter_pass_samples=0,
        )

    length = target_length or int(spec.global_parameters.get("segment_length_bp", 100))
    filter_rate = estimate_filter_pass_rate(length, n=filter_samples)

    seed_sequence: str | None = None
    build_full: Callable[[dict[str, Any]], Program] | None = None

    if fixture_id == "dnachisel-num1":
        try:
            seed_sequence = generate_filter_safe_sequence(length, seed=length)
        except RuntimeError:
            seed_sequence = None

        def build_full(params: dict[str, Any]) -> Program:
            return build_dnachisel_num1_program(params)

        build_full_fn: Callable[[dict[str, Any]], Program] | None = build_full
    else:
        build_full_fn = None

    ladder = run_isolation_ladder(
        length,
        build_full_program=build_full_fn,
        num_steps=num_steps,
        seed_sequence=seed_sequence,
        use_seed_for_l2=True,
    )
    classification = classify_report(ladder)
    final_len = ladder[-1].output_length if ladder else 0
    mcmc_accepted = final_len == length

    return PreflightReport(
        fixture_id=fixture_id,
        target_length=length,
        filter_pass_rate=filter_rate,
        ladder_steps=ladder,
        classification=classification,
        mcmc_accepted_any=mcmc_accepted,
        filter_pass_samples=filter_samples,
    )


def assert_workload_feasible(report: PreflightReport) -> None:
    """Raise ValueError when preflight classifies the binding as infeasible."""

    if report.classification == "ok":
        return
    if report.classification == "platform_error":
        raise ValueError(
            f"platform error at length={report.target_length}: L0 bare MCMC failed. "
            f"{report.summary()}"
        )
    raise ValueError(
        f"binding infeasible at length={report.target_length} "
        f"(filter_pass_rate={report.filter_pass_rate:.2%}). "
        "Seed a filter-safe sequence, soften hard filters during search, or document "
        "reduced scope in the fixture README. "
        f"{report.summary()}"
    )


def assert_output_length(program: Program, expected_length: int) -> None:
    """Assert MCMC produced a full-length sequence."""

    joined = program.constructs[0].joined_sequences
    sequence = joined[0].sequence if joined else ""
    if len(sequence) != expected_length:
        raise AssertionError(
            f"binding failure: expected output length {expected_length}, got {len(sequence)}. "
            "Run preflight before blaming proto-language or scaling compute."
        )


def preflight_dnachisel_params(params: dict[str, Any], *, num_steps: int | None = None) -> None:
    """Dev-only gate: run quick preflight at params segment length."""

    length = int(params["segment_length_bp"])
    report = run_preflight(
        "dnachisel-num1",
        target_length=length,
        num_steps=num_steps or PREFLIGHT_NUM_STEPS,
        filter_samples=200,
    )
    assert_workload_feasible(report)
