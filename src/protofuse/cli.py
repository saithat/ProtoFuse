"""CLI for reviewed workflow handoffs, execution, and learned-fusion development."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from protofuse.phillip import compile_proto_plan, recommend_topologies
from protofuse.phillip.contracts import MethodologySpec
from protofuse.phillip.handoff_config import HANDOFF_CONFIGS
from protofuse.sai.hardware import MODAL_GPU_CHOICES

if TYPE_CHECKING:
    from proto_language.core import Program

FIXTURE_CHOICES = tuple(sorted(HANDOFF_CONFIGS))
RunTier = Literal["smoke", "full"]


def _load(path: Path) -> MethodologySpec:
    return MethodologySpec.model_validate_json(path.read_text())


def _write_text_atomic(path: Path, payload: str) -> None:
    """Replace a result file only after its complete contents reach disk."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _run_fixture(
    fixture_id: str,
    *,
    tier: RunTier,
) -> tuple[Program, float, dict[str, Any] | None]:
    """Run one reviewed fixture through its standard workload entry point."""

    from protofuse.phillip.program_builders import (
        run_af3_boltz2_state_sweep,
        run_antibody_cdr_maturation,
        run_bioemu_ensemble_filter,
        run_boltz2_state_sweep,
        run_custom_egfp_lung,
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
        summarize_custom_egfp_program,
    )

    runners: dict[str, Callable[..., tuple[Program, float]]] = {
        "af3-boltz2-state-sweep": run_af3_boltz2_state_sweep,
        "antibody-cdr-maturation": run_antibody_cdr_maturation,
        "bioemu-ensemble-filter": run_bioemu_ensemble_filter,
        "boltz2-state-sweep": run_boltz2_state_sweep,
        "custom-egfp-lung": run_custom_egfp_lung,
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
    summary = summarize_custom_egfp_program(program) if fixture_id == "custom-egfp-lung" else None
    return program, wall_ms, summary


def main() -> None:
    from protofuse.env import load_repo_env

    load_repo_env()
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
        help="disable automatic save, resume, and structured event logging for this run",
    )
    custom_parity_parser = subparsers.add_parser(
        "custom-reference-parity",
        help="compare one full CUSTOM pool with the pinned released implementation",
    )
    custom_parity_parser.add_argument("--seed", type=int, required=True)
    custom_parity_parser.add_argument("--tier", choices=("full",), default="full")
    custom_parity_parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="atomically write the parity JSON artifact instead of printing it",
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
    trace_parser.add_argument(
        "--group-by-input-batch",
        action="store_true",
        help=(
            "derive split groups from each proposal batch while keeping sibling proposals together"
        ),
    )
    trace_parser.add_argument("--seed", type=int, default=None)
    trace_parser.add_argument("--device", choices=("local", "modal"), default="local")
    trace_parser.add_argument(
        "--modal-gpu",
        choices=(*MODAL_GPU_CHOICES, "auto"),
        default=None,
        help=(
            "exact Modal accelerator, or 'auto' for score-collection-only deployment "
            "fallback; required when --device modal"
        ),
    )
    trace_parser.add_argument("--tier", choices=("smoke", "full"), default=None)
    trace_parser.add_argument(
        "--hash-inputs-only",
        action="store_true",
        help="omit raw input sequences from trace rows",
    )
    fusion_parser = subparsers.add_parser(
        "fusion",
        help="compare, validate, train, or evaluate learned-fusion artifacts",
    )
    fusion_sub = fusion_parser.add_subparsers(dest="fusion_command", required=True)
    fusion_validate = fusion_sub.add_parser("validate")
    fusion_validate.add_argument("artifact", type=Path)
    fusion_validate.add_argument("--allow-unreviewed", action="store_true")
    fusion_profile = fusion_sub.add_parser("profile")
    fusion_profile.add_argument("--trace", type=Path, action="append", required=True)
    fusion_profile.add_argument("--out", type=Path, default=None)
    fusion_compare = fusion_sub.add_parser(
        "compare-models",
        help="compare linear, tree, and small neural surrogates on one grouped split",
    )
    fusion_compare.add_argument("--trace", type=Path, action="append", required=True)
    fusion_compare.add_argument("--optimizer-index", type=int, required=True)
    fusion_compare.add_argument("--constraint", action="append", required=True)
    fusion_compare.add_argument("--seed", type=int, default=0)
    fusion_compare.add_argument("--out", type=Path, required=True)
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
    fusion_evaluate.add_argument(
        "--modal-gpu",
        choices=MODAL_GPU_CHOICES,
        default=None,
        help="exact Modal accelerator shared by both arms; required for Modal evaluation",
    )
    fusion_evaluate.add_argument("--allow-unreviewed", action="store_true")
    fusion_evaluate.add_argument(
        "--no-warmup",
        action="store_true",
        help="include startup effects by skipping the unmeasured warmup pair",
    )
    fusion_evaluate.add_argument(
        "--out",
        type=Path,
        default=None,
        help="write the complete JSON report instead of printing it",
    )
    fusion_audit = fusion_sub.add_parser(
        "audit",
        help="audit a frozen linear artifact on disjoint held-out parent traces",
    )
    fusion_audit.add_argument("artifact", type=Path)
    fusion_audit.add_argument("--trace", type=Path, action="append", required=True)
    fusion_audit.add_argument("--out", type=Path, required=True)
    fusion_audit.add_argument("--max-normalized-mae", type=float, default=0.05)
    fusion_audit.add_argument("--min-spearman", type=float, default=0.90)
    fusion_audit.add_argument("--min-coverage", type=float, default=0.30)
    fusion_audit.add_argument("--min-groups", type=int, default=4)
    fusion_audit.add_argument("--allow-unreviewed", action="store_true")
    custom_mfe_audit = fusion_sub.add_parser(
        "audit-custom-mfe-sampled",
        help="audit the frozen sampled-window CUSTOM MFE candidate",
    )
    custom_mfe_audit.add_argument("--trace", type=Path, action="append", required=True)
    custom_mfe_audit.add_argument("--development-report", type=Path, required=True)
    custom_mfe_audit.add_argument("--workers", type=int, default=8)
    custom_mfe_audit.add_argument("--out", type=Path, required=True)
    custom_mfe_evaluate = fusion_sub.add_parser(
        "evaluate-custom-mfe",
        help="pair Proto with an exact-parallel or frozen sampled-window MFE bundle",
    )
    custom_mfe_evaluate.add_argument("collection", type=Path)
    custom_mfe_evaluate.add_argument("program_id")
    custom_mfe_evaluate.add_argument(
        "--mode",
        choices=("exact-parallel", "sampled-window"),
        required=True,
    )
    custom_mfe_evaluate.add_argument("--seed", type=int, action="append", required=True)
    custom_mfe_evaluate.add_argument("--workers", type=int, default=8)
    custom_mfe_evaluate.add_argument("--audit-report", type=Path, default=None)
    custom_mfe_evaluate.add_argument("--allow-unreviewed", action="store_true")
    custom_mfe_evaluate.add_argument("--no-warmup", action="store_true")
    custom_mfe_evaluate.add_argument("--out", type=Path, required=True)
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
    paper_parser.add_argument(
        "--search-doi",
        default=None,
        metavar="DOI",
        help="verify quotes against this DOI's Paperclip full text (e.g. a preprint)",
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
                print(f"checkpoint={session.directory}", flush=True)
                print(f"events={session.event_log_path}", flush=True)
                program, wall_ms, summary = _run_fixture(args.fixture, tier=args.tier)
        if summary is not None:
            print(json.dumps(summary, indent=2))
        sequence = program.constructs[0].joined_sequences[0].sequence
        print(f"fixture={args.fixture} tier={args.tier} wall_ms={wall_ms:.0f}")
        print(sequence[:120] + ("..." if len(sequence) > 120 else ""))
        return

    if args.command == "custom-reference-parity":
        from protofuse.phillip.program_builders import run_custom_reference_parity

        parity_report = run_custom_reference_parity(seed=args.seed, tier=args.tier)
        payload = json.dumps(parity_report, indent=2, allow_nan=False) + "\n"
        if args.out is None:
            print(payload, end="")
        else:
            _write_text_atomic(args.out, payload)
            print(f"parity={args.out}")
        if not parity_report["passed"]:
            raise SystemExit(1)
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
        from contextlib import AbstractContextManager, nullcontext

        from protofuse.sai.analyzer import load_reviewed_program
        from protofuse.sai.evaluation import apply_program_seed
        from protofuse.sai.hardware import experiment_hardware, pinned_modal_hardware
        from protofuse.sai.tracing import JsonlTraceWriter, trace_program_constraints

        traced_program = load_reviewed_program(args.collection, program_id=args.program_id)
        device: Literal["modal"] | None = "modal" if args.device == "modal" else None
        hardware_scope: AbstractContextManager[None]
        if args.modal_gpu == "auto":
            if device != "modal":
                raise ValueError("--modal-gpu auto requires --device modal")
            # Teacher scores are valid across supported accelerators, but timings are
            # not comparable when each deployed service selects from its own fallback
            # policy. Keep this path trace-only; paired evaluation still requires one
            # exact accelerator class.
            hardware_scope = nullcontext()
            hardware_report = {
                "purpose": "score_collection",
                "device": "modal",
                "accelerator": None,
                "selection_policy": "deployment_default",
                "timing_eligible": False,
                "context_id": "deployment-default",
                "pairing": "none",
                "max_containers_per_service": None,
                "retries": None,
                "scaledown_window_seconds": None,
                "identity_level": "unverified",
                "same_physical_accelerator_verified": False,
                "local_host": None,
            }
        else:
            hardware = experiment_hardware(
                device,
                args.modal_gpu,
                # Reuse one pinned option identity across a trace campaign so Modal can
                # retain warm model containers. Run/group IDs remain in every trace row;
                # changing this environment label per seed needlessly cold-started both
                # parent services without improving data isolation.
                context_id=(
                    f"trace-{traced_program.collection.manifest.collection_id}-"
                    f"{args.tier or 'unspecified'}"
                ),
            )
            hardware_scope = pinned_modal_hardware(hardware)
            hardware_report = hardware.as_dict()
        writer = JsonlTraceWriter(args.out)
        with (
            hardware_scope,
            trace_program_constraints(
                traced_program.program,
                writer,
                run_id=args.run_id,
                group_id=args.group_id,
                group_by_input_batch=args.group_by_input_batch,
                include_inputs=not args.hash_inputs_only,
                collection_id=traced_program.collection.manifest.collection_id,
                program_id=traced_program.entry.program_id,
                methodology_id=traced_program.collection.manifest.methodology_id,
                tier=args.tier,
            ),
        ):
            if args.seed is not None:
                apply_program_seed(traced_program.program, args.seed)
            traced_program.program.run(device=device)
        print(f"trace={args.out}")
        print(f"hardware={json.dumps(hardware_report, sort_keys=True)}")
        return

    if args.command == "fusion":
        from protofuse.sai.analyzer import load_reviewed_program
        from protofuse.sai.artifacts import file_sha256, load_fusion_artifact

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

        if args.fusion_command == "compare-models":
            from protofuse.sai.model import evo2_output_normalizations
            from protofuse.sai.model_comparison import compare_model_families
            from protofuse.sai.training import load_teacher_samples

            traces = tuple(args.trace)
            labels = tuple(args.constraint)
            samples = load_teacher_samples(
                traces,
                optimizer_index=args.optimizer_index,
                constraint_labels=labels,
            )
            evo2_labels = {
                "enformer_pattern_l1_sum",
                "borzoi_pattern_l1_sum",
            }
            output_normalizations = (
                evo2_output_normalizations(labels)
                if labels and set(labels) <= evo2_labels
                else ()
            )
            report = compare_model_families(
                samples,
                output_labels=labels,
                trace_paths=traces,
                output_normalizations=output_normalizations,
                seed=args.seed,
            )
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
            print(f"model_comparison={args.out}")
            return

        if args.fusion_command == "train":
            from protofuse.sai.model import evo2_output_normalizations
            from protofuse.sai.training import (
                load_teacher_samples,
                train_linear_ensemble,
                validate_teacher_trace_contract,
                write_trained_fusion,
            )

            training_program = load_reviewed_program(
                args.collection,
                program_id=args.program_id,
            )
            traces = tuple(args.trace)
            labels = tuple(args.constraint)
            validate_teacher_trace_contract(
                traces,
                program=training_program.program,
                optimizer_index=args.optimizer_index,
                constraint_labels=labels,
            )
            samples = load_teacher_samples(
                traces,
                optimizer_index=args.optimizer_index,
                constraint_labels=labels,
            )
            output_normalizations = (
                evo2_output_normalizations(labels)
                if training_program.collection.manifest.collection_id
                == "evo2-enformer-borzoi"
                else ()
            )
            training = train_linear_ensemble(
                samples,
                output_labels=labels,
                trace_paths=traces,
                output_normalizations=output_normalizations,
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

        if args.fusion_command == "audit":
            from protofuse.sai.audit import audit_frozen_fusion

            audit_report = audit_frozen_fusion(
                args.artifact,
                tuple(args.trace),
                max_normalized_mae=args.max_normalized_mae,
                min_spearman=args.min_spearman,
                min_coverage=args.min_coverage,
                min_groups=args.min_groups,
                require_reviewed=not args.allow_unreviewed,
            )
            _write_text_atomic(
                args.out,
                json.dumps(audit_report, indent=2, allow_nan=False) + "\n",
            )
            print(f"audit={args.out}")
            if not audit_report["passed"]:
                raise SystemExit(1)
            return

        if args.fusion_command == "audit-custom-mfe-sampled":
            from protofuse.sai.custom_mfe_audit import audit_sampled_custom_mfe
            from protofuse.sai.exact_custom import (
                FROZEN_CUSTOM_MFE_UNCERTAINTY_THRESHOLD_KCAL_MOL,
            )

            development = json.loads(args.development_report.read_text())
            split = development["dataset"]["split"]
            development_groups = tuple(
                group
                for key in ("train_groups", "calibration_groups", "audit_groups")
                for group in split[key]
            )
            audit_report = audit_sampled_custom_mfe(
                tuple(args.trace),
                development_trace_sha256=tuple(split["trace_sha256"]),
                development_groups=development_groups,
                uncertainty_threshold=(
                    FROZEN_CUSTOM_MFE_UNCERTAINTY_THRESHOLD_KCAL_MOL
                ),
                workers=args.workers,
            )
            _write_text_atomic(
                args.out,
                json.dumps(audit_report, indent=2, allow_nan=False) + "\n",
            )
            print(f"audit={args.out}")
            if not audit_report["passed"]:
                raise SystemExit(1)
            return

        if args.fusion_command == "evaluate-custom-mfe":
            from protofuse.sai.evaluation import evaluate_paired_transform
            from protofuse.sai.exact_custom import (
                FROZEN_CUSTOM_MFE_INTERCEPT_KCAL_MOL,
                FROZEN_CUSTOM_MFE_SLOPE,
                FROZEN_CUSTOM_MFE_UNCERTAINTY_THRESHOLD_KCAL_MOL,
                FROZEN_CUSTOM_MFE_WINDOW_STRIDE,
            )
            from protofuse.sai.optimizer import optimize_program
            from protofuse.sai.registry import FusionRegistry
            from protofuse.sai.transform import (
                build_exact_custom_mfe_bundle,
                build_sampled_custom_mfe_bundle,
            )

            if not args.allow_unreviewed:
                raise ValueError(
                    "CUSTOM MFE development bundles require --allow-unreviewed"
                )
            reference = load_reviewed_program(
                args.collection,
                program_id=args.program_id,
            )
            offline_metrics = None
            audit_report_sha256 = None
            if args.mode == "sampled-window":
                if args.audit_report is None:
                    raise ValueError("sampled-window evaluation requires --audit-report")
                external_audit = json.loads(args.audit_report.read_text())
                frozen_spec = external_audit.get("frozen_spec")
                audit_provenance = external_audit.get("provenance")
                audit_checks = external_audit.get("checks")
                heldout_group_count = (
                    audit_provenance.get("heldout_group_count")
                    if isinstance(audit_provenance, dict)
                    else None
                )
                if (
                    external_audit.get("schema_version") != "1.0"
                    or external_audit.get("status") != "pass"
                    or external_audit.get("passed") is not True
                    or not isinstance(audit_checks, dict)
                    or not audit_checks
                    or not all(value is True for value in audit_checks.values())
                    or isinstance(heldout_group_count, bool)
                    or not isinstance(heldout_group_count, int)
                    or heldout_group_count < 4
                    or not isinstance(frozen_spec, dict)
                    or frozen_spec.get("window_stride")
                    != FROZEN_CUSTOM_MFE_WINDOW_STRIDE
                    or frozen_spec.get("calibration_intercept_kcal_mol")
                    != FROZEN_CUSTOM_MFE_INTERCEPT_KCAL_MOL
                    or frozen_spec.get("calibration_slope") != FROZEN_CUSTOM_MFE_SLOPE
                    or frozen_spec.get("uncertainty_threshold_kcal_mol")
                    != FROZEN_CUSTOM_MFE_UNCERTAINTY_THRESHOLD_KCAL_MOL
                ):
                    raise ValueError("sampled-window external audit is missing, failed, or stale")
                audit_report_sha256 = file_sha256(args.audit_report)
                bundle = build_sampled_custom_mfe_bundle(
                    reference.program,
                    workers=args.workers,
                    window_stride=FROZEN_CUSTOM_MFE_WINDOW_STRIDE,
                    intercept=FROZEN_CUSTOM_MFE_INTERCEPT_KCAL_MOL,
                    slope=FROZEN_CUSTOM_MFE_SLOPE,
                    uncertainty_threshold=(
                        FROZEN_CUSTOM_MFE_UNCERTAINTY_THRESHOLD_KCAL_MOL
                    ),
                )
                audit_metrics = external_audit["metrics"]
                offline_metrics = {
                    "audit_mae": [audit_metrics["accepted_mae_kcal_mol"]],
                    "audit_rank_correlation": [audit_metrics["accepted_spearman"]],
                    "audit_selective_coverage": external_audit["samples"]["coverage"],
                    "audit_accepted_mae": [audit_metrics["accepted_mae_kcal_mol"]],
                    "audit_accepted_mae_q95_q05_fraction": [
                        audit_metrics["accepted_mae_q95_q05_fraction"]
                    ],
                }
            else:
                bundle = build_exact_custom_mfe_bundle(
                    reference.program,
                    workers=args.workers,
                )

            def transform_program(program: Program) -> Program:
                registry: FusionRegistry[Program] = FusionRegistry()
                registry.register(bundle)
                optimized = optimize_program(program, registry)
                if optimized.applied_fusions != (bundle.qualified_id,):
                    raise RuntimeError(
                        f"CUSTOM MFE bundle was not applied: {optimized.diagnostics}"
                    )
                return optimized.program

            provenance = {
                "collection_id": reference.collection.manifest.collection_id,
                "methodology_id": reference.collection.manifest.methodology_id,
                "program_id": reference.entry.program_id,
                "program_source_sha256": reference.entry.sha256,
                "fusion_id": bundle.fusion_id,
                "fusion_version": bundle.version,
                "reviewed": False,
                "workers": args.workers,
                "uncertainty_threshold_kcal_mol": (
                    FROZEN_CUSTOM_MFE_UNCERTAINTY_THRESHOLD_KCAL_MOL
                    if args.mode == "sampled-window"
                    else None
                ),
                "audit_report_sha256": audit_report_sha256,
                "seeds": tuple(args.seed),
            }

            def serialized(evaluation: Any) -> str:
                report = evaluation.as_dict()
                report["provenance"] = provenance
                return json.dumps(report, indent=2, allow_nan=False) + "\n"

            def persist_progress(evaluation: Any) -> None:
                _write_text_atomic(args.out, serialized(evaluation))

            evaluation = evaluate_paired_transform(
                lambda: load_reviewed_program(
                    args.collection,
                    program_id=args.program_id,
                ).program,
                transform_program,
                optimizer_index=0,
                seeds=args.seed,
                warmup=not args.no_warmup,
                offline_surrogate_metrics=offline_metrics,
                on_progress=persist_progress,
            )
            _write_text_atomic(args.out, serialized(evaluation))
            print(f"evaluation={args.out}")
            return

        from protofuse.sai.evaluation import evaluate_paired

        artifact = load_fusion_artifact(
            args.artifact,
            require_reviewed=not args.allow_unreviewed,
        )
        benchmark_program = load_reviewed_program(
            args.collection,
            program_id=args.program_id,
        )
        offline_metrics = (
            json.loads((artifact.root / "metrics.json").read_text())
            if (artifact.root / "metrics.json").is_file()
            else None
        )
        provenance = {
            "collection_id": benchmark_program.collection.manifest.collection_id,
            "methodology_id": benchmark_program.collection.manifest.methodology_id,
            "program_id": benchmark_program.entry.program_id,
            "program_source_sha256": benchmark_program.entry.sha256,
            "artifact_manifest_sha256": file_sha256(artifact.root / "manifest.json"),
            "fusion_id": artifact.manifest.fusion_id,
            "fusion_version": artifact.manifest.version,
            "model_sha256": artifact.manifest.model_sha256,
            "training_trace_sha256": artifact.manifest.training_trace_sha256,
            "split_manifest_sha256": artifact.manifest.split_manifest_sha256,
            "device": args.device,
            "seeds": tuple(args.seed),
        }

        def serialized(evaluation: Any) -> str:
            report = evaluation.as_dict()
            report["provenance"] = provenance
            return json.dumps(report, indent=2, allow_nan=False) + "\n"

        def persist_progress(evaluation: Any) -> None:
            if args.out is not None:
                _write_text_atomic(args.out, serialized(evaluation))

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
            modal_gpu=args.modal_gpu,
            warmup=not args.no_warmup,
            offline_surrogate_metrics=offline_metrics,
            on_progress=persist_progress,
        )
        payload = serialized(evaluation)
        if args.out is None:
            print(payload, end="")
        else:
            _write_text_atomic(args.out, payload)
            print(f"evaluation={args.out}")
        return

    if args.command == "paper":
        from protofuse.phillip.paper_review import build_paper_review, format_review

        paper_review = build_paper_review(
            args.fixture,
            offline=args.offline,
            text_path=args.text,
            search_doi=args.search_doi,
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
