"""Runnable Proto program for CUSTOM eGFP lung tissue codon pool optimization."""

from protofuse.phillip.program_builders import run_custom_egfp_lung_report


def main() -> None:
    import sys

    tier = "smoke" if "--smoke" in sys.argv else "full"
    result = run_custom_egfp_lung_report(tier=tier)
    sequence = result.program.constructs[0].joined_sequences[0].sequence
    print(
        f"tier={tier} pool={result.n_pool} passed={result.candidates_passed_filter} "
        f"time={result.wall_time_ms / 1000:.1f}s tissue_score={result.best.tissue_score:.3f}"
    )
    print(sequence[:120] + ("..." if len(sequence) > 120 else ""))


if __name__ == "__main__":
    main()
