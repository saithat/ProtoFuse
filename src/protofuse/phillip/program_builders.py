"""Build runnable Proto programs from reviewed methodology fixtures."""

from __future__ import annotations

import math
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from time import perf_counter
from typing import Any, Literal, cast

from proto_language.constraint import (
    ablang_perplexity_constraint,
    af3_offtarget_iptm_specificity_constraint,
    balanced_aa_constraint,
    boltz_binding_strength_constraint,
    esm2_perplexity_constraint,
    gap_gini_constraint,
    gc_content_constraint,
    max_homopolymer_constraint,
    mpnn_sequence_probability_constraint,
    overall_protein_quality_constraint,
    protein_complexity_constraint,
    protein_globularity_constraint,
    protein_length_constraint,
    protein_symmetry_ring_constraint,
    structure_composite_constraint,
    structure_ensemble_rmsd_constraint,
    structure_interface_contact_constraint,
    structure_ipae_constraint,
    structure_iptm_constraint,
    structure_pae_constraint,
    structure_plddt_constraint,
    structure_radius_gyration_constraint,
    structure_rmsd_constraint,
)
from proto_language.core import Constraint, Construct, InputSlot, Program, Segment
from proto_language.generator import (
    ESM2Generator,
    ESM2GeneratorConfig,
    Evo2Generator,
    Evo2GeneratorConfig,
    FreeBindCraftGenerator,
    FreeBindCraftGeneratorConfig,
    MPNNMutationGenerator,
    MPNNMutationGeneratorConfig,
    ProteinMPNNGenerator,
    ProteinMPNNGeneratorConfig,
    RandomNucleotideGenerator,
    RandomNucleotideGeneratorConfig,
    RandomProteinGenerator,
    RandomProteinGeneratorConfig,
    RFdiffusionMPNNBinderGenerator,
    RFdiffusionMPNNBinderGeneratorConfig,
)
from proto_language.optimizer import (
    BeamSearchOptimizer,
    BeamSearchOptimizerConfig,
    CyclingOptimizer,
    CyclingOptimizerConfig,
    MCMCOptimizer,
    MCMCOptimizerConfig,
    RejectionSamplingOptimizer,
    RejectionSamplingOptimizerConfig,
)
from proto_tools import (
    AlphaFold3Config,
    InverseFoldingStructureInput,
    PdbFetchFastaInput,
    ProteinMPNNSampleConfig,
    RFdiffusion3Config,
    is_valid_structure,
    run_pdb_fetch_fasta,
)
from proto_tools.entities.structures.selection import (
    ChainSelection,
    ResidueSelection,
)
from proto_tools.entities.structures.structure import Structure
from proto_tools.tools.masked_models.esm2.esm2_sample import ESM2_MODEL_CHECKPOINTS
from proto_tools.transforms.masking import MaskingStrategy

from protofuse.phillip.contracts import MethodologySpec
from protofuse.phillip.custom_constraints import (
    CUSTOM_METRIC_FIELDS,
    CUSTOM_METRIC_LABELS,
    CustomMetricConfig,
    CustomPaperPoolOptimizer,
    CustomTissueCodonGenerator,
    CustomTissueCodonGeneratorConfig,
    custom_cai_constraint,
    custom_cpb_constraint,
    custom_enc_constraint,
    custom_mfe_constraint,
    custom_mfe_init_constraint,
    ordered_pool_sha256,
)
from protofuse.phillip.cycling_builders import (
    bioemu_constraint_config,
    make_rfdiffusion_boltz_cycling_conditioning_fn,
)
from protofuse.phillip.dnachisel_constraints import (
    codon_usage_constraint,
    kmer_uniqueness_constraint,
    pattern_avoidance_constraint,
    reference_homology_constraint,
    sliding_window_gc_constraint,
)
from protofuse.phillip.evo2_paper_constraints import (
    evo2_paper_borzoi_l1_constraint,
    evo2_paper_enformer_l1_constraint,
)
from protofuse.phillip.genome_context import resolve_evo2_genomic_context
from protofuse.phillip.handoff_config import program_run_device, run_compiled_program
from protofuse.phillip.pair_scaling_contract import (
    PairScaledStateTMScoreConfig,
    pair_scaled_state_tmscore_constraint,
)
from protofuse.phillip.pool_optimizer import (
    PoolOptimizerConfig,
    run_pool_optimizer,
)
from protofuse.phillip.region_solver import RegionSolverConfig, run_region_local_program
from protofuse.phillip.rfd3_paper import (
    RFD3AF3PaperSuccessConfig,
    RFD3PaperBinderGenerator,
    RFD3PaperBinderGeneratorConfig,
    crop_target_structure,
    paper_binder_origin,
    rfd3_af3_paper_success_constraint,
    target_sequence_from_cropped_structure,
)
from protofuse.phillip.sequence_init import generate_filter_safe_sequence
from protofuse.phillip.state_sweep_generators import (
    FixedSequenceSweepGenerator,
    FixedSequenceSweepGeneratorConfig,
)

WorkloadTier = Literal["smoke", "full"]

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "workspaces" / "phillip" / "fixtures"

SMOKE_DEFAULTS: dict[str, int] = {
    "segment_length_bp": 100,
    "num_steps": 50,
    "max_region_passes": 1,
}

CUSTOM_SMOKE_DEFAULTS: dict[str, int] = {
    "segment_length_bp": 717,
    "n_pool": 30,
}

GPCR_CXCR4_SMOKE_DEFAULTS: dict[str, int] = {
    "binder_length_aa": 50,
    "num_samples": 2,
}

