"""Small CLI for methodology extraction, validation, and Proto planning."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from protofuse.phillip import compile_proto_plan, recommend_topologies
from protofuse.phillip.contracts import MethodologySpec


def _load(path: Path) -> MethodologySpec:
    return MethodologySpec.model_validate_json(path.read_text())


def main() -> None:
    parser = argparse.ArgumentParser(prog="protofuse")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "recommend", "compile"):
        child = subparsers.add_parser(command)
        child.add_argument("spec", type=Path)
    compile_parser = subparsers.choices["compile"]
    compile_parser.add_argument("--device", choices=("local", "modal"), default="local")
    compile_parser.add_argument(
        "--registry",
        choices=("baseline", "dnachisel", "dnachisel-num1", "custom-egfp"),
        default=None,
        help="reviewed symbol registry for compile binding",
    )
    run_parser = subparsers.add_parser("run", help="run a reviewed fixture workload")
    run_parser.add_argument(
        "fixture",
        choices=("dnachisel-num1", "custom-egfp-lung"),
    )
    run_parser.add_argument("--tier", choices=("smoke", "full"), default="smoke")
    extract_parser = subparsers.add_parser("extract")
    extract_parser.add_argument("paper", type=Path)
    extract_parser.add_argument("--out", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "extract":
        from protofuse.phillip import ScientificAgent
        from protofuse.phillip.anthropic_backend import AnthropicBackend

        methodology = ScientificAgent(AnthropicBackend()).extract(args.paper.read_text())
        args.out.write_text(methodology.model_dump_json(indent=2) + "\n")
        print(f"wrote {args.out}")
        return

    if args.command == "run":
        import logging

        logging.disable(logging.CRITICAL)
        if args.fixture == "dnachisel-num1":
            from protofuse.phillip.program_builders import run_dnachisel_num1

            program, wall_ms = run_dnachisel_num1(tier=args.tier)
        else:
            from protofuse.phillip.program_builders import run_custom_egfp_lung_report

            result = run_custom_egfp_lung_report(tier=args.tier)
            program = result.program
            wall_ms = result.wall_time_ms
            print(
                json.dumps(
                    {
                        "pool": result.n_pool,
                        "passed_filter": result.candidates_passed_filter,
                        "best_tissue_score": result.best.tissue_score,
                    },
                    indent=2,
                )
            )
        sequence = program.constructs[0].joined_sequences[0].sequence
        print(f"fixture={args.fixture} tier={args.tier} wall_ms={wall_ms:.0f}")
        print(sequence[:120] + ("..." if len(sequence) > 120 else ""))
        return

    spec = _load(args.spec)
    if args.command == "validate":
        print(f"valid MethodologySpec v{spec.schema_version}: {spec.paper.title}")
        return

    recommendations = recommend_topologies(spec)
    if args.command == "recommend":
        print(json.dumps([item.model_dump(mode="json") for item in recommendations], indent=2))
        return

    registry = None
    if args.registry:
        from protofuse.phillip import registries

        registry = {
            "baseline": registries.DNA_BASELINE_REGISTRY,
            "dnachisel": registries.DNA_CHISEL_REGISTRY,
            "dnachisel-num1": registries.DNA_CHISEL_NUM1_REGISTRY,
            "custom-egfp": registries.CUSTOM_EGFP_REGISTRY,
        }[args.registry]

    plan = compile_proto_plan(spec, recommendations[0], registry=registry, device=args.device)
    print(plan.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
