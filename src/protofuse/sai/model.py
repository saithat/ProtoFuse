"""Safe JSON-backed vector-output linear ensembles for sequence-only fusion baselines."""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ModelArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SequenceFeatureSchema(ModelArtifact):
    sequence_type: str
    alphabet: str = Field(min_length=2)
    kmer_size: int = Field(default=1, ge=1, le=3)
    stride: int = Field(default=1, ge=1)
    include_composition: bool = True
    expected_length: int | None = Field(default=None, ge=1)
    position_encoding: Literal["none", "one_hot"] = "none"

    @model_validator(mode="after")
    def position_encoding_has_fixed_length(self) -> SequenceFeatureSchema:
        if self.position_encoding == "one_hot" and self.expected_length is None:
            raise ValueError("one-hot position encoding requires expected_length")
        return self

    @property
    def kmers(self) -> tuple[str, ...]:
        return tuple(
            "".join(parts) for parts in itertools.product(self.alphabet, repeat=self.kmer_size)
        )

    @property
    def feature_count(self) -> int:
        aggregate_count = len(self.kmers) + (
            len(self.alphabet) if self.include_composition else 0
        )
        positional_count = (
            self.expected_length * len(self.alphabet)
            if self.position_encoding == "one_hot" and self.expected_length is not None
            else 0
        )
        return aggregate_count + positional_count


class OutputNormalization(ModelArtifact):
    """Frozen conversion between a model's unit interval and a raw Proto score."""

    kind: Literal["identity", "sequence_bins"] = "identity"
    input_index: int | None = Field(default=None, ge=0)
    resolution_bp: int | None = Field(default=None, ge=1)
    trim_prefix_bp: int = Field(default=0, ge=0)
    maximum_bins: int | None = Field(default=None, ge=1)
    maximum_loss_per_bin: float = Field(default=1.0, gt=0.0)

    @model_validator(mode="after")
    def fields_match_kind(self) -> OutputNormalization:
        if not math.isfinite(self.maximum_loss_per_bin):
            raise ValueError("maximum_loss_per_bin must be finite")
        if self.kind == "identity":
            if (
                self.input_index is not None
                or self.resolution_bp is not None
                or self.maximum_bins is not None
            ):
                raise ValueError("identity normalization cannot select a sequence or resolution")
            if self.trim_prefix_bp != 0 or self.maximum_loss_per_bin != 1.0:
                raise ValueError("identity normalization cannot alter the raw score")
        elif self.input_index is None or self.resolution_bp is None:
            raise ValueError("sequence_bins normalization requires input_index and resolution_bp")
        return self

    def sequence_bin_count(self, sequences: tuple[str, ...]) -> int | None:
        if self.kind == "identity":
            return None
        if self.input_index is None or self.resolution_bp is None:  # validated above
            raise ValueError("invalid sequence_bins normalization")
        try:
            sequence = sequences[self.input_index]
        except IndexError as exc:
            raise ValueError(
                f"normalization input index {self.input_index} is out of range"
            ) from exc
        target_bp = len(sequence) - self.trim_prefix_bp
        if target_bp <= 0:
            raise ValueError("normalization target is empty after prefix trimming")
        target_bins = math.ceil(target_bp / self.resolution_bp)
        if self.maximum_bins is not None and target_bins > self.maximum_bins:
            raise ValueError(
                f"normalization target has {target_bins} bins; maximum is {self.maximum_bins}"
            )
        return target_bins

    def scale(self, sequences: tuple[str, ...]) -> float:
        target_bins = self.sequence_bin_count(sequences)
        if target_bins is None:
            return 1.0
        return float(target_bins) * self.maximum_loss_per_bin


# The analytic bound is (3 + sqrt(3)) / 4. Round upward enough to cover
# float32 LCB arithmetic and reduction over the paper's maximum 624 bins.
BORZOI_LCB_MAXIMUM_L1_PER_BIN = 1.1830132