FREEBINDCRAFT_SMOKE_DEFAULTS: dict[str, int] = {
    "binder_length_aa": 50,
    "num_samples": 5,
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

SYMMETRIC_OLIGOMER_SMOKE_DEFAULTS: dict[str, int] = {
    "segment_length_aa": 60,
    "symmetry_order": 3,
    "n_pool": 100,
    "num_samples": 5,
}

PPI_INTERFACE_SMOKE_DEFAULTS: dict[str, int | str] = {
    "num_steps": 20,
    "max_region_passes": 1,
    "esm2_checkpoint": "esm2_t6_8M_UR50D",
    "proposal_generator": "esm2",
}

RFDIFFUSION3_BOLTZ2_SMOKE_DEFAULTS: dict[str, int | float] = {
    "binder_length_aa": 50,
    "num_steps": 2,
}

LIGANDMPNN_ENZYME_SMOKE_DEFAULTS: dict[str, int | str] = {
    "num_steps": 20,
    "mutations_per_step": 2,
    "esm2_checkpoint": "esm2_t6_8M_UR50D",
}

BIOEMU_ENSEMBLE_SMOKE_DEFAULTS: dict[str, int] = {
    "segment_length_aa": 80,
    "num_steps": 20,
    "bioemu_num_samples": 2,
}

BOLTZ2_STATE_SWEEP_SMOKE_DEFAULTS: dict[str, int | str | bool] = {
    "dominant_state_pdb": "4AKE",
    "alternative_state_pdb": "1AKE",
    "num_samples": 6,
    "num_results": 3,
    "max_msa_seqs": 128,
}

RFDIFFUSION3_AF3_PPI_SMOKE_DEFAULTS: dict[str, int] = {
    "num_samples": 8,
    "num_results": 4,
    "diffusion_batch_size": 2,
}

AF3_BOLTZ2_STATE_SMOKE_DEFAULTS: dict[str, int | str | bool] = {
    "dominant_state_pdb": "4AKE",
    "alternative_state_pdb": "1AKE",
    "num_samples": 2,
    "num_results": 2,
    "max_msa_seqs": 128,
}

EVO2_REGULATORY_SMOKE_DEFAULTS: dict[str, int] = {
    "segment_length_bp": 128,
    "evo2_generator_prompt_bp": 4096,
    "num_results": 1,
    "proposals_per_result": 2,
}

_SMOKE_DEFAULTS_BY_WORKLOAD: dict[str, Mapping[str, object]] = {
    "antibody_cdr_maturation": ANTIBODY_CDR_SMOKE_DEFAULTS,
    "bioemu_ensemble_filter": BIOEMU_ENSEMBLE_SMOKE_DEFAULTS,
    "boltz2_state_sweep": BOLTZ2_STATE_SWEEP_SMOKE_DEFAULTS,
    "rfdiffusion3_af3_ppi": RFDIFFUSION3_AF3_PPI_SMOKE_DEFAULTS,
    "af3_boltz2_state_sweep": AF3_BOLTZ2_STATE_SMOKE_DEFAULTS,
    "evo2_regulatory_design": EVO2_REGULATORY_SMOKE_DEFAULTS,
    "custom_egfp_pool": CUSTOM_SMOKE_DEFAULTS,
    "esm2_protein_maturation": ESM2_SMOKE_DEFAULTS,
    "freebindcraft_binder": FREEBINDCRAFT_SMOKE_DEFAULTS,
    "gpcr_cxcr4_binder": GPCR_CXCR4_SMOKE_DEFAULTS,
    "ligandmpnn_enzyme_redesign": LIGANDMPNN_ENZYME_SMOKE_DEFAULTS,
    "ppi_interface_specificity": PPI_INTERFACE_SMOKE_DEFAULTS,
    "rfdiffusion3_boltz2_binder": RFDIFFUSION3_BOLTZ2_SMOKE_DEFAULTS,
    "symmetric_oligomer_ring": SYMMETRIC_OLIGOMER_SMOKE_DEFAULTS,
}
_SEEDED_PROTEIN_WORKLOADS = {"bioemu_ensemble_filter", "esm2_protein_maturation"}

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
        "target_hotspots": list(spec.global_parameters.get("target_hotspots", [])),
        "hotspots": list(spec.global_parameters.get("hotspots", ["A94", "A259", "A284"])),
        "binder_length_aa": int(spec.global_parameters.get("binder_length_aa", 70)),
        "min_binder_length_aa": int(spec.global_parameters.get("min_binder_length_aa", 65)),
        "max_binder_length_aa": int(spec.global_parameters.get("max_binder_length_aa", 75)),
        "num_samples": int(spec.global_parameters.get("num_samples", 10)),
        "num_results": int(spec.global_parameters.get("num_results", 1)),
        "min_iptm": float(spec.global_parameters.get("min_iptm", 0.5)),
        "min_plddt": float(spec.global_parameters.get("min_plddt", 70.0)),
        "max_ipae": float(spec.global_parameters.get("max_ipae", 0.35)),
        "max_pae": float(spec.global_parameters.get("max_pae", 15.0)),
        "rmsd_inflection_angstroms": float(
            spec.global_parameters.get("rmsd_inflection_angstroms", 2.0)
        ),
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
        "symmetry_order": int(spec.global_parameters.get("symmetry_order", 6)),
        "max_symmetry_std": float(spec.global_parameters.get("max_symmetry_std", 10.0)),
        "max_globularity": float(spec.global_parameters.get("max_globularity", 20.0)),
        "binder_sequence": spec.global_parameters.get("binder_sequence", ""),
        "off_target_pdb": spec.global_parameters.get("off_target_pdb", "4RWS"),
        "off_target_chains": list(spec.global_parameters.get("off_target_chains", ["A"])),
        "interface_regions": list(spec.global_parameters.get("interface_regions", [])),
        "target_dna_sequence": spec.global_parameters.get("target_dna_sequence", ""),
        "target_motif": spec.global_parameters.get("target_motif", ""),
        "off_target_motifs": list(spec.global_parameters.get("off_target_motifs", [])),
        "dna_indices": list(spec.global_parameters.get("dna_indices", [])),
        "desired_margin": float(spec.global_parameters.get("desired_margin", 0.1)),
        "include_reverse_complement": bool(
            spec.global_parameters.get("include_reverse_complement", False)
        ),
        "proposal_generator": spec.global_parameters.get("proposal_generator", "mpnn"),
        "enzyme_pdb": spec.global_parameters.get("enzyme_pdb", "3HTB"),
        "enzyme_chain": spec.global_parameters.get("enzyme_chain", "A"),
        "active_site_positions": list(spec.global_parameters.get("active_site_positions", [])),
        "mpnn_temperature": float(spec.global_parameters.get("mpnn_temperature", 0.1)),
        "bioemu_num_samples": int(spec.global_parameters.get("bioemu_num_samples", 8)),
        "max_ensemble_rmsd": float(spec.global_parameters.get("max_ensemble_rmsd", 4.0)),
        "target_name": spec.global_parameters.get("target_name", "XylE"),
        "target_uniprot": spec.global_parameters.get("target_uniprot", "P0AEJ8"),
        "target_chain_id": spec.global_parameters.get("target_chain_id", "A"),
        "dominant_state_pdb": spec.global_parameters.get("dominant_state_pdb", "4GBY"),
        "alternative_state_pdb": spec.global_parameters.get("alternative_state_pdb", "4GBZ"),
        "protein_sequence": spec.global_parameters.get("protein_sequence", ""),
        "per_state_success_angstroms": float(
            spec.global_parameters.get("per_state_success_angstroms", 2.0)
        ),
        "subsample_msa": bool(spec.global_parameters.get("subsample_msa", True)),
        "max_msa_seqs": int(spec.global_parameters.get("max_msa_seqs", 512)),
        "sampling_steps": int(spec.global_parameters.get("sampling_steps", 200)),
        "diffusion_samples": int(spec.global_parameters.get("diffusion_samples", 1)),
        "step_scale": float(spec.global_parameters.get("step_scale", 1.5)),
        "recycling_steps": int(spec.global_parameters.get("recycling_steps", 3)),
        "boltz2_seed": spec.global_parameters.get("boltz2_seed"),
        "pair_scaling_betas": list(spec.global_parameters.get("pair_scaling_betas", [])),
        "evaluation_seeds": list(spec.global_parameters.get("evaluation_seeds", [])),
        "benchmark_targets": list(spec.global_parameters.get("benchmark_targets", [])),
        "generation_seed": int(spec.global_parameters.get("generation_seed", 0)),
        "diffusion_batch_size": int(spec.global_parameters.get("diffusion_batch_size", 8)),
        "rfdiffusion3_num_timesteps": int(
            spec.global_parameters.get("rfdiffusion3_num_timesteps", 200)
        ),
        "rfdiffusion3_step_scale": float(
            spec.global_parameters.get("rfdiffusion3_step_scale", 1.5)
        ),
        "proteinmpnn_num_sequences_per_structure": int(
            spec.global_parameters.get("proteinmpnn_num_sequences_per_structure", 4)
        ),
        "proteinmpnn_temperature": float(
            spec.global_parameters.get("proteinmpnn_temperature", 0.1)
        ),
        "af3_seed": int(spec.global_parameters.get("af3_seed", 0)),
        "af3_num_diffusion_samples": int(
            spec.global_parameters.get("af3_num_diffusion_samples", 1)
        ),
        "evo2_genomic_context": dict(spec.global_parameters.get("evo2_genomic_context", {})),
        "evo2_model_checkpoint": str(
            spec.global_parameters.get("evo2_model_checkpoint", "evo2_7b")
        ),
        "evo2_generator_prompt_bp": int(
            dict(spec.global_parameters.get("evo2_genomic_context", {})).get(
                "generator_prompt_bp", 40_960
            )
        ),
        "evo2_temperature": float(spec.global_parameters.get("evo2_temperature", 1.0)),
        "evo2_top_k": int(spec.global_parameters.get("evo2_top_k", 4)),
        "beam_length": int(spec.global_parameters.get("beam_length", 128)),
        "enformer_output_tracks": list(spec.global_parameters.get("enformer_output_tracks", [11])),
        "borzoi_output_tracks": list(spec.global_parameters.get("borzoi_output_tracks", [741])),
    }
    if tier == "smoke":
        params.update(_SMOKE_DEFAULTS_BY_WORKLOAD.get(str(workload), SMOKE_DEFAULTS))
    if workload in _SEEDED_PROTEIN_WORKLOADS:
        params["seed_sequence"] = _resolve_protein_seed_sequence(
            spec,
            tier=tier,
            segment_length_aa=int(params["segment_length_aa"]),
        )
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
    run_compiled_program(program, fixture_id="dnachisel-num1")
    return program, (perf_counter() - start) * 1000


