"""Exact wrappers for the released CUSTOM eGFP-to-lung optimization."""

from __future__ import annotations

import importlib
import json
import math
from collections.abc import Callable
from hashlib import sha256
from threading import Lock
from typing import Any, Literal, cast

import numpy as np
from proto_language.constraint.constraint_registry import constraint
from proto_language.core import ConstraintOutput, Generator, Sequence
from proto_language.core.generator import GeneratorInputType
from proto_language.generator.generator_registry import generator
from proto_language.optimizer import RejectionSamplingOptimizer, RejectionSamplingOptimizerConfig
from proto_language.optimizer.optimizer_registry import optimizer
from proto_language.utils.base import BaseConfig, ConfigField

# Protein input used by the authors' released 12-1_set_up_experiment.py script.
EGFP_PROTEIN_SEQUENCE = (
    "MVSKGEELFTGVVPILVELDGDVNGHKFSVSGEGEGDATYGKLTLKFICTTGKLPVPWPTLVTTLTYGVQCFSRYPDHM"
    "KQHDFFKSAMPEGYVQERTIFFKDDGNYKTRAEVKFEGDTLVNRIELKGIDFKEDGNILGHKLEYNYNSHNVYIMADKQK"
    "NGIKVNFKIRHNIEDGSVQLADHYQQNTPIGDGPVLLPDNHYLSTQSALSKDPNEKRDHMVLLEFVTAAGITLGMDELYK"
)

CUSTOM_METRIC_FIELDS = {
    "custom_mfe": "mfe_kcal_mol",
    "custom_mfe_init": "mfe_initial_kcal_mol",
    "custom_cai": "cai",
    "custom_cpb": "cpb",
    "custom_enc": "enc",
}
CUSTOM_METRIC_LABELS = tuple(CUSTOM_METRIC_FIELDS)
_MFE_MIN_KCAL_MOL = -200.0
_MFE_MAX_KCAL_MOL = 0.0
_ENC_MIN = 0.0
_ENC_MAX = 100.0
_NUMPY_RNG_LOCK = Lock()


def ordered_pool_sha256(sequences: list[str]) -> str:
    """Hash an ordered candidate pool without writing raw sequences to result metadata."""

    return sha256(json.dumps(sequences, separators=(",", ":")).encode("ascii")).hexdigest()


def _new_optimizer(
    tissue: Literal["Lung"],
    *,
    n_pool: int,
    degree: float = 0.5,
) -> Any:
    from custom import TissueOptimizer  # type: ignore[import-untyped]

    return TissueOptimizer(tissue, n_pool=n_pool, degree=degree, prob_original=0.0)


class CustomTissueCodonGeneratorConfig(BaseConfig):
    prompts: list[str] = ConfigField(
        title="Protein prompt",
        description="Exactly one protein sequence to synonymously encode.",
        min_length=1,
        max_length=1,
    )
    target_tissue: Literal["Lung"] = ConfigField(
        default="Lung",
        title="Target tissue",
        description="Tissue model used by the released CUSTOM optimizer.",
    )
    degree: float = ConfigField(
        default=0.5,
        ge=0.0,
        le=1.0,
        title="Optimization degree",
        description="Released CUSTOM interpolation degree; the paper workflow uses 0.5.",
    )
    batch_size: int = ConfigField(
        default=1000,
        ge=1,
        title="Paper pool size",
        description="Number of synonymous candidates generated in one complete pool.",
    )