_EVO2_OUTPUT_NORMALIZATIONS = {
    "enformer_pattern_l1_sum": OutputNormalization(
        kind="sequence_bins",
        input_index=1,
        resolution_bp=128,
        maximum_bins=156,
        maximum_loss_per_bin=1.0,
    ),
    "borzoi_pattern_l1_sum": OutputNormalization(
        kind="sequence_bins",
        input_index=1,
        resolution_bp=32,
        maximum_bins=624,
        maximum_loss_per_bin=BORZOI_LCB_MAXIMUM_L1_PER_BIN,
    ),
}


def evo2_output_normalizations(
    output_labels: tuple[str, ...],
) -> tuple[OutputNormalization, ...]:
    """Return the reviewed score transforms for Evo2's two raw L1 objectives."""

    try:
        return tuple(_EVO2_OUTPUT_NORMALIZATIONS[label] for label in output_labels)
    except KeyError as exc:
        raise ValueError(f"no Evo2 output normalization is registered for {exc.args[0]!r}") from exc


class LinearEnsembleModel(ModelArtifact):
    """Portable multi-output baseline with per-objective linear coefficient columns.

    The artifact shares features, bootstrap members, and routing across outputs. It neither
    scalarizes the objectives nor explicitly models covariance between them.
    """

    schema_version: str = "1.2"
    input_schemas: tuple[SequenceFeatureSchema, ...]
    output_labels: tuple[str, ...]
    output_normalizations: tuple[OutputNormalization, ...] = ()
    coefficients: tuple[tuple[tuple[float, ...], ...], ...]
    feature_center: tuple[float, ...]
    feature_scale: tuple[float, ...]
    support_threshold: float = Field(ge=0)
    uncertainty_threshold: float = Field(ge=0)
    calibration_absolute_error: tuple[float, ...]

    @model_validator(mode="after")
    def shapes_are_consistent(self) -> LinearEnsembleModel:
        feature_count = sum(schema.feature_count for schema in self.input_schemas)
        coefficient_rows = feature_count + 1
        output_count = len(self.output_labels)
        if not self.input_schemas or not self.output_labels or not self.coefficients:
            raise ValueError("model requires input schemas, output labels, and coefficients")
        if len(self.feature_center) != feature_count or len(self.feature_scale) != feature_count:
            raise ValueError("feature center/scale dimensions do not match feature schema")
        if len(self.calibration_absolute_error) != output_count:
            raise ValueError("calibration error dimension does not match outputs")
        if self.output_normalizations and len(self.output_normalizations) != output_count:
            raise ValueError("output normalization dimension does not match outputs")
        for normalization in self.output_normalizations:
            if (
                normalization.kind == "sequence_bins"
                and normalization.input_index is not None
                and normalization.input_index >= len(self.input_schemas)
            ):
                raise ValueError("output normalization input index does not match input schemas")
        for ensemble_index, matrix in enumerate(self.coefficients):
            if len(matrix) != coefficient_rows:
                raise ValueError(
                    f"ensemble {ensemble_index} has {len(matrix)} rows; expected {coefficient_rows}"
                )
            if any(len(row) != output_count for row in matrix):
                raise ValueError(f"ensemble {ensemble_index} output dimension mismatch")
        if any(scale <= 0 or not math.isfinite(scale) for scale in self.feature_scale):
            raise ValueError("feature scales must be positive finite values")
        return self

    @property
    def resolved_output_normalizations(self) -> tuple[OutputNormalization, ...]:
        if self.output_normalizations:
            return self.output_normalizations
        return tuple(OutputNormalization() for _ in self.output_labels)

    def output_scales(self, sequences: tuple[str, ...]) -> tuple[float, ...]:
        return tuple(
            normalization.scale(sequences)
            for normalization in self.resolved_output_normalizations
        )

    def normalize_outputs(
        self,
        values: tuple[float, ...],
        sequences: tuple[str, ...],
    ) -> tuple[float, ...]:
        if len(values) != len(self.output_labels):
            raise ValueError("output dimension does not match model labels")
        return tuple(
            value / scale
            for value, scale in zip(values, self.output_scales(sequences), strict=True)
        )


@dataclass(frozen=True)
class LinearPrediction:
    values: tuple[float, ...]
    uncertainties: tuple[float, ...]
    normalized_values: tuple[float, ...]
    normalized_uncertainties: tuple[float, ...]
    support_score: float