def build_custom_egfp_program(params: dict[str, Any]) -> Program:
    """Complete released CUSTOM eGFP-to-lung pool generation and ranking workflow."""

    protein_sequence = str(params["protein_sequence"])
    coding_length = len(protein_sequence) * 3
    declared_length = int(params["segment_length_bp"])
    if declared_length != coding_length:
        raise ValueError(
            f"CUSTOM eGFP coding length is {coding_length} bp, got {declared_length}"
        )

    segment = Segment(length=coding_length, sequence_type="dna", label="egfp_cds")
    construct = Construct([segment])
    n_pool = int(params["n_pool"])
    top_k = int(params["top_k"])
    target_tissue_value = str(params["target_tissue"]).title()
    if target_tissue_value != "Lung":
        raise ValueError("The reviewed CUSTOM reproduction currently supports target_tissue='Lung'")
    target_tissue = cast(Literal["Lung"], target_tissue_value)
    generator = CustomTissueCodonGenerator(
        CustomTissueCodonGeneratorConfig(
            prompts=[protein_sequence],
            target_tissue=target_tissue,
            degree=float(params.get("degree", 0.5)),
            batch_size=n_pool,
        )
    )
    generator.assign(segment)
    metric_config = CustomMetricConfig(target_tissue=target_tissue)
    constraints = [
        Constraint(
            inputs=[segment],
            function=custom_mfe_constraint,
            function_config=metric_config,
            weight=1.0,
            label=CUSTOM_METRIC_LABELS[0],
        ),
        Constraint(
            inputs=[segment],
            function=custom_mfe_init_constraint,
            function_config=metric_config,
            weight=1.0,
            label=CUSTOM_METRIC_LABELS[1],
        ),
        Constraint(
            inputs=[segment],
            function=custom_cai_constraint,
            function_config=metric_config,
            weight=1.0,
            label=CUSTOM_METRIC_LABELS[2],
        ),
        Constraint(
            inputs=[segment],
            function=custom_cpb_constraint,
            function_config=metric_config,
            weight=1.0,
            label=CUSTOM_METRIC_LABELS[3],
        ),
        Constraint(
            inputs=[segment],
            function=custom_enc_constraint,
            function_config=metric_config,
            weight=1.0,
            label=CUSTOM_METRIC_LABELS[4],
        ),
        Constraint(
            inputs=[segment],
            function=max_homopolymer_constraint,
            function_config={"max_length": int(params["homopolymer_max"]) - 1},
            threshold=0.0,
            label="homopolymer_filter",
        ),
    ]
    optimizer = CustomPaperPoolOptimizer(
        constructs=[construct],
        generators=[generator],
        constraints=constraints,
        config=RejectionSamplingOptimizerConfig(
            num_samples=n_pool,
            num_results=top_k,
            proposal_batch_size=n_pool,
            tracking_interval=n_pool,
        ),
    )
    return Program(optimizers=[optimizer], num_results=top_k)


def run_custom_reference_parity(
    *,
    seed: int,
    tier: WorkloadTier = "full",
) -> dict[str, Any]:
    """Compare one generated CUSTOM pool against the pinned released implementation."""

    if tier != "full":
        raise ValueError("CUSTOM reference parity is a full-tier result, not a smoke diagnostic")
    if seed < 0:
        raise ValueError(f"seed must be non-negative, got {seed}")

    from custom import TissueOptimizer  # type: ignore[import-untyped]

    spec = load_fixture_spec("custom-egfp-lung")
    params = resolve_workload_params(spec, tier=tier)
    top_k = int(params["top_k"])
    expected_pool_size = int(params["n_pool"])
    built = build_custom_egfp_program(params)
    program = Program(optimizers=built.optimizers, num_results=top_k, seed=seed)
    program.run()

    optimizer = program.optimizers[0]
    if not isinstance(optimizer, CustomPaperPoolOptimizer):
        raise TypeError("expected a CustomPaperPoolOptimizer")
    generator = optimizer.generators[0]
    proposals = optimizer.segments[0].proposal_sequences
    pool = [sequence.sequence for sequence in proposals]

    metric_columns = dict(
        zip(CUSTOM_METRIC_LABELS, ("MFE", "MFEini", "CAI", "CPB", "ENC"), strict=True)
    )
    proto_metrics = {
        column: [
            float(sequence.metadata["constraints"][label]["data"][CUSTOM_METRIC_FIELDS[label]])
            for sequence in proposals
        ]
        for label, column in metric_columns.items()
    }

    reference = TissueOptimizer(
        str(params["target_tissue"]),
        n_pool=len(pool),
        degree=float(params.get("degree", 0.5)),
        prob_original=0.0,
    )
    reference.pool = list(pool)
    reference_metrics = {
        column: [float(value) for value in getattr(reference, column)()]
        for column in metric_columns.values()
    }
    # Reuse the released metric results so select_best validates ranking/filter semantics
    # without recomputing the expensive MFE columns a third time.
    for column, values in reference_metrics.items():
        setattr(reference, column, lambda values=values: values)

    homopolymer_cutoff = int(params["homopolymer_max"])
    expected = reference.select_best(
        by={
            "MFE": "min",
            "MFEini": "max",
            "CAI": "max",
            "CPB": "max",
            "ENC": "min",
        },
        homopolymers=homopolymer_cutoff,
        top=top_k,
    )
    expected_top_k = [str(sequence) for sequence in expected["Sequence"]]
    proto_top_k = [sequence.sequence for sequence in optimizer.segments[0].result_sequences]

    proto_filter = [
        int(
            sequence.metadata["constraints"]["homopolymer_filter"]["data"][
                "max_homopolymer_length"
            ]
        )
        < homopolymer_cutoff
        for sequence in proposals
    ]
    patterns = tuple(base * homopolymer_cutoff for base in "ATCG")
    reference_filter = [not any(pattern in sequence for pattern in patterns) for sequence in pool]
    filter_matches = [
        proto == released
        for proto, released in zip(proto_filter, reference_filter, strict=True)
    ]

    metric_atol = 1e-9
    metric_rtol = 1e-9
    max_abs_delta = {
        column: max(
            (abs(proto - released) for proto, released in zip(
                proto_metrics[column],
                reference_metrics[column],
                strict=True,
            )),
            default=0.0,
        )
        for column in metric_columns.values()
    }
    metric_agreement = {
        column: all(
            math.isclose(proto, released, rel_tol=metric_rtol, abs_tol=metric_atol)
            for proto, released in zip(
                proto_metrics[column],
                reference_metrics[column],
                strict=True,
            )
        )
        for column in metric_columns.values()
    }
    filter_agreement = all(filter_matches)
    ordered_top_k_identity = proto_top_k == expected_top_k
    pool_size_matches = len(pool) == expected_pool_size
    generator_seed = getattr(generator, "last_seed", None)
    passed = (
        pool_size_matches
        and isinstance(generator_seed, int)
        and all(metric_agreement.values())
        and filter_agreement
        and ordered_top_k_identity
    )

    return {
        "status": "pass" if passed else "fail",
        "passed": passed,
        "reference_package": "custom-optimizer==0.0.1",
        "tier": tier,
        "seed": seed,
        "derived_generator_seed": generator_seed,
        "pool_sha256": ordered_pool_sha256(pool),
        "pool_size": len(pool),
        "expected_pool_size": expected_pool_size,
        "top_k": top_k,
        "per_metric_max_abs_delta": max_abs_delta,
        "metric_agreement": metric_agreement,
        "filter_agreement": filter_agreement,
        "filter_disagreement_count": len(filter_matches) - sum(filter_matches),
        "ordered_top_k_identity": ordered_top_k_identity,
        "tolerances": {
            "raw_metric_atol": metric_atol,
            "raw_metric_rtol": metric_rtol,
            "filter_agreement_required": True,
            "ordered_top_k_identity_required": True,
        },
    }