@generator(
    key="custom-tissue-codon",
    label="CUSTOM Tissue Codon Generator",
    config=CustomTissueCodonGeneratorConfig,
    description="Sample synonymous coding sequences with the released CUSTOM tissue model",
    tools_called=["custom-optimizer"],
    supported_sequence_types=["dna"],
)
class CustomTissueCodonGenerator(Generator):
    """Generate the complete synonymous pool using CUSTOM's published implementation."""

    input_type = GeneratorInputType.PROMPT
    allows_empty_starting_sequence = True

    def __init__(self, config: CustomTissueCodonGeneratorConfig) -> None:
        super().__init__()
        self.config = config
        self.prompts = config.prompts
        self.batch_size = config.batch_size
        self.last_seed: int | None = None

    def _sample(self) -> None:
        self._validate_generator()
        optimizer_instance = _new_optimizer(
            self.config.target_tissue,
            n_pool=len(self.segment.proposal_sequences),
            degree=self.config.degree,
        )
        seed = self._next_seed()
        self.last_seed = seed
        # CUSTOM 0.0.1 uses NumPy's process-global RNG. Serialize this small section and
        # restore seeded runs so concurrent Proto programs cannot perturb one another.
        with _NUMPY_RNG_LOCK:
            previous_state = np.random.get_state() if seed is not None else None
            try:
                if seed is not None:
                    np.random.seed(seed)
                optimizer_instance.optimize(self.prompts[0])
            finally:
                if previous_state is not None:
                    np.random.set_state(previous_state)

        pool = [str(item) for item in optimizer_instance.pool]
        if len(pool) != len(self.segment.proposal_sequences):
            raise RuntimeError(
                f"CUSTOM returned {len(pool)} candidates for "
                f"{len(self.segment.proposal_sequences)} requested proposals"
            )
        expected_length = self.segment.sequence_length
        if any(len(item) != expected_length for item in pool):
            raise RuntimeError("CUSTOM returned a coding sequence with an unexpected length")
        genetic_code = cast(dict[str, str], importlib.import_module("custom.custom").GENETIC_CODE)
        translated = [
            "".join(
                genetic_code[candidate[index : index + 3]]
                for index in range(0, len(candidate), 3)
            )
            for candidate in pool
        ]
        if any(protein != self.prompts[0].upper() for protein in translated):
            raise RuntimeError("CUSTOM returned a non-synonymous coding sequence")
        for proposal, candidate in zip(self.segment.proposal_sequences, pool, strict=True):
            proposal.sequence = candidate


class CustomMetricConfig(BaseConfig):
    target_tissue: Literal["Lung"] = ConfigField(
        default="Lung",
        title="Target tissue",
        description="Tissue model associated with the candidate pool.",
    )


def _metric_values(
    input_sequences: list[tuple[Sequence, ...]],
    config: CustomMetricConfig,
    method_name: str,
) -> list[float]:
    instance = _new_optimizer(config.target_tissue, n_pool=len(input_sequences))
    instance.pool = [sequence.sequence for (sequence,) in input_sequences]
    method = cast(Callable[[], list[float]], getattr(instance, method_name))
    values = [float(value) for value in method()]
    if len(values) != len(input_sequences) or any(not math.isfinite(value) for value in values):
        raise ValueError(f"CUSTOM {method_name} returned invalid metric values")
    return values


def _affine_energy(value: float, *, lower: float, upper: float, maximize: bool) -> float:
    if not lower < upper or value < lower - 1e-9 or value > upper + 1e-9:
        raise ValueError(
            f"CUSTOM metric {value} is outside the registered [{lower}, {upper}] range"
        )
    scaled = (value - lower) / (upper - lower)
    energy = 1.0 - scaled if maximize else scaled
    return min(1.0, max(0.0, energy))


def _outputs(
    values: list[float],
    *,
    metric: str,
    lower: float,
    upper: float,
    maximize: bool,
) -> list[ConstraintOutput]:
    return [
        ConstraintOutput(
            score=_affine_energy(value, lower=lower, upper=upper, maximize=maximize),
            metadata={metric: value},
        )
        for value in values
    ]


