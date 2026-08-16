"""Fetch paper full text for Phillip's extraction pipeline."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen

REPO_ROOT = Path(__file__).resolve().parents[3]
PAPERS_DIR = REPO_ROOT / "data" / "papers"

# Nature article + bioRxiv preprint (full methods on preprint).
GPCR_MINIPROTEIN_DOI = "10.1038/s41586-026-10656-8"
GPCR_MINIPROTEIN_PREPRINT_DOI = "10.1101/2025.03.23.644666"
GPCR_MINIPROTEIN_PREPRINT_URL = (
    "https://www.biorxiv.org/content/10.1101/2025.03.23.644666v1.full-text"
)

_PAPER_PATH_RE = re.compile(r"(/papers/[^\s]+|/clipboard/[^\s]+)")

# `paperclip lookup` prints "<doc_id> · <venue> · <date>" rather than a VFS path.
_DOC_ID_RE = re.compile(r"^\s*([A-Za-z0-9_.:-]+)\s+·\s", re.MULTILINE)

# Lines inside content.lines are emitted as "L<n>: <text>".
_NUMBERED_LINE_RE = re.compile(r"^L(\d+):\s?(.*)$")

# `cat` prefixes large documents with e.g. "[~45744 tokens total, showing first ~1000 chars]".
_TRUNCATION_RE = re.compile(r"showing first ~?\d+ chars")

# The shell reports failures on stdout as "ERR: vsh: ..." while still exiting 0.
_GREP_ERROR_RE = re.compile(r"^ERR:\s*(.+)$", re.MULTILINE)
_NO_MATCH_MARKER = "(no matches found)"
_TRANSIENT_ERROR_RE = re.compile(r"unavailable|timed out|temporarily|try again", re.IGNORECASE)


class PaperIngestError(RuntimeError):
    """Raised when no ingestion backend can retrieve paper text."""


class PaperSearchError(RuntimeError):
    """Raised when a Paperclip search fails, as distinct from finding nothing."""


def _ensure_paperclip_env() -> dict[str, str]:
    from protofuse.env import load_repo_env

    load_repo_env()
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


def paperclip_document_path(doi: str) -> str | None:
    """Resolve a Paperclip VFS document path for a DOI via `paperclip lookup`.

    Lookup reports a document id, not a path, so the id is joined onto /papers/.
    """

    if shutil.which("paperclip") is None:
        return None
    proc = _run_paperclip(["lookup", "doi", doi])
    if proc.returncode != 0:
        return None
    path_match = _PAPER_PATH_RE.search(proc.stdout)
    if path_match:
        return path_match.group(1).rstrip("/")
    id_match = _DOC_ID_RE.search(proc.stdout)
    if id_match:
        return f"/papers/{id_match.group(1)}"
    return None


def paperclip_grep(
    document_path: str,
    pattern: str,
    *,
    ignore_case: bool = True,
    context: int = 0,
    timeout: int = 120,
    attempts: int = 3,
    retry_delay: float = 4.0,
) -> list[tuple[int, str]]:
    """Return `(line_number, text)` for literal matches inside a Paperclip document.

    Fixed-string matching keeps quoted punctuation from being read as a regex. Matched
    lines come back whole, unlike `cat`, which returns only a truncated preview.

    The pattern is passed positionally because this grep silently reports no matches when
    given `-e`. Errors are detected from the output rather than the exit status, which
    stays 0 even when the document store is unavailable; without that check an outage
    would be indistinguishable from a quote that genuinely is not in the paper. Document
    storage is intermittently unavailable, so transient failures are retried.
    """

    if shutil.which("paperclip") is None:
        raise PaperSearchError("the paperclip CLI is not installed")
    if pattern.startswith("-"):
        raise PaperSearchError(f"cannot search for a pattern starting with '-': {pattern!r}")

    args = ["grep", "-F"]
    if ignore_case:
        args.append("-i")
    if context > 0:
        args.extend(["-C", str(context)])
    args.extend([pattern, f"{document_path}/content.lines"])

    for attempt in range(1, attempts + 1):
        proc = _run_paperclip(args, timeout=timeout)
        error = _GREP_ERROR_RE.search(proc.stdout)
        if proc.returncode == 0 and error is None:
            if _NO_MATCH_MARKER in proc.stdout:
                return []
            return _parse_numbered_lines(proc.stdout)

        detail = error.group(1).strip() if error else proc.stderr.strip()
        transient = error is not None and _TRANSIENT_ERROR_RE.search(detail) is not None
        if not transient or attempt == attempts:
            raise PaperSearchError(detail or f"searching {document_path} failed")
        time.sleep(retry_delay * attempt)

    raise PaperSearchError(f"searching {document_path} failed after {attempts} attempts")


def _parse_numbered_lines(output: str) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for line in output.splitlines():
        match = _NUMBERED_LINE_RE.match(line.strip())
        if match:
            hits.append((int(match.group(1)), match.group(2).strip()))
    return hits


def _paperclip_read_content(path: str) -> str | None:
    """Read line-numbered full text from a Paperclip document path.

    `cat` answers large documents with a truncated preview. Returning that as full text
    would make quote checks fail on text that is merely absent from the preview, so a
    truncated response is treated as no text at all.
    """

    proc = _run_paperclip(["cat", f"{path}/content.lines"])
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    if _TRUNCATION_RE.search(proc.stdout):
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


def _paperclip_ingest(
    doi: str,
    *,
    preprint_doi: str | None = None,
    clipboard_folder: str = "/clipboard/protofuse/",
) -> str | None:
    """Try Paperclip lookup, then fetch-into-clipboard, for primary and preprint DOIs."""

    if shutil.which("paperclip") is None:
        return None

    for candidate in (doi, preprint_doi):
        if not candidate:
            continue
        path = paperclip_document_path(candidate)
        if path:
            text = _paperclip_read_content(path)
            if text:
                return text
        text = _paperclip_fetch_to_clipboard(candidate, folder=clipboard_folder)
        if text:
            return text
    return None


def _http_fetch_text(url: str) -> str:
    with urlopen(url, timeout=60) as response:  # noqa: S310 -- trusted public preprint URL
        raw: bytes = response.read()
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