def summarize_custom_egfp_program(program: Program) -> dict[str, Any]:
    """Return paper-comparable raw metrics for a completed CUSTOM program."""

    optimizer = program.optimizers[0]
    if not isinstance(optimizer, CustomPaperPoolOptimizer):
        raise TypeError("expected a CustomPaperPoolOptimizer")
    score_by_sequence = optimizer.paper_score_by_sequence
    result_sequences = program.constructs[0].segments[0].result_sequences
    rows: list[dict[str, Any]] = []
    for sequence in result_sequences:
        constraint_data = sequence.metadata["constraints"]
        row: dict[str, Any] = {
            "sequence": sequence.sequence,
            "paper_score": score_by_sequence[sequence.sequence],
        }
        for label, field in CUSTOM_METRIC_FIELDS.items():
            row[field] = float(constraint_data[label]["data"][field])
        rows.append(row)
    rows.sort(key=lambda row: float(row["paper_score"]), reverse=True)
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank

    passed_filter, pool_size = optimizer._last_filter_pass_counts["homopolymer_filter"]
    generator = optimizer.generators[0]
    return {
        "comparison": "released CUSTOM metric definitions via Proto",
        "pool_size": pool_size,
        "passed_homopolymer_filter": passed_filter,
        "selected": len(rows),
        "target_tissue": "Lung",
        "generator_seed": getattr(generator, "last_seed", None),
        "pool_sha256": optimizer.candidate_pool_sha256,
        "ranking": rows,
    }


def run_custom_egfp_lung(*, tier: WorkloadTier = "full") -> tuple[Program, float]:
    """Run the paper-scale CUSTOM eGFP-to-lung reproduction."""

    spec = load_fixture_spec("custom-egfp-lung")
    params = resolve_workload_params(spec, tier=tier)
    program = build_custom_egfp_program(params)
    start = perf_counter()
    run_compiled_program(program, fixture_id="custom-egfp-lung")
    return program, (perf_counter() - start) * 1000


def _hotspot_residue_string(hotspots: list[str]) -> str | None:
    """Convert chain-prefixed hotspot labels (e.g. A94) to FreeBindCraft residue lists."""

    if not hotspots:
        return None
    residues: list[str] = []
    for hotspot in hotspots:
        label = str(hotspot).strip()
        if not label:
            continue
        if label[0].isalpha() and len(label) > 1 and label[1:].isdigit():
            residues.append(label[1:])
        else:
            residues.append(label)
    return ",".join(residues) if residues else None


def _alphafold2_binder_structure_config(
    *,
    pdb_id: str,
    target_chains: list[str],
    hotspot_residues: str | None,
) -> dict[str, Any]:
    """Shared AF2 binder constraint config for binder+target validation."""

    return {
        "structure_tool": "alphafold2_binder",
        "alphafold2_binder_config": {
            # This field takes PDB content, unlike the generator's Structure-or-content field.
            "target_pdb": _target_structure_from_pdb(pdb_id).structure_pdb,
            "target_chains": target_chains,
            "binder_input_index": 0,
            "target_input_indices": [1],
            "binder_chain": None,
            "target_hotspot": hotspot_residues,
        },
    }


def _target_sequence_from_pdb(pdb_id: str, chain_ids: list[str]) -> str:
    fetched = run_pdb_fetch_fasta(inputs=PdbFetchFastaInput(pdb_id=pdb_id))
    for chain in fetched.chains:
        if any(chain_id in chain.chain_ids for chain_id in chain_ids):
            return str(chain.sequence)
    raise ValueError(f"no FASTA chain in {pdb_id} matching {chain_ids}")


@lru_cache(maxsize=8)
def _target_structure_from_pdb(pdb_id: str) -> Structure:
    """Fetch coordinates for a PDB accession and validate them before tool binding.

    Structure fields accept content, a path, or a `Structure` — never an accession, so an
    unresolved ID only fails once the tool parses it. RCSB omits `.pdb` for entries above
    that format's size limits, making `.cif` a distinct candidate rather than a retry.
    """

    attempts: list[str] = []
    for file_format in ("pdb", "cif"):
        try:
            structure = Structure.from_rcsb(pdb_id, file_format=file_format)
        except Exception as exc:  # noqa: BLE001 - fall through to the next candidate
            attempts.append(f"{file_format}: {exc}")
            continue
        if is_valid_structure(structure.structure):
            return structure
        attempts.append(f"{file_format}: fetched but failed structure validation")
    raise ValueError(f"could not resolve structure {pdb_id!r} from RCSB; tried: {attempts}")


