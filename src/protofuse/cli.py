"""CLI for reviewed workflow handoffs, execution, and learned-fusion development."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from protofuse.phillip import compile_proto_plan, recommend_topologies
from protofuse.phillip.contracts import MethodologySpec
from protofuse.phillip.handoff_config import HANDOFF_CONFIGS

if TYPE_CHECKING:
    from proto_language.core import Program

FIXTURE_CHOICES = tuple(sorted(HANDOFF_CONFIGS))
RunTier = Literal["smoke", "full"]


def _load(path: Path) -> MethodologySpec:
    return MethodologySpec.model_validate_json(path.read_text())


def _run_fixture(
    fixture_id: str,
    *,
    tier: RunTier,
) -> tuple[Program, float, dict[str, int | float] | None]:
    """Run one reviewed fixture through its standard workload entry point."""

    from protofuse.phillip.program_builders import (
        run_af3_boltz2_state_sweep,
        run_antibody_cdr_maturation,
        run_bioemu_ensemble_filter,
        run_boltz2_state_sweep,
        run_custom_egfp_lung_report,
        run_dnachisel_num1,
        run_esm2_protein_maturation,
        run_evo2_regulatory_design,
        run_freebindcraft_binder,
        run_gpcr_cxcr4_miniprotein,
        run_ligandmpnn_enzyme_redesign,
        run_ppi_interface_specificity,
        run_rfdiffusion3_af3_ppi,
        run_rfdiffusion3_boltz2_binder,
        run_symmetric_oligomer_ring,
    )

    if fixture_id == "custom-egfp-lung":
        result = run_custom_egfp_lung_report(tier=tier)
        summary = {
            "pool": result.n_pool,
            "passed_filter": result.candidates_passed_filter,
            "best_tissue_score": result.best.tissue_score,
        }
        return result.program, result.wall_time_ms, summary

    runners: dict[str, Callable[..., tuple[Program, float]]] = {
        "af3-boltz2-state-sweep": run_af3_boltz2_state_sweep,
        "antibody-cdr-maturation": run_antibody_cdr_maturation,
        "bioemu-ensemble-filter": run_bioemu_ensemble_filter,
        "boltz2-state-sweep": run_boltz2_state_sweep,
        "dnachisel-num1": run_dnachisel_num1,
        "esm2-protein-maturation": run_esm2_protein_maturation,
        "evo2-enformer-borzoi": run_evo2_regulatory_design,
        "freebindcraft-binder": run_freebindcraft_binder,
        "gpcr-cxcr4-miniprotein": run_gpcr_cxcr4_miniprotein,
        "ligandmpnn-enzyme-redesign": run_ligandmpnn_enzyme_redesign,
        "ppi-interface-specificity": run_ppi_interface_specificity,
        "rfdiffusion3-boltz2-binder": run_rfdiffusion3_boltz2_binder,
        "rfdiffusion3-af3-ppi": run_rfdiffusion3_af3_ppi,
        "symmetric-oligomer-ring": run_symmetric_oligomer_ring,
    }
    try:
        runner = runners[fixture_id]
    except KeyError as exc:
        raise ValueError(f"run not implemented for fixture={fixture_id}") from exc
    program, wall_ms = runner(tier=tier)
    return program, wall_ms, None


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
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
    run_parser.add_argument(
        "--checkpoint-dir",
        type=Path,
        default=Path("data/runs/checkpoints"),
        help="checkpoint root (default: data/runs/checkpoints)",
    )
    run_parser.add_argument(
        "--restart",
        action="store_true",
        help="archive any saved run for this fixture/tier and start over",
    )
    run_parser.add_argument(
        "--no-checkpoint",
        action="store_true",
        help="disable automatic save and resume for this run",
    )
    collection_parser = subparsers.add_parser(
        "collection",
        help="validate a frozen program collection under proto_programs/generated/",
    )
    collection_sub = collection_parser.add_subparsers(dest="collection_command", required=True)
    collection_validate = collection_sub.add_parser("validate")
    collection_validate.add_argument("collection_id")
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="load one reviewed generated program and print its exact signature",
    )
    analyze_parser.add_argument("collection", type=Path)
    analyze_parser.add_argument("program_id")
    trace_parser = subparsers.add_parser(
        "trace",
        help="run one reviewed program and append parent constraint outputs to JSONL",
    )
    trace_parser.add_argument("collection", type=Path)
    trace_parser.add_argument("program_id")
    trace_parser.add_argument("--out", type=Path, required=True)
    trace_parser.add_argument("--run-id", required=True)
    trace_parser.add_argument("--group-id", required=True)
    trace_parser.add_argument("--device", choices=("local", "modal"), default="local")
    trace_parser.add_argument("--tier", choices=("smoke", "full"), default=None)
    trace_parser.add_argument(
        "--hash-inputs-only",
        action="store_true",
        help="omit raw input sequences from trace rows",
    )
    fusion_parser = subparsers.add_parser(
        "fusion",
        help="validate, train, or evaluate learned-fusion artifacts",
    )
    fusion_sub = fusion_parser.add_subparsers(dest="fusion_command", required=True)
    fusion_validate = fusion_sub.add_parser("validate")
    fusion_validate.add_argument("artifact", type=Path)
    fusion_validate.add_argument("--allow-unreviewed", action="store_true")
    fusion_profile = fusion_sub.add_parser("profile")
    fusion_profile.add_argument("--trace", type=Path, action="append", required=True)
    fusion_profile.add_argument("--out", type=Path, default=None)
    fusion_train = fusion_sub.add_parser("train")
    fusion_train.add_argument("collection", type=Path)
    fusion_train.add_argument("program_id")
    fusion_train.add_argument("--trace", type=Path, action="append", required=True)
    fusion_train.add_argument("--optimizer-index", type=int, required=True)
    fusion_train.add_argument("--constraint", action="append", required=True)
    fusion_train.add_argument("--fusion-id", required=True)
    fusion_train.add_argument("--version", required=True)
    fusion_train.add_argument("--out", type=Path, required=True)
    fusion_train.add_argument("--seed", type=int, default=0)
    fusion_train.add_argument("--ensemble-size", type=int, default=8)
    fusion_evaluate = fusion_sub.add_parser("evaluate")
    fusion_evaluate.add_argument("artifact", type=Path)
    fusion_evaluate.add_argument("collection", type=Path)
    fusion_evaluate.add_argument("program_id")
    fusion_evaluate.add_argument("--seed", type=int, action="append", required=True)
    fusion_evaluate.add_argument("--device", choices=("local", "modal"), default="local")
    fusion_evaluate.add_argument("--allow-unreviewed", action="store_true")
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
    paper_parser = subparsers.add_parser(
        "paper",
        help="pull up a fixture's paper (metadata, abstract, quote checks) for human review",
    )
    paper_parser.add_argument("fixture", choices=FIXTURE_CHOICES)
    paper_parser.add_argument(
        "--abstract-only",
        action="store_true",
        help="print only paper identity and abstract",
    )
    paper_parser.add_argument(
        "--offline",
        action="store_true",
        help="skip the DOI registry lookup and use local files only",
    )
    paper_parser.add_argument(
        "--text",
        type=Path,
        default=None,
        help="verify quotes against this text instead of the fixture's paper.source_path",
    )
    paper_parser.add_argument("--json", action="store_true", help="emit machine-readable report")
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
        preflight_report = run_preflight(
            args.fixture,
            target_length=args.length,
            filter_samples=args.samples,
            num_steps=args.steps,
        )
        print(preflight_report.summary())
        if args.strict:
            try:
                assert_workload_feasible(preflight_report)
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
                raise SystemExit(1) from exc
        elif preflight_report.classification != "ok":
            raise SystemExit(1)
        return

    if args.command == "run":
        import logging

        from protofuse.checkpoints import checkpoint_session

        logging.disable(logging.CRITICAL)
        if args.no_checkpoint:
            program, wall_ms, summary = _run_fixture(args.fixture, tier=args.tier)
        else:
            with checkpoint_session(
                args.checkpoint_dir,
                run_id=args.fixture,
                tier=args.tier,
                restart=args.restart,
            ) as session:
                print(f"checkpoint={session.directory}")
                program, wall_ms, summary = _run_fixture(args.fixture, tier=args.tier)
        if summary is not None:
            print(json.dumps(summary, indent=2))
        sequence = program.constructs[0].joined_sequences[0].sequence
        print(f"fixture={args.fixture} tier={args.tier} wall_ms={wall_ms:.0f}")
        print(sequence[:120] + ("..." if len(sequence) > 120 else ""))
        return

    if args.command == "collection":
        from protofuse.program_collection import load_collection

        root = Path("proto_programs/generated") / args.collection_id
        loaded_collection = load_collection(root, require_reviewed=True)
        print(
            f"ok: {loaded_collection.manifest.collection_id} "
            f"({len(loaded_collection.manifest.programs)} programs, "
            f"methodology={loaded_collection.manifest.methodology_id})"
        )
        return

    if args.command == "analyze":
        from protofuse.sai.analyzer import load_reviewed_program

        analyzed = load_reviewed_program(args.collection, program_id=args.program_id)
        print(analyzed.signature.model_dump_json(indent=2))
        print(f"sha256={analyzed.signature.sha256}")
        return

    if args.command == "trace":
        from protofuse.sai.analyzer import load_reviewed_program
        from protofuse.sai.tracing import JsonlTraceWriter, trace_program_constraints

        traced_program = load_reviewed_program(args.collection, program_id=args.program_id)
        writer = JsonlTraceWriter(args.out)
        with trace_program_constraints(
            traced_program.program,
            writer,
            run_id=args.run_id,
            group_id=args.group_id,
            include_inputs=not args.hash_inputs_only,
            collection_id=traced_program.collection.manifest.collection_id,
            program_id=traced_program.entry.program_id,
            methodology_id=traced_program.collection.manifest.methodology_id,
            tier=args.tier,
        ):
            traced_program.program.run(device="modal" if args.device == "modal" else None)
        print(f"trace={args.out}")
        return

    if args.command == "fusion":
        from protofuse.sai.analyzer import load_reviewed_program
        from protofuse.sai.artifacts import load_fusion_artifact

        if args.fusion_command == "validate":
            artifact = load_fusion_artifact(
                args.artifact,
                require_reviewed=not args.allow_unreviewed,
            )
            print(
                f"ok: {artifact.manifest.fusion_id}@{artifact.manifest.version} "
                f"reviewed={artifact.manifest.reviewed}"
            )
            return

        if args.fusion_command == "profile":
            from protofuse.sai.profiling import profile_traces

            trace_profile = profile_traces(tuple(args.trace))
            payload = trace_profile.model_dump_json(indent=2) + "\n"
            if args.out is None:
                print(payload, end="")
            else:
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(payload)
                print(f"profile={args.out}")
            return

        if args.fusion_command == "train":
            from protofuse.sai.training import (
                load_teacher_samples,
                train_linear_ensemble,
                write_trained_fusion,
            )

            training_program = load_reviewed_program(
                args.collection,
                program_id=args.program_id,
            )
            traces = tuple(args.trace)
            labels = tuple(args.constraint)
            samples = load_teacher_samples(
                traces,
                optimizer_index=args.optimizer_index,
                constraint_labels=labels,
            )
            training = train_linear_ensemble(
                samples,
                output_labels=labels,
                trace_paths=traces,
                seed=args.seed,
                ensemble_size=args.ensemble_size,
            )
            artifact = write_trained_fusion(
                args.out,
                program=training_program.program,
                optimizer_index=args.optimizer_index,
                constraint_labels=labels,
                fusion_id=args.fusion_id,
                version=args.version,
                result=training,
            )
            print(
                json.dumps(
                    {
                        "artifact": str(artifact.root),
                        "reviewed": artifact.manifest.reviewed,
                        "metrics": training.metrics,
                    },
                    indent=2,
                )
            )
            return

        from protofuse.sai.evaluation import evaluate_paired

        artifact = load_fusion_artifact(
            args.artifact,
            require_reviewed=not args.allow_unreviewed,
        )

        def build_program() -> Program:
            return load_reviewed_program(
                args.collection,
                program_id=args.program_id,
            ).program

        evaluation = evaluate_paired(
            build_program,
            artifact,
            seeds=args.seed,
            device="modal" if args.device == "modal" else None,
        )
        print(json.dumps(evaluation.as_dict(), indent=2))
        return

    if args.command == "paper":
        from protofuse.phillip.paper_review import build_paper_review, format_review

        paper_review = build_paper_review(
            args.fixture,
            offline=args.offline,
            text_path=args.text,
        )
        if args.json:
            print(json.dumps(paper_review.as_dict(), indent=2))
        else:
            print(format_review(paper_review, abstract_only=args.abstract_only))
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
            for review_report in reports:
                print(review_report.summary())
        blocked = [review_report.fixture_id for review_report in reports if not review_report.ok]
        if blocked:
            raise SystemExit(f"blocked: {', '.join(blocked)}")
        return

    if args.command == "generate":
        from protofuse.phillip.generator import generate_program_sources, write_design_programs
        from protofuse.phillip.program_builders import load_fixture_spec
        from protofuse.phillip.registries import lookup_registry, profile_for_fixture

        spec = load_fixture_spec(args.fixture)
        workload_profile = profile_for_fixture(args.fixture)
        recommendations = recommend_topologies(spec)
        plan = compile_proto_plan(
            spec,
            recommendations[0],
            registry=lookup_registry(workload_profile.registry_name),
        )
        sources = generate_program_sources(spec, plan, profile=workload_profile)
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
