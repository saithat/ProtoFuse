"""Reviewed name-to-Proto-symbol maps for paper methodology compilation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from protofuse.phillip.contracts import MethodologySpec

REGISTRY_VERSION = "1"

DNA_BASELINE_REGISTRY: dict[str, str] = {
    "random nucleotide generator": "proto_language.generator.RandomNucleotideGenerator",
    "GC content": "proto_language.constraint.gc_content_constraint",
    "homopolymer limit": "proto_language.constraint.max_homopolymer_constraint",
    "MCMC": "proto_language.optimizer.MCMCOptimizer",
}

DNA_CHISEL_REGISTRY: dict[str, str] = {
    **DNA_BASELINE_REGISTRY,
    "windowed GC content": "proto_language.constraint.gc_content_constraint",
    "BsaI site removal": "proto_language.constraint.max_homopolymer_constraint",
    "stochastic mutation generator": "proto_language.generator.RandomNucleotideGenerator",
    "MCMC refinement": "proto_language.optimizer.MCMCOptimizer",
}

DNA_CHISEL_NUM1_REGISTRY: dict[str, str] = {
    **DNA_BASELINE_REGISTRY,
    "windowed GC content": "protofuse.phillip.dnachisel_constraints.sliding_window_gc_constraint",
    "BsaI site removal": "protofuse.phillip.dnachisel_constraints.pattern_avoidance_constraint",
    "k-mer uniqueness": "protofuse.phillip.dnachisel_constraints.kmer_uniqueness_constraint",
    "codon optimization": "protofuse.phillip.dnachisel_constraints.codon_usage_constraint",
    "stochastic mutation generator": "proto_language.generator.RandomNucleotideGenerator",
    "region-local MCMC refinement": "proto_language.optimizer.MCMCOptimizer",
}

CUSTOM_EGFP_REGISTRY: dict[str, str] = {
    **DNA_BASELINE_REGISTRY,
    "probabilistic tissue codon generator": "proto_language.generator.RandomNucleotideGenerator",
    "tissue codon optimization": "protofuse.phillip.custom_constraints.tissue_codon_constraint",
    "GC content target": "proto_language.constraint.gc_content_constraint",
    "homopolymer filter": "proto_language.constraint.max_homopolymer_constraint",
    "pool propose-score-select": "protofuse.phillip.pool_optimizer.run_pool_optimizer",
}

# --- Protein workflow registries (Wave 1+) ---

PROTEIN_SHARED_REGISTRY: dict[str, str] = {
    **DNA_BASELINE_REGISTRY,
    "MCMC refinement": "proto_language.optimizer.MCMCOptimizer",
    "ESM-2 mutation": "proto_language.generator.ESM2Generator",
    "semigreedy mutation": "proto_language.generator.SemigreedyMutationGenerator",
    "ESM-2 perplexity": "proto_language.constraint.esm2_perplexity_constraint",
    "structure pLDDT": "proto_language.constraint.structure_plddt_constraint",
    "structure PAE": "proto_language.constraint.structure_pae_constraint",
    "protein complexity": "proto_language.constraint.protein_complexity_constraint",
    "protein length": "proto_language.constraint.protein_length_constraint",
    "balanced amino acids": "proto_language.constraint.balanced_aa_constraint",
    "structure ipTM": "proto_language.constraint.structure_iptm_constraint",
    "AbLang perplexity": "proto_language.constraint.ablang_perplexity_constraint",
    "region-local MCMC refinement": "proto_language.optimizer.MCMCOptimizer",
}

ESM2_PROTEIN_MATURATION_REGISTRY: dict[str, str] = {
    **PROTEIN_SHARED_REGISTRY,
    "ESM-2 masked mutation": "proto_language.generator.ESM2Generator",
    "ESM-2 naturalness": "proto_language.constraint.esm2_perplexity_constraint",
    "ESMFold structure quality": "proto_language.constraint.structure_plddt_constraint",
    "ESMFold interface PAE": "proto_language.constraint.structure_pae_constraint",
    "developability complexity": "proto_language.constraint.protein_complexity_constraint",
    "length bounds": "proto_language.constraint.protein_length_constraint",
    "amino acid balance": "proto_language.constraint.balanced_aa_constraint",
}

ANTIBODY_CDR_MATURATION_REGISTRY: dict[str, str] = {
    **PROTEIN_SHARED_REGISTRY,
    "CDR ESM-2 mutation": "proto_language.generator.ESM2Generator",
    "AbLang naturalness": "proto_language.constraint.ablang_perplexity_constraint",
    "ESMFold interface quality": "proto_language.constraint.structure_iptm_constraint",
    "CDR complexity": "proto_language.constraint.protein_complexity_constraint",
    "gap distribution": "proto_language.constraint.gap_gini_constraint",
}

SYMMETRIC_OLIGOMER_RING_REGISTRY: dict[str, str] = {
    **PROTEIN_SHARED_REGISTRY,
    "random protein mutation": "proto_language.generator.RandomProteinGenerator",
    "ProteinMPNN inverse folding": "proto_language.generator.ProteinMPNNGenerator",
    "protein symmetry ring": "proto_language.constraint.protein_symmetry_ring_constraint",
    "protein globularity": "proto_language.constraint.protein_globularity_constraint",
    "structure radius of gyration": "proto_language.constraint.structure_radius_gyration_constraint",
    "structure composite quality": "proto_language.constraint.structure_composite_constraint",
    "overall protein quality": "proto_language.constraint.overall_protein_quality_constraint",
    "rejection sampling design filter": "proto_language.optimizer.RejectionSamplingOptimizer",
    "pool propose-score-select": "protofuse.phillip.pool_optimizer.run_pool_optimizer",
}

GPCR_CXCR4_REGISTRY: dict[str, str] = {
    "RFdiffusion MPNN binder design": "proto_language.generator.RFdiffusionMPNNBinderGenerator",
    "structure ipTM filter": "proto_language.constraint.structure_iptm_constraint",
    "Boltz2 binding strength": "proto_language.constraint.boltz_binding_strength_constraint",
    "protein length range": "proto_language.constraint.protein_length_constraint",
    "rejection sampling design filter": "proto_language.optimizer.RejectionSamplingOptimizer",
}

PPI_INTERFACE_REGISTRY: dict[str, str] = {
    **PROTEIN_SHARED_REGISTRY,
    "interface ESM-2 mutation": "proto_language.generator.ESM2Generator",
    "interface MPNN mutation": "proto_language.generator.MPNNMutationGenerator",
    "target interface ipTM": "proto_language.constraint.structure_iptm_constraint",
    "Boltz2 binding strength": "proto_language.constraint.boltz_binding_strength_constraint",
    "AF3 off-target ipTM specificity": (
        "proto_language.constraint.af3_offtarget_iptm_specificity_constraint"
    ),
    "interface contact loss": "proto_language.constraint.structure_interface_contact_constraint",
}

RFDIFFUSION3_BOLTZ2_REGISTRY: dict[str, str] = {
    **GPCR_CXCR4_REGISTRY,
    "ProteinMPNN inverse folding": "proto_language.generator.ProteinMPNNGenerator",
    "ESM-2 naturalness": "proto_language.constraint.esm2_perplexity_constraint",
    "protein globularity": "proto_language.constraint.protein_globularity_constraint",
    "structure pLDDT filter": "proto_language.constraint.structure_plddt_constraint",
    "cycling design refinement": "proto_language.optimizer.CyclingOptimizer",
}

LIGANDMPNN_ENZYME_REGISTRY: dict[str, str] = {
    **PROTEIN_SHARED_REGISTRY,
    "LigandMPNN active-site mutation": "proto_language.generator.MPNNMutationGenerator",
    "MPNN sequence probability": "proto_language.constraint.mpnn_sequence_probability_constraint",
    "structure pLDDT filter": "proto_language.constraint.structure_plddt_constraint",
    "protein length range": "proto_language.constraint.protein_length_constraint",
}

BIOEMU_ENSEMBLE_REGISTRY: dict[str, str] = {
    **PROTEIN_SHARED_REGISTRY,
    "ESM-2 masked mutation": "proto_language.generator.ESM2Generator",
    "structure ensemble RMSD": "proto_language.constraint.structure_ensemble_rmsd_constraint",
    "structure pLDDT filter": "proto_language.constraint.structure_plddt_constraint",
    "protein length range": "proto_language.constraint.protein_length_constraint",
}

BOLTZ2_STATE_SWEEP_REGISTRY: dict[str, str] = {
    **PROTEIN_SHARED_REGISTRY,
    "fixed sequence inference sweep": (
        "protofuse.phillip.state_sweep_generators.FixedSequenceSweepGenerator"
    ),
    "structure pLDDT filter": "proto_language.constraint.structure_plddt_constraint",
    "dominant state RMSD": "proto_language.constraint.structure_rmsd_constraint",
    "alternative state RMSD": "proto_language.constraint.structure_rmsd_constraint",
    "protein length range": "proto_language.constraint.protein_length_constraint",
    "rejection sampling ensemble filter": "proto_language.optimizer.RejectionSamplingOptimizer",
}

FREEBINDCRAFT_REGISTRY: dict[str, str] = {
    "FreeBindCraft binder design": "proto_language.generator.FreeBindCraftGenerator",
    "structure ipTM filter": "proto_language.constraint.structure_iptm_constraint",
    "structure interface PAE": "proto_language.constraint.structure_ipae_constraint",
    "structure pLDDT filter": "proto_language.constraint.structure_plddt_constraint",
    "structure RMSD filter": "proto_language.constraint.structure_rmsd_constraint",
    "PyRosetta interface score": "proto_language.constraint.pyrosetta_interface_constraint",
    "protein length range": "proto_language.constraint.protein_length_constraint",
    "rejection sampling design filter": "proto_language.optimizer.RejectionSamplingOptimizer",
}

REGISTRY_BY_NAME: dict[str, dict[str, str]] = {
    "baseline": DNA_BASELINE_REGISTRY,
    "dnachisel": DNA_CHISEL_REGISTRY,
    "dnachisel-num1": DNA_CHISEL_NUM1_REGISTRY,
    "custom-egfp": CUSTOM_EGFP_REGISTRY,
    "gpcr-cxcr4": GPCR_CXCR4_REGISTRY,
    "freebindcraft-binder": FREEBINDCRAFT_REGISTRY,
    "esm2-protein-maturation": ESM2_PROTEIN_MATURATION_REGISTRY,
    "antibody-cdr-maturation": ANTIBODY_CDR_MATURATION_REGISTRY,
    "symmetric-oligomer-ring": SYMMETRIC_OLIGOMER_RING_REGISTRY,
    "ppi-interface-specificity": PPI_INTERFACE_REGISTRY,
    "rfdiffusion3-boltz2-binder": RFDIFFUSION3_BOLTZ2_REGISTRY,
    "ligandmpnn-enzyme-redesign": LIGANDMPNN_ENZYME_REGISTRY,
    "bioemu-ensemble-filter": BIOEMU_ENSEMBLE_REGISTRY,
    "boltz2-state-sweep": BOLTZ2_STATE_SWEEP_REGISTRY,
}

WorkloadTier = Literal["smoke", "full"]


@dataclass(frozen=True)
class ProgramVariant:
    filename: str
    tier: WorkloadTier
    docstring: str
    builder_call: str


@dataclass(frozen=True)
class WorkloadProfile:
    workload_key: str
    fixture_id: str
    registry_name: str
    builder_symbol: str
    required_global_parameters: tuple[str, ...]
    variants: tuple[ProgramVariant, ...]


WORKLOAD_PROFILES: dict[str, WorkloadProfile] = {
    "custom_egfp_pool": WorkloadProfile(
        workload_key="custom_egfp_pool",
        fixture_id="custom-egfp-lung",
        registry_name="custom-egfp",
        builder_symbol="build_custom_egfp_program",
        required_global_parameters=("workload", "segment_length_bp", "n_pool"),
        variants=(
            ProgramVariant(
                filename="design_001.py",
                tier="full",
                docstring=(
                    "Full-tier CUSTOM eGFP lung pool member (720 bp, 100 MCMC steps).\n\n"
                    "Represents one candidate in CUSTOM's n_pool=1000 propose-score-select loop.\n"
                    "Paper: Hernandez-Alias et al., Genome Biology 2023, "
                    "10.1186/s13059-023-02868-2."
                ),
                builder_call="build_custom_egfp_program(params)",
            ),
            ProgramVariant(
                filename="design_002.py",
                tier="smoke",
                docstring="Smoke-tier CUSTOM eGFP lung pool member for fast local sanity checks.",
                builder_call="build_custom_egfp_program(params)",
            ),
        ),
    ),
    "num1_gene": WorkloadProfile(
        workload_key="num1_gene",
        fixture_id="dnachisel-num1",
        registry_name="dnachisel-num1",
        builder_symbol="build_dnachisel_num1_program",
        required_global_parameters=("workload", "segment_length_bp"),
        variants=(
            ProgramVariant(
                filename="design_001.py",
                tier="full",
                docstring=(
                    "Full-tier DNA Chisel NUM1 region-local MCMC program (936 bp, 200 steps).\n\n"
                    "Represents one region-pass / inner-refinement step in the NUM1 region-local "
                    "solver.\n"
                    "Paper: DNA Chisel, 10.1093/bioinformatics/btaa558, Figure 1 NUM1 codon "
                    "optimization."
                ),
                builder_call="build_dnachisel_num1_program(params, region_pass=0)",
            ),
            ProgramVariant(
                filename="design_002.py",
                tier="smoke",
                docstring="Smoke-tier DNA Chisel NUM1 MCMC program for fast local sanity checks.",
                builder_call="build_dnachisel_num1_program(params, region_pass=0)",
            ),
        ),
    ),
    "gpcr_cxcr4_binder": WorkloadProfile(
        workload_key="gpcr_cxcr4_binder",
        fixture_id="gpcr-cxcr4-miniprotein",
        registry_name="gpcr-cxcr4",
        builder_symbol="build_gpcr_cxcr4_miniprotein_program",
        required_global_parameters=("workload", "target_pdb", "binder_length_aa", "num_samples"),
        variants=(
            ProgramVariant(
                filename="design_001.py",
                tier="full",
                docstring=(
                    "Full-tier CXCR4 miniprotein binder design (70 aa, 10 rejection samples).\n\n"
                    "Represents one in-silico design batch from Muratspahić et al., Nature 2026,\n"
                    "10.1038/s41586-026-10656-8 (dCX1_001 CXCR4 antagonist case).\n"
                    "RFdiffusion3+MPNN replaces paper RFdiffusion v1; Boltz-2 replaces AF2 filter."
                ),
                builder_call="build_gpcr_cxcr4_miniprotein_program(params)",
            ),
            ProgramVariant(
                filename="design_002.py",
                tier="smoke",
                docstring=(
                    "Smoke-tier CXCR4 miniprotein binder design for fast GPU sanity checks."
                ),
                builder_call="build_gpcr_cxcr4_miniprotein_program(params)",
            ),
        ),
    ),
    "esm2_protein_maturation": WorkloadProfile(
        workload_key="esm2_protein_maturation",
        fixture_id="esm2-protein-maturation",
        registry_name="esm2-protein-maturation",
        builder_symbol="build_esm2_protein_maturation_program",
        required_global_parameters=("workload", "segment_length_aa"),
        variants=(
            ProgramVariant(
                filename="design_001.py",
                tier="full",
                docstring=(
                    "Full-tier ESM-2 protein maturation (129 aa lysozyme, 200 MCMC steps).\n\n"
                    "Represents one region-pass in the iterative_refinement topology matching "
                    "dnachisel-num1.\n"
                    "ESM-2 proposes masked mutations; ESMFold pLDDT/PAE gate developability."
                ),
                builder_call="build_esm2_protein_maturation_program(params, region_pass=0)",
            ),
            ProgramVariant(
                filename="design_002.py",
                tier="smoke",
                docstring=(
                    "Smoke-tier ESM-2 protein maturation (80 aa truncated eGFP, 50 MCMC steps)."
                ),
                builder_call="build_esm2_protein_maturation_program(params, region_pass=0)",
            ),
        ),
    ),
    "freebindcraft_binder": WorkloadProfile(
        workload_key="freebindcraft_binder",
        fixture_id="freebindcraft-binder",
        registry_name="freebindcraft-binder",
        builder_symbol="build_freebindcraft_binder_program",
        required_global_parameters=("workload", "target_pdb", "binder_length_aa", "num_samples"),
        variants=(
            ProgramVariant(
                filename="design_001.py",
                tier="full",
                docstring=(
                    "Full-tier FreeBindCraft binder design (70 aa, 50 rejection samples).\n\n"
                    "Represents one in-silico design batch from the staged_filter topology:\n"
                    "FreeBindCraft hallucination → AF2 validation → rejection sampling.\n"
                    "Target: CXCR4 chain A from PDB 4RWS (compact benchmark epitope)."
                ),
                builder_call="build_freebindcraft_binder_program(params)",
            ),
            ProgramVariant(
                filename="design_002.py",
                tier="smoke",
                docstring=(
                    "Smoke-tier FreeBindCraft binder design (50 aa, 5 samples) for fast GPU sanity checks."
                ),
                builder_call="build_freebindcraft_binder_program(params)",
            ),
        ),
    ),
    "symmetric_oligomer_ring": WorkloadProfile(
        workload_key="symmetric_oligomer_ring",
        fixture_id="symmetric-oligomer-ring",
        registry_name="symmetric-oligomer-ring",
        builder_symbol="build_symmetric_oligomer_ring_program",
        required_global_parameters=("workload", "segment_length_aa", "symmetry_order", "n_pool"),
        variants=(
            ProgramVariant(
                filename="design_001.py",
                tier="full",
                docstring=(
                    "Full-tier symmetric oligomer ring design (80 aa monomer, C6, n_pool=1000).\n\n"
                    "Represents one pool member in the propose-score-select loop: random-protein\n"
                    "mutation with rejection sampling under ESMFold symmetry, globularity, Rg,\n"
                    "structure-composite, and overall-protein-quality constraints."
                ),
                builder_call="build_symmetric_oligomer_ring_program(params)",
            ),
            ProgramVariant(
                filename="design_002.py",
                tier="smoke",
                docstring=(
                    "Smoke-tier symmetric oligomer ring design for fast GPU sanity checks "
                    "(60 aa monomer, C3, n_pool=100)."
                ),
                builder_call="build_symmetric_oligomer_ring_program(params)",
            ),
        ),
    ),
    "ppi_interface_specificity": WorkloadProfile(
        workload_key="ppi_interface_specificity",
        fixture_id="ppi-interface-specificity",
        registry_name="ppi-interface-specificity",
        builder_symbol="build_ppi_interface_specificity_program",
        required_global_parameters=(
            "workload",
            "binder_sequence",
            "target_pdb",
            "off_target_pdb",
        ),
        variants=(
            ProgramVariant(
                filename="design_001.py",
                tier="full",
                docstring=(
                    "Full-tier PPI interface specificity (65-aa binder, 100 MCMC steps, 2 interface passes).\n\n"
                    "Represents one region-pass in the region-local solver: MPNN mutations within\n"
                    "the active interface patch, AF3/Boltz on-target scoring, AF3 off-target\n"
                    "specificity margin, and AF2 interface contact loss vs PD-L1 (4ZQK)."
                ),
                builder_call="build_ppi_interface_specificity_program(params, region_pass=0)",
            ),
            ProgramVariant(
                filename="design_002.py",
                tier="smoke",
                docstring=(
                    "Smoke-tier PPI interface specificity for fast GPU sanity checks "
                    "(20 steps, interface patch 1, ESM-2 proposals)."
                ),
                builder_call="build_ppi_interface_specificity_program(params, region_pass=0)",
            ),
        ),
    ),
    "antibody_cdr_maturation": WorkloadProfile(
        workload_key="antibody_cdr_maturation",
        fixture_id="antibody-cdr-maturation",
        registry_name="antibody-cdr-maturation",
        builder_symbol="build_antibody_cdr_maturation_program",
        required_global_parameters=(
            "workload",
            "framework_sequence",
            "cdr_regions",
            "target_antigen_sequence",
        ),
        variants=(
            ProgramVariant(
                filename="design_001.py",
                tier="full",
                docstring=(
                    "Full-tier antibody CDR maturation (121-aa nanobody, 100 MCMC steps, 3 CDR passes).\n\n"
                    "Represents one region-pass in the region-local solver: ESM-2 mutations within\n"
                    "the active CDR, AbLang naturalness, ESMFold ipTM vs peptide antigen stub,\n"
                    "protein complexity, and gap Gini vs seed framework."
                ),
                builder_call="build_antibody_cdr_maturation_program(params, region_pass=0)",
            ),
            ProgramVariant(
                filename="design_002.py",
                tier="smoke",
                docstring=(
                    "Smoke-tier antibody CDR maturation for fast GPU sanity checks "
                    "(30 steps, CDR1 only)."
                ),
                builder_call="build_antibody_cdr_maturation_program(params, region_pass=0)",
            ),
        ),
    ),
    "rfdiffusion3_boltz2_binder": WorkloadProfile(
        workload_key="rfdiffusion3_boltz2_binder",
        fixture_id="rfdiffusion3-boltz2-binder",
        registry_name="rfdiffusion3-boltz2-binder",
        builder_symbol="build_rfdiffusion3_boltz2_binder_program",
        required_global_parameters=("workload", "target_pdb", "binder_length_aa", "num_steps"),
        variants=(
            ProgramVariant(
                filename="design_001.py",
                tier="full",
                docstring=(
                    "Full-tier RFdiffusion3+Boltz-2 cycling binder (70 aa, 10 cycles).\n\n"
                    "Bootstrap via RFdiffusion3+MPNN, then ProteinMPNN redesign conditioned on\n"
                    "Boltz-2 folds against CXCR4 chain A (PDB 4RWS)."
                ),
                builder_call="build_rfdiffusion3_boltz2_binder_program(params)",
            ),
            ProgramVariant(
                filename="design_002.py",
                tier="smoke",
                docstring="Smoke-tier RFdiffusion3+Boltz-2 cycling binder (50 aa, 2 cycles).",
                builder_call="build_rfdiffusion3_boltz2_binder_program(params)",
            ),
        ),
    ),
    "ligandmpnn_enzyme_redesign": WorkloadProfile(
        workload_key="ligandmpnn_enzyme_redesign",
        fixture_id="ligandmpnn-enzyme-redesign",
        registry_name="ligandmpnn-enzyme-redesign",
        builder_symbol="build_ligandmpnn_enzyme_redesign_program",
        required_global_parameters=("workload", "enzyme_pdb", "enzyme_chain", "active_site_positions"),
        variants=(
            ProgramVariant(
                filename="design_001.py",
                tier="full",
                docstring=(
                    "Full-tier LigandMPNN enzyme active-site MCMC (3HTB, 100 steps).\n\n"
                    "Mutates ligand-aware active-site ordinals on a fixed holo backbone with\n"
                    "LigandMPNN probability and ESMFold pLDDT gates."
                ),
                builder_call="build_ligandmpnn_enzyme_redesign_program(params)",
            ),
            ProgramVariant(
                filename="design_002.py",
                tier="smoke",
                docstring="Smoke-tier LigandMPNN enzyme redesign (20 MCMC steps).",
                builder_call="build_ligandmpnn_enzyme_redesign_program(params)",
            ),
        ),
    ),
    "bioemu_ensemble_filter": WorkloadProfile(
        workload_key="bioemu_ensemble_filter",
        fixture_id="bioemu-ensemble-filter",
        registry_name="bioemu-ensemble-filter",
        builder_symbol="build_bioemu_ensemble_filter_program",
        required_global_parameters=("workload", "segment_length_aa", "target_pdb"),
        variants=(
            ProgramVariant(
                filename="design_001.py",
                tier="full",
                docstring=(
                    "Full-tier BioEmu ensemble filter (129 aa lysozyme, 100 MCMC steps).\n\n"
                    "ESM-2 proposals filtered by BioEmu ensemble RMSD vs lysozyme PDB 2LYZ\n"
                    "and ESMFold developability."
                ),
                builder_call="build_bioemu_ensemble_filter_program(params)",
            ),
            ProgramVariant(
                filename="design_002.py",
                tier="smoke",
                docstring=(
                    "Smoke-tier BioEmu ensemble filter (80 aa truncated lysozyme, 20 steps, 2 BioEmu samples)."
                ),
                builder_call="build_bioemu_ensemble_filter_program(params)",
            ),
        ),
    ),
    "boltz2_state_sweep": WorkloadProfile(
        workload_key="boltz2_state_sweep",
        fixture_id="boltz2-state-sweep",
        registry_name="boltz2-state-sweep",
        builder_symbol="build_boltz2_state_sweep_program",
        required_global_parameters=(
            "workload",
            "dominant_state_pdb",
            "alternative_state_pdb",
            "num_samples",
        ),
        variants=(
            ProgramVariant(
                filename="design_001.py",
                tier="full",
                docstring=(
                    "Full-tier Boltz-2 alternative-state sweep (XylE 491 aa, 55 draws).\n\n"
                    "Fixed E. coli XylE sequence; repeated Boltz-2 predictions with MSA\n"
                    "subsampling scored against inward 4GBY and outward 4GBZ references\n"
                    "(IOMemP transporter benchmark). Sai fusion target: boltz2-prediction\n"
                    "per sweep draw with labelled RMSD ground truth."
                ),
                builder_call="build_boltz2_state_sweep_program(params)",
            ),
            ProgramVariant(
                filename="design_002.py",
                tier="smoke",
                docstring=(
                    "Smoke-tier Boltz-2 state sweep (adenylate kinase 214 aa, 6 draws).\n\n"
                    "Soluble domain-motion proxy for fast GPU sanity checks before the\n"
                    "full XylE IOMemP transporter benchmark."
                ),
                builder_call="build_boltz2_state_sweep_program(params)",
            ),
        ),
    ),
}


def lookup_registry(name: str) -> dict[str, str]:
    try:
        return REGISTRY_BY_NAME[name]
    except KeyError as exc:
        known = ", ".join(sorted(REGISTRY_BY_NAME))
        raise ValueError(f"unknown registry {name!r}; expected one of: {known}") from exc


def profile_for_spec(spec: MethodologySpec) -> WorkloadProfile:
    workload = spec.global_parameters.get("workload")
    if not isinstance(workload, str) or not workload:
        raise ValueError("methodology global_parameters.workload must be a non-empty string")
    try:
        profile = WORKLOAD_PROFILES[workload]
    except KeyError as exc:
        known = ", ".join(sorted(WORKLOAD_PROFILES))
        raise ValueError(f"no workload profile for {workload!r}; expected one of: {known}") from exc
    missing = [
        key for key in profile.required_global_parameters if key not in spec.global_parameters
    ]
    if missing:
        raise ValueError(f"methodology missing required global_parameters: {missing}")
    return profile


def profile_for_fixture(fixture_id: str) -> WorkloadProfile:
    matches = [
        profile for profile in WORKLOAD_PROFILES.values() if profile.fixture_id == fixture_id
    ]
    if len(matches) != 1:
        known = ", ".join(sorted(item.fixture_id for item in WORKLOAD_PROFILES.values()))
        raise ValueError(f"no unique workload profile for fixture {fixture_id!r}; known: {known}")
    return matches[0]