def build_gpcr_cxcr4_miniprotein_program(params: dict[str, Any]) -> Program:
    """Rejection-sampling CXCR4 miniprotein binder design (Muratspahić et al. 2026)."""

    pdb_id = str(params["target_pdb"])
    target_chains = [str(item) for item in params["target_chains"]]
    hotspots = [str(item) for item in params["hotspots"]]
    binder_length = int(params["binder_length_aa"])

    target_sequence = _target_sequence_from_pdb(pdb_id, target_chains)
    binder = Segment(length=binder_length, sequence_type="protein", label="binder")
    target = Segment(sequence=target_sequence, sequence_type="protein", label="target")
    construct = Construct([binder, target])

    generator = RFdiffusionMPNNBinderGenerator(
        RFdiffusionMPNNBinderGeneratorConfig(
            target_structure=_target_structure_from_pdb(pdb_id),
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


def run_gpcr_cxcr4_miniprotein(*, tier: WorkloadTier = "full") -> tuple[Program, float]:
    """Run the CXCR4 miniprotein workload and return program plus wall time."""

    spec = load_fixture_spec("gpcr-cxcr4-miniprotein")
    params = resolve_workload_params(spec, tier=tier)
    program = build_gpcr_cxcr4_miniprotein_program(params)
    start = perf_counter()
    run_compiled_program(program, fixture_id="gpcr-cxcr4-miniprotein")
    return program, (perf_counter() - start) * 1000


def build_freebindcraft_binder_program(params: dict[str, Any]) -> Program:
    """Rejection-sampling FreeBindCraft mini-protein binder design against a fixed target."""

    pdb_id = str(params["target_pdb"])
    target_chains = [str(item) for item in params["target_chains"]]
    target_chain = ",".join(target_chains)
    hotspot_residues = _hotspot_residue_string(
        [str(item) for item in params.get("target_hotspots", params.get("hotspots", []))]
    )
    binder_length = int(params["binder_length_aa"])

    target_sequence = _target_sequence_from_pdb(pdb_id, target_chains)
    binder = Segment(length=binder_length, sequence_type="protein", label="binder")
    target = Segment(sequence=target_sequence, sequence_type="protein", label="target")
    construct = Construct([binder, target])

    generator = FreeBindCraftGenerator(
        FreeBindCraftGeneratorConfig(
            target_structure=_target_structure_from_pdb(pdb_id),
            target_chain=target_chain,
            target_hotspot_residues=hotspot_residues,
        )
    )
    generator.assign(binder)

    structure_config = _alphafold2_binder_structure_config(
        pdb_id=pdb_id,
        target_chains=target_chains,
        hotspot_residues=hotspot_residues,
    )
    constraints = [
        Constraint(
            inputs=[binder, target],
            function=structure_iptm_constraint,
            function_config=structure_config,
            threshold=float(params["min_iptm"]),
            label="iptm",
        ),
        Constraint(
            inputs=[binder, target],
            function=structure_ipae_constraint,
            function_config=structure_config,
            threshold=float(params["max_ipae"]),
            label="ipae",
        ),
        Constraint(
            inputs=[binder, target],
            function=structure_plddt_constraint,
            function_config=structure_config,
            threshold=float(params["min_plddt"]),
            label="plddt",
        ),
        Constraint(
            inputs=[binder, target],
            function=structure_rmsd_constraint,
            function_config={
                **structure_config,
                "target_structure": _target_structure_from_pdb(pdb_id),
                "inflection_point_angstroms": float(params["rmsd_inflection_angstroms"]),
            },
            weight=0.5,
            label="rmsd",
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


def run_freebindcraft_binder(*, tier: WorkloadTier = "full") -> tuple[Program, float]:
    """Run FreeBindCraft binder design and return its program and wall time."""

    spec = load_fixture_spec("freebindcraft-binder")
    params = resolve_workload_params(spec, tier=tier)
    program = build_freebindcraft_binder_program(params)
    start = perf_counter()
    run_compiled_program(program, fixture_id="freebindcraft-binder")
    return program, (perf_counter() - start) * 1000


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
            run_device=program_run_device("esm2-protein-maturation"),
        )
        return result.program, result.wall_time_ms

    program = build_esm2_protein_maturation_program(params, region_pass=0)
    start = perf_counter()
    run_compiled_program(program, fixture_id="esm2-protein-maturation")
    return program, (perf_counter() - start) * 1000


def _framework_fixed_positions(length: int, cdr_start: int, cdr_end: int) -> list[int]:
    """Return 1-indexed positions outside the 0-based, half-open active CDR."""

    return [
        index for index in range(1, length + 1) if index - 1 < cdr_start or index - 1 >= cdr_end
    ]


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
            model_checkpoint=cast(ESM2_MODEL_CHECKPOINTS, str(params["esm2_checkpoint"])),
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
            function_config={"structure_tool": "boltz2"},
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
            input_slots=[
                InputSlot(label="Query Sequence"),
                InputSlot(label="Reference Sequence"),
            ],
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
            run_device=program_run_device("antibody-cdr-maturation"),
        )
        return result.program, result.wall_time_ms

    program = build_antibody_cdr_maturation_program(params, region_pass=0)
    start = perf_counter()
    run_compiled_program(program, fixture_id="antibody-cdr-maturation")
    return program, (perf_counter() - start) * 1000


def _af3_offtarget_specificity_config(params: dict[str, Any]) -> dict[str, Any]:
    """Build AF3 off-target ipTM specificity constraint config from fixture parameters."""

    return {
        "structure_tool": "alphafold3",
        "target_dna_sequence": str(params["target_dna_sequence"]),
        "target_motif": str(params["target_motif"]),
        "off_target_motifs": [str(item) for item in params["off_target_motifs"]],
        "dna_indices": [int(item) for item in params["dna_indices"]],
        "desired_margin": float(params["desired_margin"]),
        "include_reverse_complement": bool(params["include_reverse_complement"]),
    }


def _ppi_interface_generator(
    params: dict[str, Any],
    binder: Segment,
    *,
    region_pass: int,
    fixed_positions: list[int],
) -> ESM2Generator | MPNNMutationGenerator:
    """Return ESM-2 (smoke) or MPNN (full) generator with interface-local masking."""

    mutations = int(params["mutations_per_step"]) + region_pass
    if str(params["proposal_generator"]).lower() == "mpnn":
        interface_regions = [[int(s), int(e)] for s, e in params["interface_regions"]]
        active_start, active_end = interface_regions[region_pass % len(interface_regions)]
        mutable_positions = ResidueSelection(
            chains={"A": list(range(active_start + 1, active_end + 1))},
        )
        structure = _target_structure_from_pdb(str(params["target_pdb"]))
        generator: ESM2Generator | MPNNMutationGenerator
        generator = MPNNMutationGenerator(
            MPNNMutationGeneratorConfig(
                model="proteinmpnn",
                num_mutations=mutations,
                structure_inputs=[InverseFoldingStructureInput(structure=structure)],
                mutable_positions=mutable_positions,
            )
        )
    else:
        generator = ESM2Generator(
            ESM2GeneratorConfig(
                model_checkpoint=cast(
                    ESM2_MODEL_CHECKPOINTS,
                    str(params["esm2_checkpoint"]),
                ),
                masking_strategy=MaskingStrategy(
                    num_mutations=mutations,
                    fixed_positions=fixed_positions,
                ),
            )
        )
    generator.assign(binder)
    return generator


def build_ppi_interface_specificity_program(
    params: dict[str, Any],
    *,
    region_pass: int = 0,
) -> Program:
    """Refine a binder interface for on-target versus off-target specificity."""

    binder_sequence = str(params["binder_sequence"])
    interface_regions = [[int(start), int(end)] for start, end in params["interface_regions"]]
    if not interface_regions:
        raise ValueError("interface_regions must contain at least one [start, end] interval")

    target_pdb = str(params["target_pdb"])
    off_target_pdb = str(params["off_target_pdb"])
    target_chains = [str(item) for item in params["target_chains"]]
    off_target_chains = [str(item) for item in params["off_target_chains"]]
    hotspot_residues = _hotspot_residue_string(
        [str(item) for item in params.get("target_hotspots", [])]
    )

    active_start, active_end = interface_regions[region_pass % len(interface_regions)]
    fixed_positions = _framework_fixed_positions(
        len(binder_sequence),
        active_start,
        active_end,
    )

    target_sequence = _target_sequence_from_pdb(target_pdb, target_chains)
    off_target_sequence = _target_sequence_from_pdb(off_target_pdb, off_target_chains)

    binder = Segment(sequence=binder_sequence, sequence_type="protein", label="binder")
    target = Segment(sequence=target_sequence, sequence_type="protein", label="target")
    off_target = Segment(
        sequence=off_target_sequence,
        sequence_type="protein",
        label="off_target",
    )
    construct = Construct([binder, target, off_target])

    generator = _ppi_interface_generator(
        params,
        binder,
        region_pass=region_pass,
        fixed_positions=fixed_positions,
    )

    af2_config = _alphafold2_binder_structure_config(
        pdb_id=target_pdb,
        target_chains=target_chains,
        hotspot_residues=hotspot_residues,
    )
    constraints = [
        Constraint(
            inputs=[binder, target],
            function=structure_iptm_constraint,
            function_config={"structure_tool": "alphafold3"},
            threshold=float(params["min_iptm"]),
            label="target_iptm",
        ),
        Constraint(
            inputs=[binder, target],
            function=boltz_binding_strength_constraint,
            function_config={},
            weight=1.0,
            label="boltz_binding",
        ),
        Constraint(
            inputs=[binder, target, off_target],
            function=af3_offtarget_iptm_specificity_constraint,
            function_config=_af3_offtarget_specificity_config(params),
            weight=1.0,
            label="af3_specificity",
        ),
        Constraint(
            inputs=[binder, target],
            function=structure_interface_contact_constraint,
            function_config=af2_config,
            weight=0.75,
            label="interface_contact",
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


def run_ppi_interface_specificity(*, tier: WorkloadTier = "full") -> tuple[Program, float]:
    """Run PPI interface specificity MCMC and return its program and wall time."""

    spec = load_fixture_spec("ppi-interface-specificity")
    params = resolve_workload_params(spec, tier=tier)
    if tier == "full":
        config = RegionSolverConfig(
            max_region_passes=int(params["max_region_passes"]),
            steps_per_region=int(params["num_steps"]),
            min_region_passes=int(params["max_region_passes"]),
        )
        result = run_region_local_program(
            lambda region_pass=0: build_ppi_interface_specificity_program(
                params,
                region_pass=region_pass,
            ),
            config=config,
            run_device=program_run_device("ppi-interface-specificity"),
        )
        return result.program, result.wall_time_ms

    program = build_ppi_interface_specificity_program(params, region_pass=0)
    start = perf_counter()
    run_compiled_program(program, fixture_id="ppi-interface-specificity")
    return program, (perf_counter() - start) * 1000


def build_symmetric_oligomer_ring_program(params: dict[str, Any]) -> Program:
    """Single pool-member rejection-sampling program for Cn symmetric ring monomer design."""

    length = int(params["segment_length_aa"])
    symmetry_order = int(params["symmetry_order"])
    monomer = Segment(length=length, sequence_type="protein", label="monomer")
    construct = Construct([monomer])
    generator = RandomProteinGenerator(
        RandomProteinGeneratorConfig(
            masking_strategy=MaskingStrategy(
                num_mutations=int(params.get("mutations_per_step", 3)),
            ),
        )
    )
    generator.assign(monomer)

    oligomer_inputs = [monomer] * symmetry_order
    structure_config = {"structure_tool": "esmfold"}
    constraints = [
        Constraint(
            inputs=oligomer_inputs,
            function=protein_symmetry_ring_constraint,
            function_config={
                "max_symmetry_std": float(params.get("max_symmetry_std", 10.0)),
            },
            weight=1.0,
            label="protein_symmetry_ring",
        ),
        Constraint(
            inputs=[monomer],
            function=protein_globularity_constraint,
            function_config={
                "max_globularity": float(params.get("max_globularity", 20.0)),
            },
            weight=0.75,
            label="protein_globularity",
        ),
        Constraint(
            inputs=[monomer],
            function=structure_radius_gyration_constraint,
            function_config=structure_config,
            weight=0.5,
            label="structure_radius_gyration",
        ),
        Constraint(
            inputs=oligomer_inputs,
            function=structure_composite_constraint,
            function_config=structure_config,
            weight=1.0,
            label="structure_composite",
        ),
        Constraint(
            inputs=[monomer],
            function=overall_protein_quality_constraint,
            function_config={
                "protein_quality_config": {
                    "enable_complexity": True,
                    "complexity_max_low_complexity": float(params.get("max_low_complexity", 0.2)),
                    "enable_balanced_aas": True,
                    "balanced_min_aa_frequency": float(params.get("min_aa_frequency", 0.02)),
                    "balanced_max_underrepresented_count": int(
                        params.get("max_underrepresented_count", 3)
                    ),
                }
            },
            weight=0.5,
            label="overall_protein_quality",
        ),
    ]
    optimizer = RejectionSamplingOptimizer(
        constructs=[construct],
        generators=[generator],
        constraints=constraints,
        config=RejectionSamplingOptimizerConfig(
            num_results=int(params.get("num_results", 1)),
            num_samples=int(params.get("num_samples", 10)),
        ),
    )
    return Program(optimizers=[optimizer], num_results=int(params.get("num_results", 1)))


def run_symmetric_oligomer_ring(*, tier: WorkloadTier = "full") -> tuple[Program, float]:
    """Run symmetric oligomer ring pool optimization; full tier uses n_pool=1000 C6 designs."""

    spec = load_fixture_spec("symmetric-oligomer-ring")
    params = resolve_workload_params(spec, tier=tier)
    pool_config = PoolOptimizerConfig(
        n_pool=int(params.get("n_pool", 500)),
        top_k=int(params.get("top_k", 10)),
        homopolymer_max=int(params.get("homopolymer_max", 5)),
    )
    result = run_pool_optimizer(
        lambda: build_symmetric_oligomer_ring_program(params),
        config=pool_config,
        run_device=program_run_device("symmetric-oligomer-ring"),
    )
    return result.program, result.wall_time_ms


def build_rfdiffusion3_boltz2_binder_program(params: dict[str, Any]) -> Program:
    """Cycling RFdiffusion3 bootstrap + ProteinMPNN redesign with Boltz-2 scoring."""

    pdb_id = str(params["target_pdb"])
    target_chains = [str(item) for item in params["target_chains"]]
    hotspots = [str(item) for item in params["hotspots"]]
    binder_length = int(params["binder_length_aa"])
    target_sequence = _target_sequence_from_pdb(pdb_id, target_chains)
    target_structure = _target_structure_from_pdb(pdb_id)

    binder = Segment(length=binder_length, sequence_type="protein", label="binder")
    target = Segment(sequence=target_sequence, sequence_type="protein", label="target")
    construct = Construct([binder, target])

    generator = ProteinMPNNGenerator(
        ProteinMPNNGeneratorConfig(temperature=float(params.get("mpnn_temperature", 0.1)))
    )
    generator.assign(binder)

    conditioning_fn = make_rfdiffusion_boltz_cycling_conditioning_fn(
        target_sequence=target_sequence,
        target_structure=target_structure,
        target_chains=target_chains,
        hotspots=hotspots,
        binder_length=binder_length,
    )
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
            function=structure_plddt_constraint,
            function_config={"structure_tool": "boltz2"},
            threshold=float(params["min_plddt"]),
            label="plddt",
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
    optimizer = CyclingOptimizer(
        target_segment=binder,
        constructs=[construct],
        generators=[generator],
        constraints=constraints,
        config=CyclingOptimizerConfig(
            num_steps=int(params["num_steps"]),
            num_results=int(params["num_results"]),
        ),
        conditioning_fn=conditioning_fn,
    )
    return Program(optimizers=[optimizer], num_results=int(params["num_results"]))


def run_rfdiffusion3_boltz2_binder(*, tier: WorkloadTier = "full") -> tuple[Program, float]:
    spec = load_fixture_spec("rfdiffusion3-boltz2-binder")
    params = resolve_workload_params(spec, tier=tier)
    program = build_rfdiffusion3_boltz2_binder_program(params)
    start = perf_counter()
    run_compiled_program(program, fixture_id="rfdiffusion3-boltz2-binder")
    return program, (perf_counter() - start) * 1000


def build_ligandmpnn_enzyme_redesign_program(params: dict[str, Any]) -> Program:
    """LigandMPNN MCMC on an enzyme active site with ESMFold developability gating."""

    enzyme_pdb = str(params["enzyme_pdb"])
    enzyme_chain = str(params["enzyme_chain"])
    enzyme_structure = _target_structure_from_pdb(enzyme_pdb)
    enzyme_sequence = enzyme_structure.get_chain_sequence(
        enzyme_chain,
        remove_non_standard=True,
    )
    chain_length = len(enzyme_structure.get_chain_positions(enzyme_chain))
    active_site_positions = [
        int(item) for item in params["active_site_positions"] if int(item) <= chain_length
    ]

    enzyme = Segment(sequence=enzyme_sequence, sequence_type="protein", label="enzyme")
    construct = Construct([enzyme])
    structure_input = InverseFoldingStructureInput(
        structure=enzyme_structure,
        chains_to_redesign=ChainSelection(chains=[enzyme_chain]),
        fixed_positions=ResidueSelection(
            chains={
                enzyme_chain: [
                    position
                    for position in range(1, chain_length + 1)
                    if position not in active_site_positions
                ]
            }
        ),
    )
    generator = MPNNMutationGenerator(
        MPNNMutationGeneratorConfig(
            model="ligandmpnn",
            structure_inputs=[structure_input],
            output_chain_id=enzyme_chain,
            num_mutations=int(params["mutations_per_step"]),
            mutable_positions=ResidueSelection(
                chains={enzyme_chain: active_site_positions},
            ),
            replacement_temperature=float(params["mpnn_temperature"]),
        )
    )
    generator.assign(enzyme)

    enzyme_length = len(enzyme_sequence)
    constraints = [
        Constraint(
            inputs=[enzyme],
            function=mpnn_sequence_probability_constraint,
            function_config={
                "model": "ligandmpnn",
                "structure_inputs": [structure_input],
                "output_chain_id": enzyme_chain,
            },
            weight=1.0,
            label="mpnn_probability",
        ),
        Constraint(
            inputs=[enzyme],
            function=structure_plddt_constraint,
            function_config={"structure_tool": "esmfold"},
            threshold=float(params["min_plddt"]),
            label="structure_plddt",
        ),
        Constraint(
            inputs=[enzyme],
            function=protein_length_constraint,
            function_config={"min_length": enzyme_length, "max_length": enzyme_length},
            threshold=0.0,
            label="protein_length",
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


def run_ligandmpnn_enzyme_redesign(*, tier: WorkloadTier = "full") -> tuple[Program, float]:
    spec = load_fixture_spec("ligandmpnn-enzyme-redesign")
    params = resolve_workload_params(spec, tier=tier)
    program = build_ligandmpnn_enzyme_redesign_program(params)
    start = perf_counter()
    run_compiled_program(program, fixture_id="ligandmpnn-enzyme-redesign")
    return program, (perf_counter() - start) * 1000


def build_bioemu_ensemble_filter_program(params: dict[str, Any]) -> Program:
    """ESM-2 MCMC with BioEmu ensemble RMSD filtering against an experimental structure."""

    length = int(params["segment_length_aa"])
    seed_sequence = str(params["seed_sequence"])[:length]
    target_pdb = str(params["target_pdb"])
    target_chain_id = str(params["target_chain_id"])
    target_structure = _target_structure_from_pdb(target_pdb)

    segment = Segment(sequence=seed_sequence, sequence_type="protein", label="candidate")
    construct = Construct([segment])
    generator = ESM2Generator(
        ESM2GeneratorConfig(
            masking_strategy=MaskingStrategy(num_mutations=int(params["mutations_per_step"])),
            sampling_method="iterative_refinement",
        )
    )
    generator.assign(segment)

    constraints = [
        Constraint(
            inputs=[segment],
            function=structure_ensemble_rmsd_constraint,
            function_config=bioemu_constraint_config(
                target_structure=target_structure,
                target_chain_id=target_chain_id,
                num_samples=int(params["bioemu_num_samples"]),
                max_ensemble_rmsd=float(params["max_ensemble_rmsd"]),
            ),
            threshold=float(params["max_ensemble_rmsd"]),
            label="ensemble_rmsd",
        ),
        Constraint(
            inputs=[segment],
            function=structure_plddt_constraint,
            function_config={"structure_tool": "esmfold"},
            threshold=float(params["min_plddt"]),
            label="structure_plddt",
        ),
        Constraint(
            inputs=[segment],
            function=protein_length_constraint,
            function_config={"min_length": length, "max_length": length},
            threshold=0.0,
            label="protein_length",
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


def run_bioemu_ensemble_filter(*, tier: WorkloadTier = "full") -> tuple[Program, float]:
    spec = load_fixture_spec("bioemu-ensemble-filter")
    params = resolve_workload_params(spec, tier=tier)
    program = build_bioemu_ensemble_filter_program(params)
    start = perf_counter()
    run_compiled_program(program, fixture_id="bioemu-ensemble-filter")
    return program, (perf_counter() - start) * 1000


def _boltz2_sweep_structure_config(params: dict[str, Any]) -> dict[str, Any]:
    """Boltz-2 config for inference-parameter sweeps on a fixed sequence."""

    boltz2_config: dict[str, Any] = {
        "subsample_msa": bool(params.get("subsample_msa", True)),
        "max_msa_seqs": int(params.get("max_msa_seqs", 512)),
        "diffusion_samples": int(params.get("diffusion_samples", 1)),
        "step_scale": float(params.get("step_scale", 1.5)),
        "recycling_steps": int(params.get("recycling_steps", 3)),
    }
    seed = params.get("boltz2_seed")
    if seed is not None:
        boltz2_config["seed"] = int(seed)
    return {"structure_tool": "boltz2", "boltz2_config": boltz2_config}


def _resolve_state_sweep_sequence(params: dict[str, Any]) -> str:
    explicit = params.get("protein_sequence")
    if isinstance(explicit, str) and explicit:
        return explicit
    chain_id = str(params.get("target_chain_id", "A"))
    return _target_sequence_from_pdb(str(params["dominant_state_pdb"]), [chain_id])


def build_boltz2_state_sweep_program(params: dict[str, Any]) -> Program:
    """Rejection-sampling Boltz-2 sweep on a fixed sequence scored against two PDB states."""

    sequence = _resolve_state_sweep_sequence(params)
    segment = Segment(sequence=sequence, sequence_type="protein", label="target")
    construct = Construct([segment])

    generator = FixedSequenceSweepGenerator(FixedSequenceSweepGeneratorConfig())
    generator.assign(segment)

    boltz_config = _boltz2_sweep_structure_config(params)
    inflection = float(params.get("per_state_success_angstroms", 2.0))
    dominant_structure = _target_structure_from_pdb(str(params["dominant_state_pdb"]))
    alternative_structure = _target_structure_from_pdb(str(params["alternative_state_pdb"]))

    constraints = [
        Constraint(
            inputs=[segment],
            function=structure_plddt_constraint,
            function_config=boltz_config,
            threshold=float(params["min_plddt"]),
            label="plddt",
        ),
        Constraint(
            inputs=[segment],
            function=structure_rmsd_constraint,
            function_config={
                **boltz_config,
                "target_structure": dominant_structure,
                "inflection_point_angstroms": inflection,
            },
            weight=1.0,
            label="rmsd_dominant",
        ),
        Constraint(
            inputs=[segment],
            function=structure_rmsd_constraint,
            function_config={
                **boltz_config,
                "target_structure": alternative_structure,
                "inflection_point_angstroms": inflection,
            },
            weight=1.0,
            label="rmsd_alternative",
        ),
        Constraint(
            inputs=[segment],
            function=protein_length_constraint,
            function_config={"min_length": len(sequence), "max_length": len(sequence)},
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


def run_boltz2_state_sweep(*, tier: WorkloadTier = "full") -> tuple[Program, float]:
    spec = load_fixture_spec("boltz2-state-sweep")
    params = resolve_workload_params(spec, tier=tier)
    program = build_boltz2_state_sweep_program(params)
    start = perf_counter()
    run_compiled_program(program, fixture_id="boltz2-state-sweep")
    return program, (perf_counter() - start) * 1000


def build_rfdiffusion3_af3_ppi_program(
    params: dict[str, Any],
    *,
    target_index: int = 0,
) -> Program:
    """RFD3 -> ProteinMPNN -> AF3 PPI benchmark with vector-valued model scores."""

    targets = list(params["benchmark_targets"])
    if not 0 <= target_index < len(targets):
        raise ValueError(f"target_index {target_index} outside benchmark target list")
    target_spec = dict(targets[target_index])
    pdb_id = str(target_spec["pdb_id"])
    target_chains = [str(item) for item in target_spec["target_chains"]]
    atom_hotspots = {
        str(residue): [str(atom) for atom in atoms]
        for residue, atoms in dict(target_spec["atom_hotspots"]).items()
    }
    binder_length = int(target_spec["prototype_binder_length_aa"])
    minimum_length, maximum_length = (
        int(value) for value in target_spec["paper_binder_length_range_aa"]
    )
    if not minimum_length <= binder_length <= maximum_length:
        raise ValueError(
            f"prototype binder length {binder_length} is outside paper range "
            f"{minimum_length}-{maximum_length}"
        )

    target_structure = crop_target_structure(
        _target_structure_from_pdb(pdb_id),
        str(target_spec["residue_span"]),
    )
    target_sequence = target_sequence_from_cropped_structure(target_structure, target_chains)
    binder_origin = paper_binder_origin(target_structure, atom_hotspots)
    target_contig = str(target_spec["residue_span"]).replace("/", ",")
    full_contig = f"{target_contig},/0,{binder_length}"
    binder = Segment(length=binder_length, sequence_type="protein", label="binder")
    target = Segment(sequence=target_sequence, sequence_type="protein", label="target")
    construct = Construct([binder, target])

    generation_seed = int(params["generation_seed"])
    generator = RFD3PaperBinderGenerator(
        RFD3PaperBinderGeneratorConfig(
            target_structure=target_structure,
            target_contig=full_contig,
            atom_hotspots=atom_hotspots,
            binder_origin=binder_origin,
            rfdiffusion3_config=RFdiffusion3Config(
                diffusion_batch_size=int(params["diffusion_batch_size"]),
                num_timesteps=int(params["rfdiffusion3_num_timesteps"]),
                seed=generation_seed,
                step_scale=float(params["rfdiffusion3_step_scale"]),
            ),
            proteinmpnn_config=ProteinMPNNSampleConfig(
                num_sequences_per_structure=int(params["proteinmpnn_num_sequences_per_structure"]),
                seed=generation_seed,
                temperature=float(params["proteinmpnn_temperature"]),
            ),
        )
    )
    generator.assign(binder)

    af3_success_config = RFD3AF3PaperSuccessConfig(
        alphafold3_config=AlphaFold3Config(
            seeds=[int(params["af3_seed"])],
            num_diffusion_samples=int(params["af3_num_diffusion_samples"]),
            include_pae_matrix=True,
        ),
    )
    constraints = [
        Constraint(
            inputs=[binder],
            function=mpnn_sequence_probability_constraint,
            function_config={
                "model": "proteinmpnn",
                "structure_source": "proposal_structure",
                "output_chain_id": "B",
                "score_mode": "probability_loss",
                "seed": generation_seed,
            },
            weight=1.0,
            label="proteinmpnn_probability",
        ),
        Constraint(
            inputs=[binder, target],
            function=rfd3_af3_paper_success_constraint,
            function_config=af3_success_config,
            threshold=0.0,
            label="af3_paper_success",
        ),
        Constraint(
            inputs=[binder],
            function=protein_length_constraint,
            function_config={"min_length": binder_length, "max_length": binder_length},
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
            seed=generation_seed,
        ),
    )
    return Program(optimizers=[optimizer], num_results=int(params["num_results"]))


def build_af3_boltz2_state_sweep_program(
    params: dict[str, Any],
    *,
    seed: int = 0,
    beta: float = -0.75,
    models: tuple[Literal["alphafold3", "boltz2"], ...] = ("alphafold3", "boltz2"),
) -> Program:
    """One fail-closed seed/beta slice of the paper's cross-model scaling sweep."""

    registered_betas = [float(value) for value in params["pair_scaling_betas"]]
    if beta not in registered_betas:
        raise ValueError(f"pair-scaling beta {beta} is not in the registered paper sweep")
    registered_seeds = [int(value) for value in params["evaluation_seeds"]]
    if seed not in registered_seeds:
        raise ValueError(f"pair-scaling seed {seed} is not in the registered implementation set")
    if not models or len(set(models)) != len(models):
        raise ValueError("pair-scaling models must be nonempty and unique")

    sequence = _resolve_state_sweep_sequence(params)
    segment = Segment(sequence=sequence, sequence_type="protein", label="target")
    construct = Construct([segment])
    generator = FixedSequenceSweepGenerator(FixedSequenceSweepGeneratorConfig())
    generator.assign(segment)

    dominant = _target_structure_from_pdb(str(params["dominant_state_pdb"]))
    alternative = _target_structure_from_pdb(str(params["alternative_state_pdb"]))

    constraints = []
    for model_name in models:
        constraints.extend(
            [
                Constraint(
                    inputs=[segment],
                    function=pair_scaled_state_tmscore_constraint,
                    function_config=PairScaledStateTMScoreConfig(
                        model=cast(Any, model_name),
                        beta=beta,
                        seed=seed,
                        recycling_steps=int(params["recycling_steps"]),
                        sampling_steps=int(params["sampling_steps"]),
                        diffusion_samples=int(params["diffusion_samples"]),
                        step_scale=float(params["step_scale"]),
                        max_msa_seqs=int(params["max_msa_seqs"]),
                        subsample_msa=bool(params["subsample_msa"]),
                        target_structure=dominant,
                        reference_state="dominant",
                    ),
                    weight=1.0,
                    label=f"{model_name}_scaled_one_minus_tm_dominant",
                ),
                Constraint(
                    inputs=[segment],
                    function=pair_scaled_state_tmscore_constraint,
                    function_config=PairScaledStateTMScoreConfig(
                        model=cast(Any, model_name),
                        beta=beta,
                        seed=seed,
                        recycling_steps=int(params["recycling_steps"]),
                        sampling_steps=int(params["sampling_steps"]),
                        diffusion_samples=int(params["diffusion_samples"]),
                        step_scale=float(params["step_scale"]),
                        max_msa_seqs=int(params["max_msa_seqs"]),
                        subsample_msa=bool(params["subsample_msa"]),
                        target_structure=alternative,
                        reference_state="alternative",
                    ),
                    weight=1.0,
                    label=f"{model_name}_scaled_one_minus_tm_alternative",
                ),
            ]
        )
    constraints.append(
        Constraint(
            inputs=[segment],
            function=protein_length_constraint,
            function_config={"min_length": len(sequence), "max_length": len(sequence)},
            threshold=0.0,
            label="length",
        )
    )
    optimizer = RejectionSamplingOptimizer(
        constructs=[construct],
        generators=[generator],
        constraints=constraints,
        config=RejectionSamplingOptimizerConfig(
            num_results=int(params["num_results"]),
            num_samples=int(params["num_samples"]),
            seed=seed,
        ),
    )
    return Program(optimizers=[optimizer], num_results=int(params["num_results"]))


def build_evo2_regulatory_design_program(
    params: dict[str, Any],
    *,
    morse_pattern: str,
    dot_bp: int,
    proposals_per_result: int | None = None,
) -> Program:
    """Evo 2 beam search with separate Enformer and Borzoi accessibility objectives."""

    left_flank, prompt, right_flank = resolve_evo2_genomic_context(
        dict(params["evo2_genomic_context"])
    )
    prompt_bp = int(params["evo2_generator_prompt_bp"])
    if not 0 < prompt_bp <= len(prompt):
        raise ValueError(
            f"Evo 2 prompt length must be in [1, {len(prompt)}], got {prompt_bp}"
        )
    prompt = prompt[-prompt_bp:]
    left_context = Segment(sequence=left_flank, sequence_type="dna", label="Left Flank")
    target = Segment(
        length=int(params["segment_length_bp"]),
        sequence_type="dna",
        label="Target",
    )
    right_context = Segment(
        sequence=right_flank,
        sequence_type="dna",
        label="Right Flank",
    )
    construct = Construct([left_context, target, right_context])

    generator = Evo2Generator(
        Evo2GeneratorConfig(
            prompts=[prompt],
            model_checkpoint=cast(Any, params["evo2_model_checkpoint"]),
            temperature=float(params["evo2_temperature"]),
            top_k=int(params["evo2_top_k"]),
            cached_generation=True,
            store_kv_cache=True,
            prepend_prompt=False,
        )
    )
    generator.assign(target)

    pattern_config = {
        "organism": "mouse",
        "pattern": morse_pattern,
        "dot_bp": dot_bp,
        "dash_bp": dot_bp * 3,
        "intra_symbol_gap_bp": dot_bp,
        "inter_letter_gap_bp": dot_bp * 3,
        "pattern_start_bp": 0,
    }
    constraints = [
        Constraint(
            inputs=[left_context, target, right_context],
            function=evo2_paper_enformer_l1_constraint,
            function_config={
                **pattern_config,
                "enformer_output_tracks": params["enformer_output_tracks"],
            },
            weight=0.5,
            label="enformer_pattern_l1_sum",
        ),
        Constraint(
            inputs=[left_context, target, right_context],
            function=evo2_paper_borzoi_l1_constraint,
            function_config={
                **pattern_config,
                "borzoi_output_tracks": params["borzoi_output_tracks"],
            },
            weight=0.5,
            label="borzoi_pattern_l1_sum",
        ),
    ]
    optimizer = BeamSearchOptimizer(
        target_segment=target,
        constructs=[construct],
        generators=[generator],
        constraints=constraints,
        config=BeamSearchOptimizerConfig(
            prompt=prompt,
            beam_length=int(params["beam_length"]),
            num_results=int(params["num_results"]),
            proposals_per_result=(
                int(params["proposals_per_result"])
                if proposals_per_result is None
                else proposals_per_result
            ),
            score_by="last",
            prepend_prompt=False,
            use_kv_caching=True,
            seed=int(params["generation_seed"]),
        ),
    )
    return Program(optimizers=[optimizer], num_results=int(params["num_results"]))


def run_rfdiffusion3_af3_ppi(*, tier: WorkloadTier = "full") -> tuple[Program, float]:
    """Run the first benchmark target through the reviewed RFD3/AF3 workflow."""

    spec = load_fixture_spec("rfdiffusion3-af3-ppi")
    params = resolve_workload_params(spec, tier=tier)
    program = build_rfdiffusion3_af3_ppi_program(params, target_index=0)
    start = perf_counter()
    run_compiled_program(program, fixture_id="rfdiffusion3-af3-ppi")
    return program, (perf_counter() - start) * 1000


def run_af3_boltz2_state_sweep(*, tier: WorkloadTier = "full") -> tuple[Program, float]:
    """Run the reviewed seed-zero cross-model state-recovery diagnostic."""

    spec = load_fixture_spec("af3-boltz2-state-sweep")
    params = resolve_workload_params(spec, tier=tier)
    program = build_af3_boltz2_state_sweep_program(
        params,
        seed=0,
        beta=-0.15 if tier == "smoke" else -0.75,
        models=("boltz2",) if tier == "smoke" else ("alphafold3", "boltz2"),
    )
    start = perf_counter()
    run_compiled_program(program, fixture_id="af3-boltz2-state-sweep")
    return program, (perf_counter() - start) * 1000


def run_evo2_regulatory_design(*, tier: WorkloadTier = "full") -> tuple[Program, float]:
    """Run the primary EVO2 Morse-pattern program from the reviewed collection."""

    spec = load_fixture_spec("evo2-enformer-borzoi")
    params = resolve_workload_params(spec, tier=tier)
    morse_pattern = "." if tier == "smoke" else ". ...- --- ..---"
    dot_bp = 128 if tier == "smoke" else 384
    program = build_evo2_regulatory_design_program(
        params,
        morse_pattern=morse_pattern,
        dot_bp=dot_bp,
    )
    start = perf_counter()
    run_compiled_program(program, fixture_id="evo2-enformer-borzoi")
    return program, (perf_counter() - start) * 1000