@constraint(
    key="custom-mfe",
    label="CUSTOM MFE",
    config=CustomMetricConfig,
    description="Mean 40-nt body-window minimum free energy from released CUSTOM",
    tools_called=["viennarna"],
    category="sequence_composition",
    supported_sequence_types=["dna"],
)
def custom_mfe_constraint(
    input_sequences: list[tuple[Sequence, ...]], config: CustomMetricConfig
) -> list[ConstraintOutput]:
    values = _metric_values(input_sequences, config, "MFE")
    return _outputs(
        values,
        metric="mfe_kcal_mol",
        lower=_MFE_MIN_KCAL_MOL,
        upper=_MFE_MAX_KCAL_MOL,
        maximize=False,
    )


@constraint(
    key="custom-mfe-init",
    label="CUSTOM Initial MFE",
    config=CustomMetricConfig,
    description="First-40-nt minimum free energy from released CUSTOM",
    tools_called=["viennarna"],
    category="sequence_composition",
    supported_sequence_types=["dna"],
)
def custom_mfe_init_constraint(
    input_sequences: list[tuple[Sequence, ...]], config: CustomMetricConfig
) -> list[ConstraintOutput]:
    values = _metric_values(input_sequences, config, "MFEini")
    return _outputs(
        values,
        metric="mfe_initial_kcal_mol",
        lower=_MFE_MIN_KCAL_MOL,
        upper=_MFE_MAX_KCAL_MOL,
        maximize=True,
    )


@constraint(
    key="custom-cai",
    label="CUSTOM CAI",
    config=CustomMetricConfig,
    description="Human codon adaptation index from released CUSTOM",
    tools_called=["custom-optimizer"],
    category="sequence_composition",
    supported_sequence_types=["dna"],
)
def custom_cai_constraint(
    input_sequences: list[tuple[Sequence, ...]], config: CustomMetricConfig
) -> list[ConstraintOutput]:
    return _outputs(
        _metric_values(input_sequences, config, "CAI"),
        metric="cai",
        lower=0.0,
        upper=1.0,
        maximize=True,
    )


@constraint(
    key="custom-cpb",
    label="CUSTOM CPB",
    config=CustomMetricConfig,
    description="Human codon-pair bias from released CUSTOM",
    tools_called=["custom-optimizer"],
    category="sequence_composition",
    supported_sequence_types=["dna"],
)
def custom_cpb_constraint(
    input_sequences: list[tuple[Sequence, ...]], config: CustomMetricConfig
) -> list[ConstraintOutput]:
    values = _metric_values(input_sequences, config, "CPB")
    custom_module = importlib.import_module("custom.custom")
    human_scores = custom_module.CPSs["Homo_sapiens"]
    return _outputs(
        values,
        metric="cpb",
        lower=float(human_scores.min()),
        upper=float(human_scores.max()),
        maximize=True,
    )


@constraint(
    key="custom-enc",
    label="CUSTOM ENC",
    config=CustomMetricConfig,
    description="Effective number of codons from released CUSTOM",
    tools_called=["custom-optimizer"],
    category="sequence_composition",
    supported_sequence_types=["dna"],
)
def custom_enc_constraint(
    input_sequences: list[tuple[Sequence, ...]], config: CustomMetricConfig
) -> list[ConstraintOutput]:
    return _outputs(
        _metric_values(input_sequences, config, "ENC"),
        metric="enc",
        # CUSTOM's finite-sequence estimator can slightly exceed ENC's idealized
        # 20–61 interpretation. This broad affine envelope transports it into Proto's
        # [0, 1] contract without clipping or changing the paper's pool-relative rank.
        lower=_ENC_MIN,
        upper=_ENC_MAX,
        maximize=False,
    )


