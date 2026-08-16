#!/usr/bin/env python3
"""Sync curated primary figures via Paperclip into figure_manifest.json."""

from __future__ import annotations

import argparse

from protofuse.phillip.paper_figures import sync_all_primary_figures, sync_primary_figure
from protofuse.phillip.paper_profiles import MANIFEST_PATH, REPO_ROOT


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "collection_ids",
        nargs="*",
        help="Collections to sync (default: all curated primary-figure collections)",
    )
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="Do not call paperclip fetch when figures are missing",
    )
    args = parser.parse_args()

    if args.collection_ids:
        for collection_id in args.collection_ids:
            primary = sync_primary_figure(
                collection_id,
                fetch_if_missing=not args.no_fetch,
            )
            status = primary["paperclip_path"] if primary else "not found"
            print(f"{collection_id}: {status}")
    else:
        synced = sync_all_primary_figures(fetch_if_missing=not args.no_fetch)
        for collection_id, primary in sorted(synced.items()):
            cached = primary.get("file") or primary.get("url") or primary["paperclip_path"]
            print(f"{collection_id}: {cached}")

    print(f"wrote {MANIFEST_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
