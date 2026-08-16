"""ProtoFuse generators for fixed-sequence structure inference sweeps."""

from __future__ import annotations

from typing import final

from proto_language.core import Generator, GeneratorInputType
from proto_language.generator.generator_registry import generator
from proto_language.utils.base import BaseConfig


class FixedSequenceSweepGeneratorConfig(BaseConfig):
    """No-op configuration for fixed-sequence Boltz-2 inference sweeps."""


@generator(
    key="fixed-sequence-sweep",
    label="Fixed Sequence Sweep",
    config=FixedSequenceSweepGeneratorConfig,
    description="No-op mutation generator for repeated Boltz-2 inference on one sequence",
    uses_gpu=False,
    tools_called=[],
    supported_sequence_types=["protein"],
)
@final
class FixedSequenceSweepGenerator(Generator):
    """Keep proposal sequences unchanged; sweep diversity comes from Boltz-2 inference."""

    input_type = GeneratorInputType.STARTING_SEQUENCE
    allows_empty_starting_sequence = False

    def __init__(self, config: FixedSequenceSweepGeneratorConfig | None = None) -> None:
        super().__init__()
        self.config = config or FixedSequenceSweepGeneratorConfig()

    def _sample(self) -> None:
        return
