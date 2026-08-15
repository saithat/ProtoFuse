"""Reviewed finalize metadata for Phillip → Sai program collection handoffs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CompileDevice = Literal["local", "modal"]


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
        methodology_id="custom-egfp-v1",
        seed_policy="caller supplied; pool uses stochastic MCMC init per member",
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
    "gpcr-cxcr4-miniprotein": HandoffConfig(
        fixture_id="gpcr-cxcr4-miniprotein",
        methodology_id="gpcr-cxcr4-v1",
        seed_policy=(
            "RFdiffusion3/ProteinMPNN seeds from generator; rejection sampling is stateless"
        ),
        compile_device="modal",
        requires_paper_source=True,
    ),
}


def handoff_config_for(fixture_id: str) -> HandoffConfig:
    try:
        return HANDOFF_CONFIGS[fixture_id]
    except KeyError as exc:
        known = ", ".join(sorted(HANDOFF_CONFIGS))
        raise ValueError(f"no handoff config for {fixture_id!r}; known: {known}") from exc
