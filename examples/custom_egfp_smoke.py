"""Runnable Proto program for CUSTOM eGFP lung tissue codon pool optimization."""

from protofuse.phillip.program_builders import run_custom_egfp_lung


def main() -> None:
    import sys

    tier = "smoke" if "--smoke" in sys.argv else "full"
    program, wall_time_ms = run_custom_egfp_lung(tier=tier)
    sequence = program.constructs[0].joined_sequences[0].sequence
    print(f"tier={tier} results={len(program.constructs)} time={wall_time_ms / 1000:.1f}s")
    print(sequence[:120] + ("..." if len(sequence) > 120 else ""))


if __name__ == "__main__":
    main()
