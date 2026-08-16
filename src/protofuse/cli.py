"""Small CLI for methodology extraction, validation, and Proto planning."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from protofuse.phillip import compile_proto_plan, recommend_topologies
from protofuse.phillip.contracts import MethodologySpec
from protofuse.phillip.handoff_config import HANDOFF_CONFIGS

FIXTURE_CHOICES = tuple(sorted(HANDOFF_CONFIGS))


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
    preflight_parser = subparsers.add_parser(
        "preflight",
        help="validate workload binding feasibility before scaling compute",
    )
    preflight_parser.add_argument(
        "fixture",
        choices=FIXTURE_CHOICES,
    )
    preflight_parser.add_argument(
        "--length",
        type=int,
        default=None,
        help="target construct length in bp (defaults to fixture global_parameters)",
    )
    preflight_parser.add_argument(
        "--samples",
        type=int,
        default=500,
        help="Monte Carlo samples for filter pass-rate estimate",
    )
    preflight_parser.add_argument(
        "--steps",
        type=int,
        default=50,
        help="MCMC steps per isolation ladder level",
    )
    preflight_parser.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero when classification is not ok",
    )
    run_parser = subparsers.add_parser("run", help="run a reviewed fixture workload")
    run_parser.add_argument(
        "fixture",
        choices=FIXTURE_CHOICES,
    )
    run_parser.add_argument("--tier", choices=("smoke", "full"), default="smoke")
    collection_parser = subparsers.add_parser(
        "collection",
        help="validate a frozen program collection under proto_programs/generated/",
    )
    collection_sub = collection_parser.add_subparsers(dest="collection_command", required=True)
    collection_validate = collection_sub.add_parser("validate")
    collection_validate.add_argument("collection_id")
    generate_parser = subparsers.add_parser(
        "generate",
        help="generate design_*.py programs from a reviewed fixture methodology",
    )
    generate_parser.add_argument("fixture", choices=FIXTURE_CHOICES)
    generate_parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output directory (defaults to proto_programs/generated/<fixture>)",
    )
    review_parser = subparsers.add_parser(
        "review",
        help="run every machine-checkable handoff gate for a fixture and its collection",
    )
    review_parser.add_argument("fixture", nargs="?", choices=FIXTURE_CHOICES, default=None)
    review_parser.add_argument(
        "--all",
        action="store_true",
        help="review every fixture that has a frozen collection",
    )
    review_parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="skip workload feasibility preflight (faster on DNA workloads)",
    )
    review_parser.add_argument(
        "--length",
        type=int,
        default=None,
        help="preflight target length (defaults to fixture global_parameters)",
    )
    review_parser.add_argument("--json", action="store_true", help="emit machine-readable report")
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

    if args.command == "preflight":
        import logging
        import sys

        from protofuse.phillip.workload_preflight import assert_workload_feasible, run_preflight

        logging.disable(logging.CRITICAL)
        report = run_preflight(
            args.fixture,
            target_length=args.length,
            filter_samples=args.samples,
            num_steps=args.steps,
        )
        print(report.summary())
        if args.strict:
            try:
                assert_workload_feasible(report)
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
                raise SystemExit(1) from exc
        elif report.classification != "ok":
            raise SystemExit(1)
        return

    if args.command == "run":
        import logging

        logging.disable(logging.CRITICAL)
        if args.fixture == "dnachisel-num1":
            from protofuse.phillip.program_builders import run_dnachisel_num1

            program, wall_ms = run_dnachisel_num1(tier=args.tier)
        elif args.fixture == "custom-egfp-lung":
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
        elif args.fixture == "esm2-protein-maturation":
            from protofuse.phillip.program_builders import run_esm2_protein_maturation

            program, wall_ms = run_esm2_protein_maturation(tier=args.tier)
        elif args.fixture == "antibody-cdr-maturation":
            from protofuse.phillip.program_builders import run_antibody_cdr_maturation

            program, wall_ms = run_antibody_cdr_maturation(tier=args.tier)
        elif args.fixture == "gpcr-cxcr4-miniprotein":
            from time import perf_counter

            from protofuse.phillip.program_builders import (
                build_gpcr_cxcr4_miniprotein_program,
                load_fixture_spec,
                resolve_workload_params,
            )

            spec = load_fixture_spec("gpcr-cxcr4-miniprotein")
            params = resolve_workload_params(spec, tier=args.tier)
            program = build_gpcr_cxcr4_miniprotein_program(params)
            start = perf_counter()
            program.run()
            wall_ms = (perf_counter() - start) * 1000
        elif args.fixture == "freebindcraft-binder":
            from protofuse.phillip.program_builders import run_freebindcraft_binder

            program, wall_ms = run_freebindcraft_binder(tier=args.tier)
        elif args.fixture == "symmetric-oligomer-ring":
            from protofuse.phillip.program_builders import run_symmetric_oligomer_ring

            program, wall_ms = run_symmetric_oligomer_ring(tier=args.tier)
        elif args.fixture == "ppi-interface-specificity":
            from protofuse.phillip.program_builders import run_ppi_interface_specificity

            program, wall_ms = run_ppi_interface_specificity(tier=args.tier)
        else:
            raise SystemExit(f"run not implemented for fixture={args.fixture}")
        sequence = program.constructs[0].joined_sequences[0].sequence
        print(f"fixture={args.fixture} tier={args.tier} wall_ms={wall_ms:.0f}")
        print(sequence[:120] + ("..." if len(sequence) > 120 else ""))
        return

    if args.command == "collection":
        from protofuse.program_collection import load_collection

        root = Path("proto_programs/generated") / args.collection_id
        loaded = load_collection(root, require_reviewed=True)
        print(
            f"ok: {loaded.manifest.collection_id} "
            f"({len(loaded.manifest.programs)} programs, "
            f"methodology={loaded.manifest.methodology_id})"
        )
        return

    if args.command == "review":
        from protofuse.phillip.review import COLLECTIONS_DIR, review_fixture

        if args.all:
            targets = [name for name in FIXTURE_CHOICES if (COLLECTIONS_DIR / name).is_dir()]
        elif args.fixture:
            targets = [args.fixture]
        else:
            raise SystemExit("review requires a fixture ID or --all")

        reports = [
            review_fixture(
                fixture,
                run_preflight_check=not args.skip_preflight,
                preflight_length=args.length,
            )
            for fixture in targets
        ]
        if args.json:
            print(json.dumps([report.as_dict() for report in reports], indent=2))
        else:
            for report in reports:
                print(report.summary())
        blocked = [report.fixture_id for report in reports if not report.ok]
        if blocked:
            raise SystemExit(f"blocked: {', '.join(blocked)}")
        return

    if args.command == "generate":
        from protofuse.phillip.generator import generate_program_sources, write_design_programs
        from protofuse.phillip.program_builders import load_fixture_spec
        from protofuse.phillip.registries import lookup_registry, profile_for_fixture

        spec = load_fixture_spec(args.fixture)
        profile = profile_for_fixture(args.fixture)
        recommendations = recommend_topologies(spec)
        plan = compile_proto_plan(
            spec,
            recommendations[0],
            registry=lookup_registry(profile.registry_name),
        )
        sources = generate_program_sources(spec, plan, profile=profile)
        output_dir = args.out or Path("proto_programs/generated") / args.fixture
        paths = write_design_programs(output_dir, sources)
        print(f"wrote {len(paths)} programs to {output_dir}")
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
        from protofuse.phillip.registries import lookup_registry

        registry = lookup_registry(args.registry)

    plan = compile_proto_plan(spec, recommendations[0], registry=registry, device=args.device)
    print(plan.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
