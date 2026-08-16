"""Reviewed finalize metadata for Phillip → Sai program collection handoffs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from protofuse.checkpoints import run_program

if TYPE_CHECKING:
    from proto_language.core import Program

CompileDevice = Literal["local", "modal"]
ProgramRunDevice = Literal["modal"] | None


@dataclass(frozen=True)
class HandoffConfig:
    fixture_id: str
    methodology_id: str
    seed_policy: str
    compile_device: CompileDevice = "local"
    requires_paper_source: bool = False


HANDOFF_CONFIGS: dict[str, HandoffConfig] = {
    "dnachisel-num1": HandoffConfig(
        fixture_id="dnachisel-num1",
        methodology_id="dnachisel-v2",
        seed_policy="filter-safe random init seeded by length + region_pass",
        compile_device="local",
    ),
    "custom-egfp-lung": HandoffConfig(
        fixture_id="custom-egfp-lung",
        methodology_id="custom-egfp-v2",
        seed_policy="caller supplied; one derived NumPy seed drives the released CUSTOM pool",
        compile_device="local",
    ),
    "esm2-protein-maturation": HandoffConfig(
        fixture_id="esm2-protein-maturation",
        methodology_id="esm2-protein-maturation-v1",
        seed_policy="seed protein from fixture global_parameters; smoke uses truncated eGFP",
        compile_device="modal",
    ),
    "antibody-cdr-maturation": HandoffConfig(
        fixture_id="antibody-cdr-maturation",
        methodology_id="antibody-cdr-maturation-v1",
        seed_policy="ESM-2 seeds from framework_sequence; CDR masking via region_pass",
        compile_device="modal",
    ),
    "symmetric-oligomer-ring": HandoffConfig(
        fixture_id="symmetric-oligomer-ring",
        methodology_id="symmetric-oligomer-ring-v1",
        seed_policy="random-protein init per pool member; symmetry order from fixture parameters",
        compile_device="modal",
    ),
    "gpcr-cxcr4-miniprotein": HandoffConfig(
        fixture_id="gpcr-cxcr4-miniprotein",
        methodology_id="gpcr-cxcr4-v1",
        seed_policy=(
            "RFdiffusion3/ProteinMPNN seeds from generator; rejection sampling is stateless"
        ),
        compile_device="modal",
        requires_paper_source=True,
    ),
    "freebindcraft-binder": HandoffConfig(
        fixture_id="freebindcraft-binder",
        methodology_id="freebindcraft-binder-v1",
        seed_policy=(
            "FreeBindCraft seeds from generator; rejection sampling is stateless per batch"
        ),
        compile_device="modal",
    ),
    "ppi-interface-specificity": HandoffConfig(
        fixture_id="ppi-interface-specificity",
        methodology_id="ppi-interface-specificity-v1",
        seed_policy="binder_sequence seed; interface masking via region_pass",
        compile_device="modal",
    ),
    "rfdiffusion3-boltz2-binder": HandoffConfig(
        fixture_id="rfdiffusion3-boltz2-binder",
        methodology_id="rfdiffusion3-boltz2-binder-v1",
        seed_policy="RFdiffusion3 bootstrap then Boltz-2-conditioned ProteinMPNN cycles",
        compile_device="modal",
    ),
    "ligandmpnn-enzyme-redesign": HandoffConfig(
        fixture_id="ligandmpnn-enzyme-redesign",
        methodology_id="ligandmpnn-enzyme-redesign-v1",
        seed_policy="enzyme sequence from holo PDB 3HTB; active-site masking via ResidueSelection",
        compile_device="modal",
    ),
    "bioemu-ensemble-filter": HandoffConfig(
        fixture_id="bioemu-ensemble-filter",
        methodology_id="bioemu-ensemble-filter-v1",
        seed_policy="lysozyme seed sequence; smoke truncates to 80 aa",
        compile_device="modal",
    ),
    "boltz2-state-sweep": HandoffConfig(
        fixture_id="boltz2-state-sweep",
        methodology_id="boltz2-state-sweep-v1",
        seed_policy=(
            "fixed benchmark sequence; Boltz-2 stochasticity from subsample_msa and implicit seeds"
        ),
        compile_device="modal",
    ),
    "rfdiffusion3-af3-ppi": HandoffConfig(
        fixture_id="rfdiffusion3-af3-ppi",
        methodology_id="rfdiffusion3-af3-ppi-v2",
        seed_policy=(
            "paper generation seeds not reported; prototype fixes RFdiffusion3 and "
            "ProteinMPNN seed 0 and AlphaFold3 seed 0; paired full/fused arms must match"
        ),
        compile_device="modal",
    ),
    "af3-boltz2-state-sweep": HandoffConfig(
        fixture_id="af3-boltz2-state-sweep",
        methodology_id="af3-boltz2-state-sweep-v3",
        seed_policy=(
            "paper reports five seeds without values; the target-level protocol slice uses "
            "implementation seeds 0 through 4 across ten beta settings and five draws per "
            "setting, paired identically across full/fused arms"
        ),
        compile_device="modal",
    ),
    "evo2-enformer-borzoi": HandoffConfig(
        fixture_id="evo2-enformer-borzoi",
        methodology_id="evo2-enformer-borzoi-v3",
        seed_policy=(
            "paper generation seed not reported; BeamSearchOptimizer seed is fixed to 0, "
            "paired identically across full/fused arms, while Evo2Generator exposes no seed field"
        ),
        compile_device="modal",
    ),
}


def handoff_config_for(fixture_id: str) -> HandoffConfig:
    try:
        return HANDOFF_CONFIGS[fixture_id]
    except KeyError as exc:
        known = ", ".join(sorted(HANDOFF_CONFIGS))
        raise ValueError(f"no handoff config for {fixture_id!r}; known: {known}") from exc


def program_run_device(fixture_id: str) -> ProgramRunDevice:
    """Return the ``device`` argument for ``Program.run`` from handoff metadata."""

    return "modal" if handoff_config_for(fixture_id).compile_device == "modal" else None


def run_compiled_program(program: Program, *, fixture_id: str) -> None:
    """Execute a compiled program, routing GPU tools to Modal when configured."""

    device = program_run_device(fixture_id)
    run_program(program, device=device)