def _features(sequence: str, schema: SequenceFeatureSchema) -> list[float]:
    if schema.expected_length is not None and len(sequence) != schema.expected_length:
        raise ValueError(
            f"sequence length {len(sequence)} does not match expected {schema.expected_length}"
        )
    unexpected = sorted(set(sequence) - set(schema.alphabet))
    if unexpected:
        raise ValueError(f"sequence contains unsupported symbols: {unexpected}")
    kmers = schema.kmers
    kmer_index = {kmer: index for index, kmer in enumerate(kmers)}
    values = [0.0] * schema.feature_count
    positions = list(range(0, max(0, len(sequence) - schema.kmer_size + 1), schema.stride))
    valid_positions = [
        position
        for position in positions
        if len(sequence[position : position + schema.kmer_size]) == schema.kmer_size
    ]
    denominator = max(1, len(valid_positions))
    for position in valid_positions:
        kmer = sequence[position : position + schema.kmer_size]
        values[kmer_index[kmer]] += 1.0 / denominator
    if schema.include_composition:
        composition_offset = len(kmers)
        length = max(1, len(sequence))
        for offset, symbol in enumerate(schema.alphabet):
            values[composition_offset + offset] = sequence.count(symbol) / length
    if schema.position_encoding == "one_hot":
        aggregate_count = len(kmers) + (
            len(schema.alphabet) if schema.include_composition else 0
        )
        symbol_index = {symbol: index for index, symbol in enumerate(schema.alphabet)}
        alphabet_size = len(schema.alphabet)
        for position, symbol in enumerate(sequence):
            values[aggregate_count + position * alphabet_size + symbol_index[symbol]] = 1.0
    return values


def featurize_inputs(
    sequences: tuple[str, ...],
    schemas: tuple[SequenceFeatureSchema, ...],
) -> tuple[float, ...]:
    if len(sequences) != len(schemas):
        raise ValueError(f"received {len(sequences)} inputs; expected {len(schemas)}")
    features: list[float] = []
    for sequence, schema in zip(sequences, schemas, strict=True):
        features.extend(_features(sequence, schema))
    return tuple(features)


class LinearEnsemblePredictor:
    def __init__(self, artifact: LinearEnsembleModel) -> None:
        self.artifact = artifact

    def featurize(self, sequences: tuple[str, ...]) -> tuple[float, ...]:
        return featurize_inputs(sequences, self.artifact.input_schemas)

    def predict(self, sequences: tuple[str, ...]) -> LinearPrediction:
        features = self.featurize(sequences)
        design = (1.0, *features)
        ensemble_outputs: list[tuple[float, ...]] = []
        for matrix in self.artifact.coefficients:
            outputs = tuple(
                sum(design[row] * matrix[row][column] for row in range(len(design)))
                for column in range(len(self.artifact.output_labels))
            )
            ensemble_outputs.append(outputs)
        normalized_values = tuple(
            sum(output[column] for output in ensemble_outputs) / len(ensemble_outputs)
            for column in range(len(self.artifact.output_labels))
        )
        normalized_uncertainties = tuple(
            math.sqrt(
                sum(
                    (output[column] - normalized_values[column]) ** 2
                    for output in ensemble_outputs
                )
                / len(ensemble_outputs)
            )
            for column in range(len(normalized_values))
        )
        output_scales = self.artifact.output_scales(sequences)
        values = tuple(
            value * scale
            for value, scale in zip(normalized_values, output_scales, strict=True)
        )
        uncertainties = tuple(
            uncertainty * scale
            for uncertainty, scale in zip(
                normalized_uncertainties,
                output_scales,
                strict=True,
            )
        )
        support_score = math.sqrt(
            sum(
                ((value - center) / scale) ** 2
                for value, center, scale in zip(
                    features,
                    self.artifact.feature_center,
                    self.artifact.feature_scale,
                    strict=True,
                )
            )
            / len(features)
        )
        return LinearPrediction(
            values,
            uncertainties,
            normalized_values,
            normalized_uncertainties,
            support_score,
        )
