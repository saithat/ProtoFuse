"""Build baseline Proto programs for registered integration scenarios."""

from __future__ import annotations

from typing import Any

from proto_language.constraint import gc_content_constraint, max_homopolymer_constraint
from proto_language.core import Constraint, Construct, Program, Segment
from proto_language.generator import (
    RandomNucleotideGenerator,
    RandomNucleotideGeneratorConfig,
)
from proto_language.optimizer import MCMCOptimizer, MCMCOptimizerConfig
from proto_tools.transforms.masking import MaskingStrategy

from protofuse.integration.scenarios import (
    integrations_version_dir,
    load_scenario_manifest,
    load_scenario_methodology,
)

SCENARIO_IDS = frozenset({"balanced-gc", "dnachisel-gc-optimization"})


def build_baseline_program(scenario_id: str, *, seed: int = 0) -> Program:
    """Return a runnable baseline Program for a catalog scenario."""

    if scenario_id not in SCENARIO_IDS:
        raise ValueError(f"unsupported benchmark scenario: {scenario_id}")

    if scenario_id == "balanced-gc":
        return _build_balanced_gc(seed=seed)
    return _build_dnachisel(seed=seed)


def load_scenario_global_parameters(scenario_id: str) -> dict[str, Any]:
    scenario_dir = integrations_version_dir() / "sai" / scenario_id
    manifest = load_scenario_manifest(scenario_dir)
    spec = load_scenario_methodology(scenario_dir, manifest)
    return dict(spec.global_parameters)


def _build_balanced_gc(*, seed: int) -> Program:
    del seed
    segment = Segment(length=24, sequence_type="dna")
    construct = Construct([segment])
    generator = RandomNucleotideGenerator(RandomNucleotideGeneratorConfig())
    generator.assign(segment)
    constraints = [
        Constraint(
            inputs=[segment],
            function=gc_content_constraint,
            function_config={"min_gc": 40, "max_gc": 60},
            label="gc_content",
        ),
        Constraint(
            inputs=[segment],
            function=max_homopolymer_constraint,
            function_config={"max_length": 5},
            label="homopolymer",
        ),
    ]
    optimizer = MCMCOptimizer(
        constructs=[construct],
        generators=[generator],
        constraints=constraints,
        config=MCMCOptimizerConfig(
            num_results=1,
            proposals_per_result=1,
            num_steps=5,
            max_temperature=1.0,
        ),
    )
    return Program(optimizers=[optimizer], num_results=1)


def _build_dnachisel(*, seed: int) -> Program:
    del seed
    segment = Segment(length=100, sequence_type="dna")
    construct = Construct([segment])
    generator = RandomNucleotideGenerator(
        RandomNucleotideGeneratorConfig(
            masking_strategy=MaskingStrategy(num_mutations=3),
        )
    )
    generator.assign(segment)
    constraints = [
        Constraint(
            inputs=[segment],
            function=gc_content_constraint,
            function_config={"min_gc": 45, "max_gc": 65},
            weight=1.0,
            label="windowed_gc_content",
        ),
        Constraint(
            inputs=[segment],
            function=max_homopolymer_constraint,
            function_config={"max_length": 4},
            threshold=0.0,
            label="homopolymer",
        ),
    ]
    optimizer = MCMCOptimizer(
        constructs=[construct],
        generators=[generator],
        constraints=constraints,
        config=MCMCOptimizerConfig(
            num_results=1,
            proposals_per_result=1,
            num_steps=50,
            max_temperature=1.0,
        ),
    )
    return Program(optimizers=[optimizer], num_results=1)
