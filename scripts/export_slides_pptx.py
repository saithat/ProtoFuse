#!/usr/bin/env python3
"""Export ProtoFuse evaluation HTML slides to PowerPoint for Google Drive import."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from build_evaluation_report import _export_slides_pptx


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Export ProtoFuse evaluation HTML slides to PowerPoint (.pptx)."
    )
    parser.add_argument(
        "--html",
        type=Path,
        default=root / "reports" / "protofuse-evaluation-slides.html",
        help="source slide deck HTML",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "reports" / "protofuse-evaluation-slides.pptx",
        help="destination PowerPoint file",
    )
    args = parser.parse_args()
    _export_slides_pptx(args.html, args.output)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
