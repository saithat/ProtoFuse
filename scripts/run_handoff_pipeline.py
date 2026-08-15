#!/usr/bin/env -S uv run python
"""Generate and finalize a frozen program collection for Sai handoff."""

from __future__ import annotations

import argparse
import json
import sys

from protofuse.phillip import compile_proto_plan, recommend_topologies
from protofuse.phillip.handoff_config import HANDOFF_CONFIGS, handoff_config_for
from protofuse.phillip.handoff_pipeline import run_handoff_pipeline
from protofuse.phillip.program_builders import load_fixture_spec
from protofuse.phillip.registries import lookup_registry, profile_for_fixture


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "fixture",
        choices=sorted(HANDOFF_CONFIGS),
        help="reviewed fixture ID to hand off",
    )
    parser.add_argument(
        "--collection-id",
        default=None,
        help="override collection folder name (defaults to fixture ID)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate fixture and compile plan only; do not write programs",
    )
    args = parser.parse_args()

    if args.dry_run:
        config = handoff_config_for(args.fixture)
        spec = load_fixture_spec(args.fixture)
        profile = profile_for_fixture(args.fixture)
        plan = compile_proto_plan(
            spec,
            recommend_topologies(spec)[0],
            registry=lookup_registry(profile.registry_name),
            device=config.compile_device,
        )
        print(
            json.dumps(
                {
                    "fixture_id": args.fixture,
                    "executable": plan.executable,
                    "unresolved": plan.unresolved,
                    "compile_device": config.compile_device,
                },
                indent=2,
            )
        )
        return 0 if plan.executable else 1

    timing = run_handoff_pipeline(args.fixture, collection_id=args.collection_id)
    print(json.dumps(timing, indent=2))
    print(f"\nSai handoff ready: {timing['handoff_path']}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
