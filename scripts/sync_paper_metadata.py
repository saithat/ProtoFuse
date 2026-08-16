#!/usr/bin/env python3
"""Refresh Crossref metadata cache used by the hackathon progress notebook."""

from __future__ import annotations

import argparse

from protofuse.phillip.paper_review import (
    CROSSREF_CACHE_PATH,
    REPO_ROOT,
    sync_crossref_metadata,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "dois",
        nargs="*",
        help="DOIs to refresh (default: all fixture DOIs)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=20,
        help="Crossref request timeout in seconds",
    )
    args = parser.parse_args()

    synced = sync_crossref_metadata(args.dois or None, timeout=args.timeout)
    for doi, record in sorted(synced.items()):
        title = record.title if record else "not found"
        print(f"{doi}: {title}")

    print(f"wrote {CROSSREF_CACHE_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
