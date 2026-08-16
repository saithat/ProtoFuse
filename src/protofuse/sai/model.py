"""Safe JSON-backed vector-output linear ensembles for sequence-only fusion baselines."""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

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

    @property
    def kmers(self) -> tuple[str, ...]:
        return tuple(
            "".join(parts) for parts in itertools.product(self.alphabet, repeat=self.kmer_size)
        )

    @property
    def feature_count(self) -> int:
        return len(self.kmers) + (len(self.alphabet) if self.include_composition else 0)


class LinearEnsembleModel(ModelArtifact):
    """Portable multi-output baseline with per-objective linear coefficient columns.

    The artifact shares features, bootstrap members, and routing across outputs. It neither
    scalarizes the objectives nor explicitly models covariance between them.
    """

    schema_version: str = "1.0"
    input_schemas: tuple[SequenceFeatureSchema, ...]
    output_labels: tuple[str, ...]
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


@dataclass(frozen=True)
class LinearPrediction:
    values: tuple[float, ...]
    uncertainties: tuple[float, ...]
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
        values = tuple(
            sum(output[column] for output in ensemble_outputs) / len(ensemble_outputs)
            for column in range(len(self.artifact.output_labels))
        )
        uncertainties = tuple(
            math.sqrt(
                sum((output[column] - values[column]) ** 2 for output in ensemble_outputs)
                / len(ensemble_outputs)
            )
            for column in range(len(values))
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
        return LinearPrediction(values, uncertainties, support_score)
