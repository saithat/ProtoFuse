#!/usr/bin/env python3
"""Create web-sized JPEG siblings for large local paper figures."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from protofuse.phillip.paper_profiles import FIGURES_DIR, REPO_ROOT

MAX_EDGE = 1200
JPEG_QUALITY = 85
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}


def _sips_available() -> bool:
    return shutil.which("sips") is not None


def optimize_image(source: Path, *, max_edge: int, quality: int) -> Path:
    destination = source.with_name(f"{source.stem}-web.jpg")
    if destination.is_file() and destination.stat().st_mtime >= source.stat().st_mtime:
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    resized = destination.with_name(f"{source.stem}-resize-tmp.jpg")
    try:
        resize_proc = subprocess.run(  # noqa: S603
            ["sips", "-Z", str(max_edge), str(source), "--out", str(resized)],
            check=False,
            capture_output=True,
            text=True,
        )
        if resize_proc.returncode != 0:
            raise RuntimeError(resize_proc.stderr.strip() or "sips resize failed")

        format_proc = subprocess.run(  # noqa: S603
            [
                "sips",
                "-s",
                "format",
                "jpeg",
                "-s",
                "formatOptions",
                str(quality),
                str(resized),
                "--out",
                str(destination),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if format_proc.returncode != 0:
            raise RuntimeError(format_proc.stderr.strip() or "sips format failed")
    finally:
        resized.unlink(missing_ok=True)
    return destination


def iter_source_images(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    sources: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        if path.stem.endswith("-web"):
            continue
        sources.append(path)
    return sources


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Figure files or directories (default: data/papers/figures)",
    )
    parser.add_argument("--max-edge", type=int, default=MAX_EDGE)
    parser.add_argument("--quality", type=int, default=JPEG_QUALITY)
    args = parser.parse_args()

    if not _sips_available():
        print("sips is required (macOS); install nothing on Linux without sips", file=sys.stderr)
        raise SystemExit(1)

    roots = args.paths or [FIGURES_DIR]
    sources: list[Path] = []
    for root in roots:
        if root.is_file():
            sources.append(root)
        else:
            sources.extend(iter_source_images(root))

    if not sources:
        print("no figure images found")
        return

    for source in sources:
        try:
            destination = optimize_image(source, max_edge=args.max_edge, quality=args.quality)
        except RuntimeError as exc:
            rel_source = source.relative_to(REPO_ROOT)
            print(f"skip {rel_source}: {exc}", file=sys.stderr)
            continue
        rel_source = source.relative_to(REPO_ROOT)
        rel_dest = destination.relative_to(REPO_ROOT)
        print(f"{rel_source} -> {rel_dest} ({destination.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
