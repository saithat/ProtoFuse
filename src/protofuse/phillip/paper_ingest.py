"""Fetch paper full text for Phillip's extraction pipeline."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from urllib.request import urlopen

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]
PAPERS_DIR = REPO_ROOT / "data" / "papers"

# Nature article + bioRxiv preprint (full methods on preprint).
GPCR_MINIPROTEIN_DOI = "10.1038/s41586-026-10656-8"
GPCR_MINIPROTEIN_PREPRINT_DOI = "10.1101/2025.03.23.644666"
GPCR_MINIPROTEIN_PREPRINT_URL = (
    "https://www.biorxiv.org/content/10.1101/2025.03.23.644666v1.full-text"
)

_PAPER_PATH_RE = re.compile(r"(/papers/[^\s]+|/clipboard/[^\s]+)")


class PaperIngestError(RuntimeError):
    """Raised when no ingestion backend can retrieve paper text."""


def _ensure_paperclip_env() -> dict[str, str]:
    load_dotenv(REPO_ROOT / ".env")
    return os.environ.copy()


def _run_paperclip(args: list[str], *, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["paperclip", *args],
        check=False,
        capture_output=True,
        text=True,
        env=_ensure_paperclip_env(),
        timeout=timeout,
    )


def _paperclip_lookup_path(doi: str) -> str | None:
    """Resolve a corpus or clipboard VFS path for a DOI via `paperclip lookup`."""

    proc = _run_paperclip(["lookup", "doi", doi])
    if proc.returncode != 0:
        return None
    match = _PAPER_PATH_RE.search(proc.stdout)
    if not match:
        return None
    return match.group(1).rstrip("/")


def _paperclip_read_content(path: str) -> str | None:
    """Read line-numbered full text from a Paperclip document path."""

    proc = _run_paperclip(["cat", f"{path}/content.lines"])
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    lines: list[str] = []
    for line in proc.stdout.splitlines():
        if line.startswith("L") and ": " in line:
            _, _, body = line.partition(": ")
            lines.append(body)
        else:
            lines.append(line)
    text = "\n".join(lines).strip()
    return text or None


def _paperclip_fetch_to_clipboard(doi: str, *, folder: str) -> str | None:
    """Fetch via browser/cookies into clipboard, then read content.lines."""

    proc = _run_paperclip(["fetch", doi, "--into", folder])
    if proc.returncode != 0:
        return None
    match = _PAPER_PATH_RE.search(proc.stdout)
    if not match:
        # Fetch succeeded but path not printed — scan clipboard folder listing.
        list_proc = _run_paperclip(["ls", folder])
        if list_proc.returncode != 0:
            return None
        match = _PAPER_PATH_RE.search(list_proc.stdout)
        if not match:
            return None
    return _paperclip_read_content(match.group(1).rstrip("/"))


def _paperclip_ingest(doi: str, *, preprint_doi: str | None = None) -> str | None:
    """Try Paperclip lookup, then fetch-into-clipboard, for primary and preprint DOIs."""

    if shutil.which("paperclip") is None:
        return None

    for candidate in (doi, preprint_doi):
        if not candidate:
            continue
        path = _paperclip_lookup_path(candidate)
        if path:
            text = _paperclip_read_content(path)
            if text:
                return text
        text = _paperclip_fetch_to_clipboard(
            candidate,
            folder="/clipboard/gpcr-miniprotein/",
        )
        if text:
            return text
    return None


def _http_fetch_text(url: str) -> str:
    with urlopen(url, timeout=60) as response:  # noqa: S310 -- trusted public preprint URL
        raw = response.read()
    return raw.decode("utf-8", errors="replace")


def ingest_paper_text(
    *,
    doi: str = GPCR_MINIPROTEIN_DOI,
    preprint_doi: str = GPCR_MINIPROTEIN_PREPRINT_DOI,
    fallback_url: str = GPCR_MINIPROTEIN_PREPRINT_URL,
    local_path: Path | None = None,
) -> tuple[str, str]:
    """Return `(text, source_label)` using Paperclip, local file, then HTTP fallback."""

    if local_path is not None and local_path.is_file():
        return local_path.read_text(), f"local:{local_path}"

    paperclip_text = _paperclip_ingest(doi, preprint_doi=preprint_doi)
    if paperclip_text:
        return paperclip_text, f"paperclip:{doi}"

    default_local = PAPERS_DIR / "gpcr-miniprotein.txt"
    if default_local.is_file():
        return default_local.read_text(), f"local:{default_local}"

    if fallback_url:
        try:
            return _http_fetch_text(fallback_url), f"http:{fallback_url}"
        except OSError:
            if default_local.is_file():
                return default_local.read_text(), f"local:{default_local}"

    raise PaperIngestError(
        f"could not ingest paper text for {doi}; run `paperclip login` or set PAPERCLIP_API_KEY"
    )


def save_paper_text(
    text: str,
    *,
    filename: str,
    papers_dir: Path = PAPERS_DIR,
) -> Path:
    papers_dir.mkdir(parents=True, exist_ok=True)
    path = papers_dir / filename
    path.write_text(text)
    return path
