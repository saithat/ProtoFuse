"""Resolve and cache primary paper figures via Paperclip."""

from __future__ import annotations

import re
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import quote

from protofuse.phillip.paper_ingest import (
    PaperSearchError,
    _ensure_paperclip_env,
    _run_paperclip,
    paperclip_document_path,
)
from protofuse.phillip.paper_profiles import (
    FIGURES_DIR,
    MANIFEST_PATH,
    PRIMARY_FIGURE_IDS,
    REPO_ROOT,
    load_figure_manifest,
    save_figure_manifest,
)
from protofuse.phillip.paper_review import DOI_RE
from protofuse.phillip.program_builders import load_fixture_spec

USER_AGENT = "Mozilla/5.0 (compatible; ProtoFuse/0.1; +https://example.com)"
CLIPBOARD_FOLDER = "/clipboard/protofuse-figures/"

# When the fixture DOI is missing from Paperclip, look up the preprint/full-text DOI instead.
PAPERCLIP_LOOKUP_DOIS: dict[str, str] = {
    "dnachisel-num1": "10.1101/2019.12.16.877480",
    "gpcr-cxcr4-miniprotein": "10.1101/2025.03.23.644666",
}

# Browser-loadable fallbacks when Paperclip stores figures on GCS (clipboard PDFs).
DISPLAY_URLS: dict[str, str] = {
    "dnachisel-num1": "https://www.biorxiv.org/content/10.1101/2019.12.16.877480v1/F1.large.jpg",
    "gpcr-cxcr4-miniprotein": "https://www.biorxiv.org/content/10.1101/2025.03.23.644666v3/F1.large.jpg",
    "boltz2-state-sweep": "https://www.biorxiv.org/content/10.64898/2026.01.23.701250v3/F1.large.jpg",
}

_FIGURE_FILE_RE = re.compile(r"\.(jpg|jpeg|png|gif|tif|tiff)$", re.IGNORECASE)
_FETCH_DOC_RE = re.compile(r"(usr_[a-f0-9]+|/papers/[^\s]+|/clipboard/[^\s]+)")


def _paperclip_installed() -> bool:
    return shutil.which("paperclip") is not None


def lookup_doi_for_collection(collection_id: str) -> str | None:
    override = PAPERCLIP_LOOKUP_DOIS.get(collection_id)
    if override:
        return override
    spec = load_fixture_spec(collection_id)
    identifier = spec.paper.identifier
    if identifier and DOI_RE.match(identifier):
        return identifier
    full_text = spec.paper.full_text_identifier
    if full_text and DOI_RE.match(full_text):
        return full_text
    return None


def _parse_figure_filenames(ls_output: str) -> list[str]:
    return [
        token
        for token in ls_output.split()
        if _FIGURE_FILE_RE.search(token) and not token.startswith("[")
    ]


def paperclip_list_figures(document_path: str) -> list[str]:
    proc = _run_paperclip(["ls", f"{document_path.rstrip('/')}/figures/"])
    if proc.returncode != 0:
        return []
    return _parse_figure_filenames(proc.stdout)


def _clipboard_path_for_doi(doi: str) -> str | None:
    list_proc = _run_paperclip(["ls", CLIPBOARD_FOLDER])
    if list_proc.returncode != 0:
        return None
    entries = [part for part in list_proc.stdout.split() if part.startswith("usr_")]
    for usr in reversed(entries):
        document_path = f"{CLIPBOARD_FOLDER.rstrip('/')}/{usr}"
        if not paperclip_list_figures(document_path):
            continue
        meta_proc = _run_paperclip(["cat", f"{document_path}/meta.json"])
        if meta_proc.returncode == 0 and doi in meta_proc.stdout:
            return document_path
    for usr in reversed(entries):
        document_path = f"{CLIPBOARD_FOLDER.rstrip('/')}/{usr}"
        if paperclip_list_figures(document_path):
            return document_path
    return None


def _resolve_document_path(doi: str, *, fetch_if_missing: bool) -> str | None:
    path = paperclip_document_path(doi)
    if path and paperclip_list_figures(path):
        return path

    clipboard_path = _clipboard_path_for_doi(doi)
    if clipboard_path:
        return clipboard_path

    if not fetch_if_missing:
        return path

    proc = _run_paperclip(["fetch", doi, "--into", CLIPBOARD_FOLDER], timeout=300)
    clipboard_path: str | None = None
    if proc.returncode == 0:
        tokens = _FETCH_DOC_RE.findall(proc.stdout)
        usr_ids = [token for token in tokens if token.startswith("usr_")]
        if usr_ids:
            clipboard_path = f"{CLIPBOARD_FOLDER.rstrip('/')}/{usr_ids[-1]}"
        else:
            for token in tokens:
                if token.startswith("/clipboard/"):
                    clipboard_path = token.rstrip("/")
                    break

        if clipboard_path is None:
            list_proc = _run_paperclip(["ls", CLIPBOARD_FOLDER])
            if list_proc.returncode == 0:
                entries = [part for part in list_proc.stdout.split() if part.startswith("usr_")]
                if entries:
                    clipboard_path = f"{CLIPBOARD_FOLDER.rstrip('/')}/{entries[-1]}"

    if clipboard_path and paperclip_list_figures(clipboard_path):
        return clipboard_path
    return path


