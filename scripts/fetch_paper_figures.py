#!/usr/bin/env python3
"""Download candidate paper figures for dashboard figure approval."""

from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import quote

from protofuse.phillip.paper_profiles import (
    FIGURES_DIR,
    MANIFEST_PATH,
    load_figure_manifest,
    load_paper_profile,
    save_figure_manifest,
)
from protofuse.phillip.paper_review import DOI_RE

REPO_ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = "Mozilla/5.0 (compatible; ProtoFuse/0.1; +https://example.com)"


def _fetch_json(url: str) -> dict[str, Any] | None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _download(url: str, destination: Path) -> bool:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "image/*"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            body = response.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        return False
    if len(body) < 512:
        return False
    destination.write_bytes(body)
    return True


def _epmc_pmcid(doi: str) -> str | None:
    payload = _fetch_json(
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        f"?query=DOI:{doi}&format=json&pageSize=1"
    )
    if not payload:
        return None
    hits = payload.get("resultList", {}).get("result", [])
    if not hits:
        return None
    pmcid = hits[0].get("pmcid")
    return str(pmcid) if pmcid else None


def _figures_from_pmc(pmcid: str) -> list[dict[str, str]]:
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            xml_text = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return []

    figures: list[dict[str, str]] = []
    for match in re.finditer(
        r'<fig id="([^"]+)".*?<label>([^<]+)</label>.*?<p>(.*?)</p>.*?xlink:href="([^"]+)"',
        xml_text,
        re.S,
    ):
        caption = re.sub(r"<[^>]+>", " ", match.group(3))
        caption = re.sub(r"\s+", " ", caption).strip()
        figures.append(
            {
                "id": match.group(1),
                "label": match.group(2).strip(),
                "caption": caption,
                "href": match.group(4),
                "pmcid": pmcid,
            }
        )
    return figures


def _springer_image_url(doi: str, filename: str) -> str:
    encoded_doi = quote(doi, safe="")
    if filename.lower().endswith(".jpg"):
        filename = filename[:-4] + ".png"
    return (
        "https://media.springernature.com/full/springer-static/image/"
        f"art%3A{encoded_doi}/MediaObjects/{filename}"
    )


def _candidate_image_url(doi: str, raw: dict[str, str]) -> str:
    href = raw["href"]
    if doi.startswith("10.1186/"):
        return _springer_image_url(doi, href)
    if "pmcid" in raw:
        return f"https://www.ncbi.nlm.nih.gov/pmc/articles/{raw['pmcid']}/bin/{href}"
    return href


def fetch_candidates_for_collection(collection_id: str) -> list[dict[str, Any]]:
    profile = load_paper_profile(collection_id, fetch_online=False)
    identifier = profile.identifier
    if not identifier or not DOI_RE.match(identifier):
        return []

    raw_figures: list[dict[str, str]] = []
    pmcid = _epmc_pmcid(identifier)
    if pmcid:
        raw_figures.extend(_figures_from_pmc(pmcid))

    candidates: list[dict[str, Any]] = []
    target_dir = FIGURES_DIR / collection_id
    for raw in raw_figures:
        image_url = _candidate_image_url(identifier, raw)
        ext = ".png" if image_url.endswith(".png") else ".jpg"
        destination = target_dir / f"{raw['id']}{ext}"
        local_file: str | None = None
        if _download(image_url, destination):
            local_file = str(destination.relative_to(REPO_ROOT))
        candidates.append(
            {
                "id": raw["id"],
                "label": raw["label"],
                "caption": raw["caption"],
                "file": local_file,
                "url": image_url,
            }
        )
    return candidates


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "collection_ids",
        nargs="*",
        help="Fixture/collection IDs to fetch (default: all DOI-backed fixtures)",
    )
    parser.add_argument(
        "--approve",
        nargs=2,
        metavar=("COLLECTION_ID", "FIGURE_ID"),
        help="Set the approved primary figure id in figure_manifest.json",
    )
    args = parser.parse_args()

    if args.approve:
        collection_id, figure_id = args.approve
        manifest = load_figure_manifest()
        entry = manifest.setdefault(collection_id, {})
        if not isinstance(entry, dict):
            entry = {}
            manifest[collection_id] = entry
        entry["approved"] = figure_id
        save_figure_manifest(manifest)
        print(f"approved {collection_id} -> {figure_id}")
        return

    manifest = load_figure_manifest()
    collection_ids = args.collection_ids
    if not collection_ids:
        collection_ids = sorted(
            path.name
            for path in (REPO_ROOT / "workspaces" / "phillip" / "fixtures").iterdir()
            if path.is_dir() and (path / "methodology.json").is_file()
        )

    for collection_id in collection_ids:
        profile = load_paper_profile(collection_id, fetch_online=False)
        if not profile.identifier or not DOI_RE.match(profile.identifier):
            print(f"skip {collection_id}: no DOI")
            continue
        candidates = fetch_candidates_for_collection(collection_id)
        entry = manifest.setdefault(collection_id, {})
        if not isinstance(entry, dict):
            entry = {}
            manifest[collection_id] = entry
        entry["doi"] = profile.identifier
        entry["candidates"] = candidates
        entry.setdefault("approved", entry.get("approved"))
        downloaded = sum(1 for candidate in candidates if candidate.get("file"))
        print(f"{collection_id}: {len(candidates)} candidate(s), {downloaded} downloaded")

    save_figure_manifest(manifest)
    print(f"wrote {MANIFEST_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
