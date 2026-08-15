"""Small, local executable proving the pinned Proto installation works."""

from proto_language.constraint import gc_content_constraint, max_homopolymer_constraint
from proto_language.core import Constraint, Construct, Program, Segment
from proto_language.generator import (
    RandomNucleotideGenerator,
    RandomNucleotideGeneratorConfig,
)
from proto_language.optimizer import MCMCOptimizer, MCMCOptimizerConfig


def build_program() -> Program:
    segment = Segment(length=24, sequence_type="dna")
    construct = Construct([segment])

    generator = RandomNucleotideGenerator(RandomNucleotideGeneratorConfig())
    generator.assign(segment)

    constraints = [
        Constraint(
            inputs=[segment],
            function=gc_content_constraint,
            function_config={"min_gc": 40, "max_gc": 60},
        ),
        Constraint(
            inputs=[segment],
            function=max_homopolymer_constraint,
            function_config={"max_length": 5},
        ),
    ]
    optimizer = MCMCOptimizer(
        constructs=[construct],
        generators=[generator],
        constraints=constraints,
        config=MCMCOptimizerConfig(
            num_results=1,
            proposals_per_result=1,
            num_steps=5,
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
