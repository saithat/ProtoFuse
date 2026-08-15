"""Runnable Proto program for Pipeline 2 (DNA Chisel windowed GC scenario)."""

from proto_language.constraint import gc_content_constraint, max_homopolymer_constraint
from proto_language.core import Constraint, Construct, Program, Segment
from proto_language.generator import (
    RandomNucleotideGenerator,
    RandomNucleotideGeneratorConfig,
)
from proto_language.optimizer import MCMCOptimizer, MCMCOptimizerConfig
from proto_tools.transforms.masking import MaskingStrategy


def build_program() -> Program:
    segment = Segment(length=100, sequence_type="dna")
    construct = Construct([segment])

    generator = RandomNucleotideGenerator(
        RandomNucleotideGeneratorConfig(
            masking_strategy=MaskingStrategy(num_mutations=3),
        )
    )
    generator.assign(segment)

    constraints = [
        Constraint(
            inputs=[segment],
            function=gc_content_constraint,
            function_config={"min_gc": 45, "max_gc": 65},
            weight=1.0,
            label="windowed_gc_content",
        ),
        Constraint(
            inputs=[segment],
            function=max_homopolymer_constraint,
            function_config={"max_length": 4},
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
            proposals_per_result=1,
            num_steps=50,
            max_temperature=1.0,
        ),
    )
    return Program(optimizers=[optimizer], num_results=1)


def main() -> None:
    program = build_program()
    program.run()
    print(program.constructs[0].joined_sequences[0])


if __name__ == "__main__":
    main()