def _match_figure_file(filenames: list[str], figure_id: str) -> str | None:
    if not filenames:
        return None
    normalized = figure_id.lower().replace(".", "")
    patterns = [
        normalized,
        normalized.replace("fig", "figure"),
        f"_{normalized}",
        f"{normalized}_",
    ]

    def _matches(filename: str) -> bool:
        lowered = filename.lower()
        return any(pattern in lowered for pattern in patterns)

    matched = [name for name in filenames if _matches(name)]
    if not matched and normalized in {"fig1", "f1", "figure1"}:
        matched = [
            name
            for name in filenames
            if re.search(r"(?:^|[_-])fig(?:ure)?[_-]?1(?:[_\.]|$)|^f1[_\.]", name, re.I)
        ]
    if not matched and normalized == "fig3":
        matched = [name for name in filenames if "fig3" in name.lower() or "figure3" in name.lower()]
    if not matched:
        return filenames[0]

    def _priority(name: str) -> tuple[int, str]:
        lowered = name.lower()
        if lowered.endswith((".jpg", ".jpeg", ".png")):
            return (0, name)
        if lowered.endswith((".tif", ".tiff")):
            return (1, name)
        if lowered.endswith(".gif"):
            return (2, name)
        return (3, name)

    return sorted(matched, key=_priority)[0]


def _springer_image_url(doi: str, filename: str) -> str:
    encoded_doi = quote(doi, safe="")
    media_name = filename
    if media_name.lower().endswith(".jpg"):
        media_name = media_name[:-4] + ".png"
    return (
        "https://media.springernature.com/full/springer-static/image/"
        f"art%3A{encoded_doi}/MediaObjects/{media_name}"
    )


def _download_http(url: str, destination: Path) -> bool:
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


def _download_paperclip_binary(paperclip_path: str, destination: Path) -> bool:
    if paperclip_path.startswith("/clipboard/"):
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("wb") as handle:
            proc = subprocess.run(  # noqa: S603
                ["paperclip", "cat", paperclip_path],
                check=False,
                stdout=handle,
                env=_ensure_paperclip_env(),
                timeout=120,
            )
    except (OSError, subprocess.SubprocessError):
        return False
    if proc.returncode != 0 or not destination.is_file() or destination.stat().st_size < 512:
        return False
    preview = destination.read_bytes()[:8]
    if preview.startswith(b"gs://") or preview.startswith(b"ERR:"):
        destination.unlink(missing_ok=True)
        return False
    return True


def _figure_caption(document_path: str, label: str) -> str:
    proc = _run_paperclip(["grep", "-i", "-m", "1", label, f"{document_path}/content.lines"])
    if proc.returncode != 0 or not proc.stdout.strip():
        return ""
    line = proc.stdout.splitlines()[0]
    if ": " in line:
        _, _, body = line.partition(": ")
        return body.strip()
    return line.strip()


def sync_primary_figure(collection_id: str, *, fetch_if_missing: bool = True) -> dict[str, Any] | None:
    """Discover the curated primary figure via Paperclip and cache metadata locally."""

    if not _paperclip_installed():
        raise PaperSearchError("the paperclip CLI is not installed")

    doi = lookup_doi_for_collection(collection_id)
    if not doi:
        return None

    figure_id = PRIMARY_FIGURE_IDS.get(collection_id, "Fig1")
    document_path = _resolve_document_path(doi, fetch_if_missing=fetch_if_missing)
    if not document_path:
        return None

    filenames = paperclip_list_figures(document_path)
    filename = _match_figure_file(filenames, figure_id)
    if filename is None:
        return None

    paperclip_path = f"{document_path.rstrip('/')}/figures/{filename}"
    label = f"Fig. {figure_id.removeprefix('Fig').removeprefix('F')}" if figure_id else filename
    caption = _figure_caption(document_path, label) or _figure_caption(document_path, "Figure 1")

    ext = Path(filename).suffix or ".jpg"
    local_path = FIGURES_DIR / collection_id / f"primary{ext}"
    local_file: str | None = None

    if doi.startswith("10.1186/"):
        springer_url = _springer_image_url(doi, filename)
        if _download_http(springer_url, local_path.with_suffix(".png")):
            local_file = str(local_path.with_suffix(".png").relative_to(REPO_ROOT))
    elif not _download_paperclip_binary(paperclip_path, local_path):
        display_url = DISPLAY_URLS.get(collection_id)
        if display_url:
            _download_http(display_url, local_path.with_suffix(".jpg"))

    if local_path.is_file():
        local_file = str(local_path.relative_to(REPO_ROOT))
    elif local_path.with_suffix(".png").is_file():
        local_file = str(local_path.with_suffix(".png").relative_to(REPO_ROOT))
    elif local_path.with_suffix(".jpg").is_file():
        local_file = str(local_path.with_suffix(".jpg").relative_to(REPO_ROOT))

    url = DISPLAY_URLS.get(collection_id)
    if not url and doi.startswith("10.1186/"):
        url = _springer_image_url(doi, filename)

    return {
        "id": figure_id,
        "label": label,
        "caption": caption,
        "file": local_file,
        "url": url,
        "paperclip_path": paperclip_path,
        "paperclip_document": document_path,
        "lookup_doi": doi,
    }


def sync_all_primary_figures(*, fetch_if_missing: bool = True) -> dict[str, dict[str, Any]]:
    manifest = load_figure_manifest()
    synced: dict[str, dict[str, Any]] = {}

    for collection_id in sorted(PRIMARY_FIGURE_IDS):
        primary = sync_primary_figure(collection_id, fetch_if_missing=fetch_if_missing)
        if primary is None:
            continue
        entry = manifest.setdefault(collection_id, {})
        if not isinstance(entry, dict):
            entry = {}
            manifest[collection_id] = entry
        entry["doi"] = primary.get("lookup_doi")
        entry["approved"] = primary["id"]
        entry["primary"] = primary
        if not entry.get("candidates"):
            entry["candidates"] = [primary]
        synced[collection_id] = primary

    save_figure_manifest(manifest)
    return synced
