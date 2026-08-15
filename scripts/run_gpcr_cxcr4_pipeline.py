#!/usr/bin/env -S uv run python
"""Run the GPCR miniprotein paper → Sai handoff pipeline with timing."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from time import perf_counter

from protofuse.phillip.handoff_pipeline import run_handoff_pipeline
from protofuse.phillip.paper_ingest import (
    GPCR_MINIPROTEIN_DOI,
    ingest_paper_text,
    save_paper_text,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ID = "gpcr-cxcr4-miniprotein"


def main() -> int:
    started = perf_counter()
    extra_stages: list[dict[str, float | str]] = []

    paper_text, ingest_source = ingest_paper_text(doi=GPCR_MINIPROTEIN_DOI)
    paper_path = save_paper_text(paper_text, filename="gpcr-miniprotein.txt")
    extra_stages.append(
        {
            "stage": f"paper_ingest ({ingest_source})",
            "elapsed_s": round(perf_counter() - started, 3),
        }
    )

    timing = run_handoff_pipeline(FIXTURE_ID, extra_stages=extra_stages)
    timing["paper_doi"] = GPCR_MINIPROTEIN_DOI
    timing["paper_path"] = str(paper_path.relative_to(REPO_ROOT))
    timing["paper_ingest_source"] = ingest_source

    timing_path = REPO_ROOT / "workspaces/phillip" / f"TIMING_{FIXTURE_ID}.json"
    timing_path.write_text(json.dumps(timing, indent=2) + "\n")

    print(json.dumps(timing, indent=2))
    print(f"\nSai handoff ready: {timing['handoff_path']}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