def paper_composite_energies(metric_scores: list[list[float]]) -> list[float]:
    """Match CUSTOM's equal-weight, per-pool min-max ranking with lower-is-better energy."""

    if not metric_scores or not metric_scores[0]:
        raise ValueError("CUSTOM ranking requires at least one metric and one candidate")
    candidate_count = len(metric_scores[0])
    if any(len(scores) != candidate_count for scores in metric_scores):
        raise ValueError("CUSTOM metric vectors have inconsistent lengths")

    normalized: list[list[float]] = []
    for scores in metric_scores:
        if any(not math.isfinite(score) for score in scores):
            raise ValueError("CUSTOM ranking requires finite metric values")
        lower = min(scores)
        span = max(scores) - lower
        if span <= 0.0:
            # pandas represents this column as NaN and mean(axis=1) skips it in the
            # released select_best implementation.
            continue
        normalized.append([(value - lower) / span for value in scores])
    if not normalized:
        raise ValueError("CUSTOM ranking requires at least one non-constant metric")
    return [
        sum(scores[index] for scores in normalized) / len(normalized)
        for index in range(candidate_count)
    ]


@optimizer(
    key="custom-paper-pool",
    label="CUSTOM Paper Pool",
    config=RejectionSamplingOptimizerConfig,
    description="Rank one complete CUSTOM pool with the paper's five equally weighted metrics",
    compatible_generators=["custom-tissue-codon"],
    required_constraint_mode="discrete",
)
class CustomPaperPoolOptimizer(RejectionSamplingOptimizer):  # type: ignore[misc]
    """Use paper ordering: score the whole pool, normalize, filter, then retain top ten."""

    pool_relative_objective = True
    paper_energy_by_sequence: dict[str, float]
    paper_score_by_sequence: dict[str, float]
    candidate_pool_sha256: str
    candidate_pool_size: int

    def score_energy(
        self,
        operation: Literal["add", "multiply"] = "add",
        filter_penalty: float = math.inf,
    ) -> None:
        if operation != "add":
            raise ValueError("CUSTOM paper ranking supports additive aggregation only")
        self._validate_optimizer()
        proposal_count = len(self.segments[0].proposal_sequences)
        evaluate_all = [True] * proposal_count
        by_label = {constraint.label: constraint for constraint in self.constraints}
        missing = [label for label in CUSTOM_METRIC_LABELS if label not in by_label]
        if missing:
            raise ValueError(f"CUSTOM paper ranking is missing metrics: {', '.join(missing)}")

        metric_scores: list[list[float]] = []
        self._last_constraint_scores = {}
        for label in CUSTOM_METRIC_LABELS:
            values = by_label[label].evaluate(mask=evaluate_all, verbose=self.verbose)
            scores = [float(value) for value in values]
            metric_scores.append(scores)
            self._last_constraint_scores[label] = scores

        self._proposal_outcomes = ["accepted"] * proposal_count
        self._last_filter_pass_counts = {}
        for filter_constraint in (
            item for item in self.constraints if item.threshold is not None
        ):
            passed = [
                bool(value)
                for value in filter_constraint.evaluate(
                    mask=evaluate_all,
                    verbose=self.verbose,
                )
            ]
            self._last_filter_pass_counts[filter_constraint.label] = (
                sum(passed),
                proposal_count,
            )
            for index, accepted in enumerate(passed):
                if not accepted and self._proposal_outcomes[index] == "accepted":
                    self._proposal_outcomes[index] = filter_constraint.label

        composite = paper_composite_energies(metric_scores)
        sequences = [proposal.sequence for proposal in self.segments[0].proposal_sequences]
        self.candidate_pool_sha256 = ordered_pool_sha256(sequences)
        self.candidate_pool_size = len(sequences)
        self.paper_energy_by_sequence = dict(zip(sequences, composite, strict=True))
        self.paper_score_by_sequence = {
            sequence: 1.0 - energy for sequence, energy in self.paper_energy_by_sequence.items()
        }
        self.energy_scores = [
            score if self._proposal_outcomes[index] == "accepted" else filter_penalty
            for index, score in enumerate(composite)
        ]
        self._proposal_energy_scores = list(self.energy_scores)
        self._clear_tool_cache()
