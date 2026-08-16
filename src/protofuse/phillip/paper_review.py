"""Pull up a paper next to its encoded methodology for human review.

Phillip's one irreducible manual step is judging whether a fixture faithfully
represents its paper. This module assembles everything needed for that judgement:
registered paper metadata, the abstract, local full text when present, and a
verbatim check of every evidence quote.
"""

from __future__ import annotations

import json
import re
import textwrap
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from protofuse.phillip.contracts import Evidence, MethodologySpec
from protofuse.phillip.program_builders import load_fixture_spec

REPO_ROOT = Path(__file__).resolve().parents[3]
CROSSREF_WORK_URL = "https://api.crossref.org/works/{doi}"
USER_AGENT = "ProtoFuse/0.1 (paper review; mailto:noreply@example.com)"
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
_JATS_TAG_RE = re.compile(r"<[^>]+>")
_WORD_RE = re.compile(r"[a-z0-9]+")

TitleAgreement = Literal["match", "near_match", "mismatch", "unknown"]
LookupStatus = Literal[
    "registered",
    "variant_of_registered",
    "not_registered",
    "not_a_doi",
    "offline",
]


@dataclass(frozen=True)
class PaperRecord:
    """Metadata for a DOI as actually registered with Crossref."""

    doi: str
    title: str
    container: str | None
    year: int | None
    authors: tuple[str, ...]
    abstract: str | None
    url: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "doi": self.doi,
            "title": self.title,
            "container": self.container,
            "year": self.year,
            "authors": list(self.authors),
            "has_abstract": self.abstract is not None,
            "url": self.url,
        }


@dataclass(frozen=True)
class QuoteCheck:
    component: str
    quote: str
    found: bool
    section: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "component": self.component,
            "quote": self.quote,
            "found": self.found,
            "section": self.section,
        }


@dataclass
class PaperReview:
    fixture_id: str
    claimed_title: str
    claimed_identifier: str | None
    lookup_status: LookupStatus
    record: PaperRecord | None = None
    title_agreement: TitleAgreement = "unknown"
    full_text_path: Path | None = None
    full_text_words: int = 0
    quote_checks: list[QuoteCheck] = field(default_factory=list)
    components: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def unverified_quotes(self) -> list[QuoteCheck]:
        return [check for check in self.quote_checks if not check.found]

    def as_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "claimed_title": self.claimed_title,
            "claimed_identifier": self.claimed_identifier,
            "lookup_status": self.lookup_status,
            "title_agreement": self.title_agreement,
            "record": self.record.as_dict() if self.record else None,
            "full_text_path": str(self.full_text_path) if self.full_text_path else None,
            "full_text_words": self.full_text_words,
            "quote_checks": [check.as_dict() for check in self.quote_checks],
            "notes": self.notes,
        }


