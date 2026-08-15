"""Build runnable Proto programs from reviewed methodology fixtures."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any, Literal

from proto_language.constraint import (
    ablang_perplexity_constraint,
    balanced_aa_constraint,
    boltz_binding_strength_constraint,
    esm2_perplexity_constraint,
    gap_gini_constraint,
    gc_content_constraint,
    max_homopolymer_constraint,
    protein_complexity_constraint,
    protein_length_constraint,
    structure_iptm_constraint,
    structure_pae_constraint,
    structure_plddt_constraint,
)
from proto_language.core import Constraint, Construct, Program, Segment
from proto_language.generator import (
    ESM2Generator,
    ESM2GeneratorConfig,
    RandomNucleotideGenerator,
    RandomNucleotideGeneratorConfig,
    RFdiffusionMPNNBinderGenerator,
    RFdiffusionMPNNBinderGeneratorConfig,
)
from proto_language.optimizer import (
    MCMCOptimizer,
    MCMCOptimizerConfig,
    RejectionSamplingOptimizer,
    RejectionSamplingOptimizerConfig,
)
from proto_tools import PdbFetchFastaInput, run_pdb_fetch_fasta
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

GPCR_CXCR4_SMOKE_DEFAULTS: dict[str, int] = {
    "binder_length_aa": 50,
    "num_samples": 2,
}

ANTIBODY_CDR_SMOKE_DEFAULTS: dict[str, int | str] = {
    "num_steps": 30,
    "max_region_passes": 1,
    "esm2_checkpoint": "esm2_t6_8M_UR50D",
}

ESM2_SMOKE_DEFAULTS: dict[str, int] = {
    "segment_length_aa": 80,
    "num_steps": 50,
    "max_region_passes": 1,
}

GFP_SEQUENCE = (
    "MSKGEELFTGVVPILVELDGDVNGHKFSVSGEGEGDATYGKLTLKFICTTGKLPVPWPTLVTTFSYGVQCFSRYPDHMK"
    "QHDFFKSAMPEGYVQERTIFFKDDGNYKTRAEVKFEGDTLVNRIELKGIDFKEDGNILGHKLEYNYNSHNVYIMADKQKNG"
    "IKVNFKIRHNIEDGSVQLADHYQQNTPIGDGPVLLPDNHYLSTQSALSKDPNEKRDHMVLLEFVTAAGITHGMDELYK"
)
LYSOZYME_SEQUENCE = (
    "KVFGRCELAAAMKRHGLDNYRGYSLGNWVCAAKFESNFNTQATNRNTDGSTDYGILQINSRWWCNDGRTPGSRNLCNIPCS"
    "ALLSSDITASVNCAKKIVSDGNGMNAWVAWRNRCKGTDVQAWIRGCRL"
)


def load_fixture_spec(fixture_id: str) -> MethodologySpec:
    """Load a workspace methodology fixture by ID."""

    path = FIXTURES_DIR / fixture_id / "methodology.json"
    if not path.is_file():
        raise ValueError(f"fixture not found: {fixture_id}")
    return MethodologySpec.model_validate_json(path.read_text())


def _resolve_protein_seed_sequence(
    spec: MethodologySpec,
    *,
    tier: WorkloadTier,
    segment_length_aa: int,
) -> str:
    explicit = spec.global_parameters.get("seed_sequence")
    if isinstance(explicit, str) and explicit:
        return explicit[:segment_length_aa]

    gfp = str(spec.global_parameters.get("seed_sequence_gfp", GFP_SEQUENCE))
    lysozyme = str(spec.global_parameters.get("seed_sequence_lysozyme", LYSOZYME_SEQUENCE))
    base = gfp if tier == "smoke" else lysozyme
    return base[:segment_length_aa]


def resolve_workload_params(spec: MethodologySpec, *, tier: WorkloadTier) -> dict[str, Any]:
    workload = spec.global_parameters.get("workload")
    segment_length = int(spec.global_parameters.get("segment_length_bp", 100))
    segment_length_aa = int(spec.global_parameters.get("segment_length_aa", 129))
    num_steps = 100
    if spec.optimizers:
        num_steps = int(spec.optimizers[0].stopping_criteria.get("num_steps", num_steps))

    params = {
        "segment_length_bp": segment_length,
        "segment_length_aa": segment_length_aa,
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
        "target_pdb": spec.global_parameters.get("target_pdb", "4RWS"),
        "target_chains": list(spec.global_parameters.get("target_chains", ["A"])),
        "hotspots": list(spec.global_parameters.get("hotspots", ["A94", "A259", "A284"])),
        "binder_length_aa": int(spec.global_parameters.get("binder_length_aa", 70)),
        "min_binder_length_aa": int(spec.global_parameters.get("min_binder_length_aa", 65)),
        "max_binder_length_aa": int(spec.global_parameters.get("max_binder_length_aa", 75)),
        "num_samples": int(spec.global_parameters.get("num_samples", 10)),
        "num_results": int(spec.global_parameters.get("num_results", 1)),
        "min_iptm": float(spec.global_parameters.get("min_iptm", 0.5)),
        "min_plddt": float(spec.global_parameters.get("min_plddt", 70.0)),
        "max_pae": float(spec.global_parameters.get("max_pae", 15.0)),
        "esm2_temperature": float(spec.global_parameters.get("esm2_temperature", 1.0)),
        "max_low_complexity": float(spec.global_parameters.get("max_low_complexity", 0.2)),
        "min_aa_frequency": float(spec.global_parameters.get("min_aa_frequency", 0.02)),
        "max_underrepresented_count": int(
            spec.global_parameters.get("max_underrepresented_count", 3)
        ),
        "framework_sequence": spec.global_parameters.get("framework_sequence", ""),
        "cdr_regions": list(spec.global_parameters.get("cdr_regions", [])),
        "target_antigen_sequence": spec.global_parameters.get("target_antigen_sequence", ""),
        "max_gap_gini": float(spec.global_parameters.get("max_gap_gini", 0.15)),
        "esm2_checkpoint": spec.global_parameters.get("esm2_checkpoint", "esm2_t33_650M_UR50D"),
    }
    if workload == "esm2_protein_maturation":
        params["seed_sequence"] = _resolve_protein_seed_sequence(
            spec,
            tier=tier,
            segment_length_aa=int(params["segment_length_aa"]),
        )
    if tier == "smoke":
        if workload == "custom_egfp_pool":
            params.update(CUSTOM_SMOKE_DEFAULTS)
        elif workload == "gpcr_cxcr4_binder":
            params.update(GPCR_CXCR4_SMOKE_DEFAULTS)
        elif workload == "esm2_protein_maturation":
            params.update(ESM2_SMOKE_DEFAULTS)
            params["seed_sequence"] = _resolve_protein_seed_sequence(
                spec,
                tier="smoke",
                segment_length_aa=int(params["segment_length_aa"]),
            )
        elif workload == "antibody_cdr_maturation":
            params.update(ANTIBODY_CDR_SMOKE_DEFAULTS)
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


def _cxcr4_target_sequence(pdb_id: str, chain_ids: list[str]) -> str:
    fetched = run_pdb_fetch_fasta(inputs=PdbFetchFastaInput(pdb_id=pdb_id))
    for chain in fetched.chains:
        if any(chain_id in chain.chain_ids for chain_id in chain_ids):
            return chain.sequence
    raise ValueError(f"no FASTA chain in {pdb_id} matching {chain_ids}")


def build_gpcr_cxcr4_miniprotein_program(params: dict[str, Any]) -> Program:
    """Rejection-sampling CXCR4 miniprotein binder design (Muratspahić et al. 2026)."""

    pdb_id = str(params["target_pdb"])
    target_chains = [str(item) for item in params["target_chains"]]
    hotspots = [str(item) for item in params["hotspots"]]
    binder_length = int(params["binder_length_aa"])

    target_sequence = _cxcr4_target_sequence(pdb_id, target_chains)
    binder = Segment(length=binder_length, sequence_type="protein", label="binder")
    target = Segment(sequence=target_sequence, sequence_type="protein", label="target")
    construct = Construct([binder, target])

    generator = RFdiffusionMPNNBinderGenerator(
        RFdiffusionMPNNBinderGeneratorConfig(
            target_structure=pdb_id,
            target_chains=target_chains,
            hotspots=hotspots,
        )
    )
    generator.assign(binder)

    constraints = [
        Constraint(
            inputs=[binder, target],
            function=structure_iptm_constraint,
            function_config={"structure_tool": "boltz2"},
            threshold=float(params["min_iptm"]),
            label="iptm",
        ),
        Constraint(
            inputs=[binder, target],
            function=boltz_binding_strength_constraint,
            function_config={},
            weight=1.0,
            label="binding",
        ),
        Constraint(
            inputs=[binder],
            function=protein_length_constraint,
            function_config={
                "min_length": int(params["min_binder_length_aa"]),
                "max_length": int(params["max_binder_length_aa"]),
            },
            threshold=0.0,
            label="length",
        ),
    ]
    optimizer = RejectionSamplingOptimizer(
        constructs=[construct],
        generators=[generator],
        constraints=constraints,
        config=RejectionSamplingOptimizerConfig(
            num_results=int(params["num_results"]),
            num_samples=int(params["num_samples"]),
        ),
    )
    return Program(optimizers=[optimizer], num_results=int(params["num_results"]))


def build_esm2_protein_maturation_program(
    params: dict[str, Any],
    *,
    region_pass: int = 0,
    inner_refinement: int = 0,
) -> Program:
    """ESM-2 MCMC maturation of a seed protein with ESMFold developability constraints."""

    length = int(params["segment_length_aa"])
    seed_sequence = str(params["seed_sequence"])[:length]
    segment = Segment(sequence=seed_sequence, sequence_type="protein")
    construct = Construct([segment])
    mutations = int(params["mutations_per_step"]) + region_pass + inner_refinement
    generator = ESM2Generator(
        ESM2GeneratorConfig(
            masking_strategy=MaskingStrategy(num_mutations=mutations),
            sampling_method="iterative_refinement",
        )
    )
    generator.assign(segment)

    structure_config = {"structure_tool": "esmfold"}
    constraints = [
        Constraint(
            inputs=[segment],
            function=esm2_perplexity_constraint,
            function_config={"temperature": float(params["esm2_temperature"])},
            weight=1.0,
            label="esm2_perplexity",
        ),
        Constraint(
            inputs=[segment],
            function=structure_plddt_constraint,
            function_config=structure_config,
            threshold=float(params["min_plddt"]),
            label="structure_plddt",
        ),
        Constraint(
            inputs=[segment],
            function=structure_pae_constraint,
            function_config=structure_config,
            weight=0.75,
            label="structure_pae",
        ),
        Constraint(
            inputs=[segment],
            function=protein_complexity_constraint,
            function_config={"max_low_complexity": float(params["max_low_complexity"])},
            weight=0.5,
            label="protein_complexity",
        ),
        Constraint(
            inputs=[segment],
            function=protein_length_constraint,
            function_config={"min_length": length, "max_length": length},
            threshold=0.0,
            label="protein_length",
        ),
        Constraint(
            inputs=[segment],
            function=balanced_aa_constraint,
            function_config={
                "min_aa_frequency": float(params["min_aa_frequency"]),
                "max_underrepresented_count": int(params["max_underrepresented_count"]),
            },
            weight=0.5,
            label="balanced_aa",
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


def build_esm2_protein_maturation(*, tier: WorkloadTier = "full") -> Program:
    spec = load_fixture_spec("esm2-protein-maturation")
    params = resolve_workload_params(spec, tier=tier)
    return build_esm2_protein_maturation_program(params, region_pass=0)


def run_esm2_protein_maturation(*, tier: WorkloadTier = "full") -> tuple[Program, float]:
    """Run ESM-2 protein maturation; full tier uses region-local MCMC orchestration."""

    spec = load_fixture_spec("esm2-protein-maturation")
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
            lambda region_pass=0, inner_refinement=0: build_esm2_protein_maturation_program(
                params,
                region_pass=region_pass,
                inner_refinement=inner_refinement,
            ),
            config=config,
        )
        return result.program, result.wall_time_ms

    program = build_esm2_protein_maturation_program(params, region_pass=0)
    start = perf_counter()
    program.run()
    return program, (perf_counter() - start) * 1000


def _framework_fixed_positions(length: int, cdr_start: int, cdr_end: int) -> list[int]:
    """Return 1-indexed positions outside the active CDR (0-based half-open [cdr_start, cdr_end))."""

    return [index for index in range(1, length + 1) if index - 1 < cdr_start or index - 1 >= cdr_end]


def build_antibody_cdr_maturation_program(
    params: dict[str, Any],
    *,
    region_pass: int = 0,
) -> Program:
    """Region-local MCMC maturation of antibody CDRs with ESM-2 proposals."""

    framework_sequence = str(params["framework_sequence"])
    cdr_regions = [[int(start), int(end)] for start, end in params["cdr_regions"]]
    if not cdr_regions:
        raise ValueError("cdr_regions must contain at least one [start, end] interval")

    antigen_sequence = str(params["target_antigen_sequence"])
    active_start, active_end = cdr_regions[region_pass % len(cdr_regions)]
    fixed_positions = _framework_fixed_positions(
        len(framework_sequence),
        active_start,
        active_end,
    )

    antibody = Segment(sequence=framework_sequence, sequence_type="protein", label="antibody")
    antigen = Segment(sequence=antigen_sequence, sequence_type="protein", label="antigen")
    reference = Segment(sequence=framework_sequence, sequence_type="protein", label="reference")
    construct = Construct([antibody, antigen, reference])

    generator = ESM2Generator(
        ESM2GeneratorConfig(
            model_checkpoint=str(params["esm2_checkpoint"]),
            masking_strategy=MaskingStrategy(
                num_mutations=int(params["mutations_per_step"]) + region_pass,
                fixed_positions=fixed_positions,
            ),
        )
    )
    generator.assign(antibody)

    constraints = [
        Constraint(
            inputs=[antibody],
            function=ablang_perplexity_constraint,
            function_config={"temperature": 1.0},
            weight=1.0,
            label="ablang_naturalness",
        ),
        Constraint(
            inputs=[antibody, antigen],
            function=structure_iptm_constraint,
            function_config={"structure_tool": "esmfold"},
            threshold=float(params["min_iptm"]),
            label="interface_iptm",
        ),
        Constraint(
            inputs=[antibody],
            function=protein_complexity_constraint,
            function_config={"max_low_complexity": float(params["max_low_complexity"])},
            weight=0.5,
            label="cdr_complexity",
        ),
        Constraint(
            inputs=[antibody, reference],
            function=gap_gini_constraint,
            function_config={
                "max_gap_gini": float(params["max_gap_gini"]),
                "trim_alignment": True,
            },
            weight=0.5,
            label="gap_gini",
        ),
    ]
    optimizer = MCMCOptimizer(
        constructs=[construct],
        generators=[generator],
        constraints=constraints,
        config=MCMCOptimizerConfig(
            num_results=int(params["num_results"]),
            proposals_per_result=int(params["proposals_per_result"]),
            num_steps=int(params["num_steps"]),
            max_temperature=float(params["max_temperature"]),
        ),
    )
    return Program(optimizers=[optimizer], num_results=int(params["num_results"]))


def run_antibody_cdr_maturation(*, tier: WorkloadTier = "full") -> tuple[Program, float]:
    """Run antibody CDR maturation and return the final program plus wall time in milliseconds."""

    spec = load_fixture_spec("antibody-cdr-maturation")
    params = resolve_workload_params(spec, tier=tier)
    if tier == "full":
        config = RegionSolverConfig(
            max_region_passes=int(params["max_region_passes"]),
            steps_per_region=int(params["num_steps"]),
            min_region_passes=int(params["max_region_passes"]),
        )
        result = run_region_local_program(
            lambda region_pass=0: build_antibody_cdr_maturation_program(
                params,
                region_pass=region_pass,
            ),
            config=config,
        )
        return result.program, result.wall_time_ms

    program = build_antibody_cdr_maturation_program(params, region_pass=0)
    start = perf_counter()
    program.run()
    return program, (perf_counter() - start) * 1000


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
