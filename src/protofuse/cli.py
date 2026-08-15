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