def _normalize_words(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def _strip_markup(text: str) -> str:
    without_tags = _JATS_TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", without_tags).strip()


def _fetch_json(url: str, *, timeout: int) -> dict[str, Any] | None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _record_from_crossref(message: dict[str, Any]) -> PaperRecord:
    titles = message.get("title") or []
    authors: list[str] = []
    for author in message.get("author") or []:
        family = str(author.get("family", "")).strip()
        given = str(author.get("given", "")).strip()
        name = f"{given} {family}".strip() if family or given else ""
        if name:
            authors.append(name)
    containers = message.get("container-title") or []
    issued = (message.get("issued") or {}).get("date-parts") or [[]]
    year = None
    if issued and issued[0]:
        try:
            year = int(issued[0][0])
        except (TypeError, ValueError):
            year = None
    abstract = message.get("abstract")
    doi = str(message.get("DOI", ""))
    return PaperRecord(
        doi=doi,
        title=_strip_markup(str(titles[0])) if titles else "",
        container=_strip_markup(str(containers[0])) if containers else None,
        year=year,
        authors=tuple(authors),
        abstract=_strip_markup(str(abstract)) if abstract else None,
        url=str(message.get("URL") or f"https://doi.org/{doi}"),
    )


def fetch_paper_record(doi: str, *, timeout: int = 20) -> PaperRecord | None:
    """Look up a DOI's registered metadata, including the abstract when deposited."""

    payload = _fetch_json(CROSSREF_WORK_URL.format(doi=doi), timeout=timeout)
    if not payload:
        return None
    message = payload.get("message")
    if not isinstance(message, dict):
        return None
    return _record_from_crossref(message)


def _doi_variants(identifier: str) -> list[str]:
    """Yield the identifier plus base DOIs after stripping hand-added suffixes."""

    variants = [identifier]
    candidate = identifier
    while "-" in candidate.rsplit("/", 1)[-1]:
        candidate = candidate.rsplit("-", 1)[0]
        if DOI_RE.match(candidate):
            variants.append(candidate)
    return variants


def compare_titles(claimed: str, registered: str) -> TitleAgreement:
    claimed_words = _normalize_words(claimed)
    registered_words = _normalize_words(registered)
    if not claimed_words or not registered_words:
        return "unknown"
    if claimed_words == registered_words:
        return "match"
    overlap = len(set(claimed_words) & set(registered_words))
    ratio = overlap / max(len(set(claimed_words)), len(set(registered_words)))
    if ratio >= 0.7:
        return "near_match"
    return "mismatch"


def local_paper_text(
    spec: MethodologySpec,
    *,
    text_path: Path | None = None,
) -> tuple[Path, str] | None:
    """Return local paper text, preferring an explicit override over the fixture source."""

    if text_path is not None:
        path = text_path if text_path.is_absolute() else REPO_ROOT / text_path
        if not path.is_file():
            return None
        return path, path.read_text(errors="replace")

    source_path = spec.paper.source_path
    if not source_path:
        return None
    path = REPO_ROOT / source_path
    if not path.is_file() or path.suffix.lower() not in {".txt", ".md"}:
        return None
    return path, path.read_text(errors="replace")


def _iter_evidence(spec: MethodologySpec) -> list[tuple[str, Evidence]]:
    pairs: list[tuple[str, Evidence]] = []
    for kind, items in (
        ("generator", spec.generators),
        ("constraint", spec.constraints),
        ("optimizer", spec.optimizers),
    ):
        for item in items:
            for evidence in item.evidence:
                pairs.append((f"{kind} {item.name}", evidence))
    return pairs


def _quote_fragments(quote: str) -> list[str]:
    """Split an abridged quote on ellipses so each retained fragment is checked."""

    parts = re.split(r"\.\.\.|…", quote)
    return [" ".join(_normalize_words(part)) for part in parts if _normalize_words(part)]


def _fragments_appear_in_order(fragments: list[str], haystack: str) -> bool:
    cursor = 0
    for fragment in fragments:
        position = haystack.find(fragment, cursor)
        if position == -1:
            return False
        cursor = position + len(fragment)
    return True


def verify_quotes(spec: MethodologySpec, paper_text: str) -> list[QuoteCheck]:
    """Check each evidence quote appears verbatim in the paper, ignoring whitespace.

    Quotes abridged with an ellipsis pass when every retained fragment appears in order.
    """

    haystack = " ".join(_normalize_words(paper_text))
    checks: list[QuoteCheck] = []
    for component, evidence in _iter_evidence(spec):
        fragments = _quote_fragments(evidence.quote)
        checks.append(
            QuoteCheck(
                component=component,
                quote=evidence.quote,
                found=bool(fragments) and _fragments_appear_in_order(fragments, haystack),
                section=evidence.section,
            )
        )
    return checks


def _components(spec: MethodologySpec) -> list[tuple[str, str, dict[str, Any]]]:
    rows: list[tuple[str, str, dict[str, Any]]] = []
    for kind, items in (
        ("generator", spec.generators),
        ("constraint", spec.constraints),
        ("optimizer", spec.optimizers),
    ):
        for item in items:
            rows.append((kind, item.name, dict(item.parameters)))
    return rows


def build_paper_review(
    fixture_id: str,
    *,
    offline: bool = False,
    timeout: int = 20,
    text_path: Path | None = None,
) -> PaperReview:
    """Assemble paper metadata, abstract, full text, and quote checks for one fixture."""

    spec = load_fixture_spec(fixture_id)
    identifier = spec.paper.identifier
    review = PaperReview(
        fixture_id=fixture_id,
        claimed_title=spec.paper.title,
        claimed_identifier=identifier,
        lookup_status="offline" if offline else "not_registered",
        components=_components(spec),
    )

    if not identifier or not DOI_RE.match(identifier):
        review.lookup_status = "not_a_doi"
        review.notes.append(
            f"identifier {identifier!r} is not a DOI; this fixture is not tied to a "
            "registered publication"
        )
    elif offline:
        review.notes.append("offline mode: skipped registry lookup")
    else:
        for index, candidate in enumerate(_doi_variants(identifier)):
            record = fetch_paper_record(candidate, timeout=timeout)
            if record is None:
                continue
            review.record = record
            review.lookup_status = "registered" if index == 0 else "variant_of_registered"
            if index > 0:
                review.notes.append(
                    f"{identifier!r} is not registered; it is a local variant of {candidate!r}"
                )
            review.title_agreement = compare_titles(spec.paper.title, record.title)
            break
        else:
            review.notes.append(f"{identifier!r} did not resolve in the Crossref registry")

    local = local_paper_text(spec, text_path=text_path)
    if local is None:
        review.notes.append(
            "no local full text; evidence quotes cannot be machine-verified "
            "(papers are gitignored)"
        )
        return review

    path, text = local
    review.full_text_path = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
    review.full_text_words = len(text.split())
    review.quote_checks = verify_quotes(spec, text)

    unverified = len(review.unverified_quotes)
    if unverified and unverified == len(review.quote_checks):
        review.notes.append(
            "no quote matched this text, so the quotes were probably taken from a different "
            "document (a preprint, or a Methods section the ingest did not capture). Re-check "
            "with `--text <path>` before concluding they were invented"
        )

    return review


def format_review(review: PaperReview, *, abstract_only: bool = False, width: int = 96) -> str:
    """Render a human review sheet for one fixture."""

    lines: list[str] = [f"PAPER REVIEW — {review.fixture_id}", ""]
    lines.append(f"  fixture claims : {review.claimed_title}")
    lines.append(f"  identifier     : {review.claimed_identifier or '(none)'}")

    status_label = {
        "registered": "resolves in registry",
        "variant_of_registered": "hand-edited variant of a real DOI",
        "not_registered": "DID NOT RESOLVE",
        "not_a_doi": "NOT A DOI",
        "offline": "not checked (offline)",
    }[review.lookup_status]
    lines.append(f"  registry       : {status_label}")

    record = review.record
    if record is not None:
        agreement = {
            "match": "titles match",
            "near_match": "titles nearly match",
            "mismatch": (
                "titles differ — confirm the fixture title is a local label for a "
                "section or figure of this paper, not a different paper"
            ),
            "unknown": "title comparison inconclusive",
        }[review.title_agreement]
        lines.append(f"  registered as  : {record.title}")
        byline = ", ".join(record.authors[:3])
        if len(record.authors) > 3:
            byline += " et al."
        venue = " · ".join(part for part in (record.container, str(record.year or "")) if part)
        if byline or venue:
            lines.append(f"  authors/venue  : {byline}{' — ' if byline and venue else ''}{venue}")
        lines.append(f"  read it here   : {record.url}")
        lines.append(f"  agreement      : {agreement}")

    if record is not None and record.abstract:
        lines.extend(["", "ABSTRACT", ""])
        lines.extend(
            textwrap.wrap(record.abstract, width=width, initial_indent="  ", subsequent_indent="  ")
        )
    elif record is not None:
        lines.extend(["", "ABSTRACT", "", "  publisher deposited no abstract; open the link above"])

    if abstract_only:
        return "\n".join(lines)

    lines.extend(["", "FULL TEXT", ""])
    if review.full_text_path is not None:
        lines.append(f"  {review.full_text_path} ({review.full_text_words:,} words)")
    else:
        lines.append("  not available locally — run the paper ingest to enable quote checking")

    if review.quote_checks:
        verified = len(review.quote_checks) - len(review.unverified_quotes)
        header = f"EVIDENCE QUOTES — {verified}/{len(review.quote_checks)} verbatim in full text"
        lines.extend(["", header, ""])
        for check in review.quote_checks:
            marker = "ok  " if check.found else "MISS"
            snippet = check.quote if len(check.quote) <= 72 else check.quote[:69] + "..."
            lines.append(f"  [{marker}] {check.component}")
            lines.append(f"         “{snippet}”")

    lines.extend(["", "ENCODED COMPONENTS — this is what you are signing off on", ""])
    for kind, name, parameters in review.components:
        rendered = ", ".join(f"{key}={value}" for key, value in parameters.items())
        lines.append(f"  {kind:<10} {name}{'  [' + rendered + ']' if rendered else ''}")

    if review.notes:
        lines.extend(["", "NOTES", ""])
        for note in review.notes:
            lines.extend(
                textwrap.wrap(note, width=width, initial_indent="  - ", subsequent_indent="    ")
            )

    return "\n".join(lines)
