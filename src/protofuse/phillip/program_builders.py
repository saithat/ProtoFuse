"""Build runnable Proto programs from reviewed methodology fixtures."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any, Literal

from proto_language.constraint import gc_content_constraint, max_homopolymer_constraint
from proto_language.core import Constraint, Construct, Program, Segment
from proto_language.generator import RandomNucleotideGenerator, RandomNucleotideGeneratorConfig
from proto_language.optimizer import MCMCOptimizer, MCMCOptimizerConfig
from proto_tools.transforms.masking import MaskingStrategy

from protofuse.phillip.contracts import MethodologySpec
from protofuse.phillip.custom_constraints import tissue_codon_constraint
from protofuse.phillip.dnachisel_constraints import (
    codon_usage_constraint,
    kmer_uniqueness_constraint,
    pattern_avoidance_constraint,
    reference_homology_constraint,
    sliding_window_gc_constraint,
)
from protofuse.phillip.pool_optimizer import PoolOptimizerConfig, PoolOptimizerResult, run_pool_optimizer
from protofuse.phillip.region_solver import RegionSolverConfig, run_region_local_program
from protofuse.phillip.sequence_init import generate_filter_safe_sequence

WorkloadTier = Literal["smoke", "full"]

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "workspaces" / "phillip" / "fixtures"

SMOKE_DEFAULTS: dict[str, int] = {
    "segment_length_bp": 100,
    "num_steps": 50,
    "max_region_passes": 1,
}

CUSTOM_SMOKE_DEFAULTS: dict[str, int] = {
    "segment_length_bp": 720,
    "num_steps": 20,
    "n_pool": 30,
}


def load_fixture_spec(fixture_id: str) -> MethodologySpec:
    """Load a workspace methodology fixture by ID."""

    path = FIXTURES_DIR / fixture_id / "methodology.json"
    if not path.is_file():
        raise ValueError(f"fixture not found: {fixture_id}")
    return MethodologySpec.model_validate_json(path.read_text())


def resolve_workload_params(spec: MethodologySpec, *, tier: WorkloadTier) -> dict[str, Any]:
    segment_length = int(spec.global_parameters.get("segment_length_bp", 100))
    num_steps = 100
    if spec.optimizers:
        num_steps = int(spec.optimizers[0].stopping_criteria.get("num_steps", num_steps))

    params = {
        "segment_length_bp": segment_length,
        "num_steps": num_steps,
        "proposals_per_result": int(spec.global_parameters.get("proposals_per_result", 1)),
        "max_temperature": float(spec.global_parameters.get("max_temperature", 1.0)),
        "mutations_per_step": int(spec.global_parameters.get("mutations_per_step", 3)),
        "max_region_passes": int(spec.global_parameters.get("max_region_passes", 1)),
        "inner_refinement_steps": int(spec.global_parameters.get("inner_refinement_steps", 0)),
        "max_windows_per_pass": int(spec.global_parameters.get("max_windows_per_pass", 5)),
        "min_inner_refinements_per_pass": int(
            spec.global_parameters.get("min_inner_refinements_per_pass", 0)
        ),
        "n_pool": int(spec.global_parameters.get("n_pool", 500)),
        "top_k": int(spec.global_parameters.get("top_k", 10)),
        "homopolymer_max": int(spec.global_parameters.get("homopolymer_max", 7)),
        "target_gc": float(spec.global_parameters.get("target_gc", 50.0)),
        "target_tissue": spec.global_parameters.get("target_tissue", "lung"),
        "min_gc": float(spec.global_parameters.get("min_gc", 45)),
        "max_gc": float(spec.global_parameters.get("max_gc", 55)),
    }
    if tier == "smoke":
        if spec.global_parameters.get("workload") == "custom_egfp_pool":
            params.update(CUSTOM_SMOKE_DEFAULTS)
        else:
            params.update(SMOKE_DEFAULTS)
    return params


def build_balanced_gc_program(*, tier: WorkloadTier = "full") -> Program:
    """Small GC-balance smoke program for local sanity checks."""

    del tier
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
        config=MCMCOptimizerConfig(num_results=1, proposals_per_result=1, num_steps=5),
    )
    return Program(optimizers=[optimizer], num_results=1)


def build_dnachisel_num1_program(
    params: dict[str, Any],
    *,
    region_pass: int = 0,
    inner_refinement: int = 0,
) -> Program:
    length = int(params["segment_length_bp"])
    if params.get("seed_init", True):
        seed_sequence = params.get("seed_sequence")
        if seed_sequence is None:
            seed_sequence = generate_filter_safe_sequence(length, seed=length + region_pass)
        segment = Segment(sequence=str(seed_sequence), sequence_type="dna")
    else:
        segment = Segment(length=length, sequence_type="dna")
    construct = Construct([segment])
    mutations = int(params["mutations_per_step"]) + region_pass + inner_refinement
    generator = RandomNucleotideGenerator(
        RandomNucleotideGeneratorConfig(
            masking_strategy=MaskingStrategy(num_mutations=mutations),
        )
    )
    generator.assign(segment)

    constraints = [
        Constraint(
            inputs=[segment],
            function=sliding_window_gc_constraint,
            function_config={"min_gc": 40, "max_gc": 60, "window_bp": 100},
            weight=1.0,
            label="windowed_gc_content",
        ),
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
    optimizer = MCMCOptimizer(
        constructs=[construct],
        generators=[generator],
        constraints=constraints,
        config=MCMCOptimizerConfig(
            num_results=1,
            proposals_per_result=int(params["proposals_per_result"]),
            num_steps=int(params["num_steps"]),
            max_temperature=float(params["max_temperature"]),
        ),
    )
    return Program(optimizers=[optimizer], num_results=1)


def build_dnachisel_num1(*, tier: WorkloadTier = "full") -> Program:
    spec = load_fixture_spec("dnachisel-num1")
    params = resolve_workload_params(spec, tier=tier)
    return build_dnachisel_num1_program(params, region_pass=0)


def run_dnachisel_num1(*, tier: WorkloadTier = "full") -> tuple[Program, float]:
    """Run the NUM1 fixture and return the final program plus wall time in milliseconds."""

    spec = load_fixture_spec("dnachisel-num1")
    params = resolve_workload_params(spec, tier=tier)
    if tier == "full":
        config = RegionSolverConfig(
            max_region_passes=int(params["max_region_passes"]),
            steps_per_region=int(params["num_steps"]),
            min_region_passes=int(params["max_region_passes"]),
            inner_refinement_steps=int(params["inner_refinement_steps"]),
            max_windows_per_pass=int(params["max_windows_per_pass"]),
            min_inner_refinements_per_pass=int(params["min_inner_refinements_per_pass"]),
            window_bp=100,
        )
        result = run_region_local_program(
            lambda region_pass=0, inner_refinement=0: build_dnachisel_num1_program(
                params,
                region_pass=region_pass,
                inner_refinement=inner_refinement,
            ),
            config=config,
        )
        return result.program, result.wall_time_ms

    program = build_dnachisel_num1_program(params, region_pass=0)
    start = perf_counter()
    program.run()
    return program, (perf_counter() - start) * 1000


def build_custom_egfp_program(params: dict[str, Any]) -> Program:
    """Single pool-member MCMC program for CUSTOM eGFP lung optimization."""

    segment = Segment(length=int(params["segment_length_bp"]), sequence_type="dna")
    construct = Construct([segment])
    generator = RandomNucleotideGenerator(
        RandomNucleotideGeneratorConfig(
            masking_strategy=MaskingStrategy(num_mutations=int(params["mutations_per_step"])),
        )
    )
    generator.assign(segment)
    constraints = [
        Constraint(
            inputs=[segment],
            function=tissue_codon_constraint,
            function_config={"target_tissue": params.get("target_tissue", "lung")},
            weight=1.0,
            label="tissue_codon_lung",
        ),
        Constraint(
            inputs=[segment],
            function=gc_content_constraint,
            function_config={
                "min_gc": float(params.get("min_gc", 45)),
                "max_gc": float(params.get("max_gc", 55)),
            },
            weight=0.5,
            label="gc_target",
        ),
        Constraint(
            inputs=[segment],
            function=max_homopolymer_constraint,
            function_config={"max_length": int(params.get("homopolymer_max", 6))},
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
            proposals_per_result=int(params["proposals_per_result"]),
            num_steps=int(params["num_steps"]),
            max_temperature=float(params["max_temperature"]),
        ),
    )
    return Program(optimizers=[optimizer], num_results=1)


def run_custom_egfp_lung(*, tier: WorkloadTier = "full") -> tuple[Program, float]:
    """Run CUSTOM pool optimization; full tier targets ~1-2 minute wall time."""

    spec = load_fixture_spec("custom-egfp-lung")
    params = resolve_workload_params(spec, tier=tier)
    pool_config = PoolOptimizerConfig(
        n_pool=int(params.get("n_pool", 500)),
        top_k=int(params.get("top_k", 10)),
        homopolymer_max=int(params.get("homopolymer_max", 7)),
    )
    result = run_pool_optimizer(
        lambda: build_custom_egfp_program(params),
        config=pool_config,
        target_gc=float(params.get("target_gc", 50.0)),
    )
    return result.program, result.wall_time_ms


def run_custom_egfp_lung_report(*, tier: WorkloadTier = "full") -> PoolOptimizerResult:
    """Run CUSTOM pool optimization and return the full pool report."""

    spec = load_fixture_spec("custom-egfp-lung")
    params = resolve_workload_params(spec, tier=tier)
    pool_config = PoolOptimizerConfig(
        n_pool=int(params.get("n_pool", 500)),
        top_k=int(params.get("top_k", 10)),
        homopolymer_max=int(params.get("homopolymer_max", 7)),
    )
    return run_pool_optimizer(
        lambda: build_custom_egfp_program(params),
        config=pool_config,
        target_gc=float(params.get("target_gc", 50.0)),
    )
