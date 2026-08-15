"""Small local CLI for contract validation and topology recommendation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from protofuse.contracts import MethodologySpec
from protofuse.integration import compile_proto_plan, validate_integrations
from protofuse.sai import recommend_topologies


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
    integrations_parser = subparsers.add_parser(
        "integrations",
        help="validate versioned integration scenarios under philip-sai-integrations/",
    )
    integrations_sub = integrations_parser.add_subparsers(
        dest="integrations_command",
        required=True,
    )
    integrations_validate = integrations_sub.add_parser("validate")
    integrations_validate.add_argument("--version", default="1")
    extract_parser = subparsers.add_parser("extract")
    extract_parser.add_argument("paper", type=Path)
    extract_parser.add_argument("--out", type=Path, required=True)

    benchmark_parser = subparsers.add_parser(
        "benchmark",
        help="run baseline/candidate benchmarks for a handoff decision",
    )
    benchmark_sub = benchmark_parser.add_subparsers(dest="benchmark_command", required=True)
    for name in ("baseline", "candidate", "compare"):
        child = benchmark_sub.add_parser(name)
        child.add_argument("--decision-id", required=True)
        child.add_argument("--scenario", default=None)
        child.add_argument("--seed", type=int, default=0)
        child.add_argument("--repetitions", type=int, default=None)
        child.add_argument("--device", default="local")
        if name == "compare":
            child.add_argument("--skip-candidate", action="store_true")

    args = parser.parse_args()
    if args.command == "integrations":
        for message in validate_integrations(version=args.version):
            print(message)
        return

    if args.command == "extract":
        from protofuse.scientific_agent import ScientificAgent
        from protofuse.scientific_agent.anthropic_backend import AnthropicBackend

        methodology = ScientificAgent(AnthropicBackend()).extract(args.paper.read_text())
        args.out.write_text(methodology.model_dump_json(indent=2) + "\n")
        print(f"wrote {args.out}")
        return

    if args.command == "benchmark":
        from protofuse.phillip.benchmark import (
            compare_benchmark,
            run_baseline_benchmark,
            run_candidate_benchmark,
        )

        if args.benchmark_command == "baseline":
            result = run_baseline_benchmark(
                decision_id=args.decision_id,
                scenario_id=args.scenario or "dnachisel-gc-optimization",
                seed=args.seed,
                repetitions=args.repetitions or 1,
                device=args.device,
            )
        elif args.benchmark_command == "candidate":
            result = run_candidate_benchmark(
                decision_id=args.decision_id,
                scenario_id=args.scenario or "dnachisel-gc-optimization",
                seed=args.seed,
                repetitions=args.repetitions or 1,
                device=args.device,
            )
        else:
            result = compare_benchmark(
                decision_id=args.decision_id,
                scenario_id=args.scenario,
                seed=args.seed,
                repetitions=args.repetitions,
                device=args.device,
                skip_candidate=args.skip_candidate,
            )
        print(json.dumps(result if isinstance(result, dict) else result.report, indent=2))
        return

    spec = _load(args.spec)
    if args.command == "validate":
        print(f"valid MethodologySpec v{spec.schema_version}: {spec.paper.title}")
        return

    recommendations = recommend_topologies(spec)
    if args.command == "recommend":
        print(json.dumps([item.model_dump(mode="json") for item in recommendations], indent=2))
        return

    plan = compile_proto_plan(spec, recommendations[0], device=args.device)
    print(plan.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
