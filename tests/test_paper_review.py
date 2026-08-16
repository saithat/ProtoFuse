from pathlib import Path

import pytest

from protofuse.phillip import paper_review as paper_review_module
from protofuse.phillip.paper_ingest import PaperSearchError
from protofuse.phillip.paper_review import (
    build_paper_review,
    compare_titles,
    format_review,
    verify_quotes,
    verify_quotes_remote,
)
from protofuse.phillip.program_builders import load_fixture_spec


def _fake_grep(document: dict[int, str]):
    """Stand in for `paperclip grep`: case-insensitive literal match over known lines."""

    def grep(document_path: str, pattern: str, **kwargs: object) -> list[tuple[int, str]]:
        needle = pattern.lower()
        return [
            (number, text)
            for number, text in sorted(document.items())
            if needle in text.lower()
        ]

    return grep


def _constraint_quotes() -> list[str]:
    spec = load_fixture_spec("dnachisel-num1")
    return [evidence.quote for item in spec.constraints for evidence in item.evidence]


def _all_quotes() -> list[str]:
    spec = load_fixture_spec("dnachisel-num1")
    return [
        evidence.quote
        for group in (spec.generators, spec.constraints, spec.optimizers)
        for item in group
        for evidence in item.evidence
    ]


def test_compare_titles_distinguishes_match_from_mismatch() -> None:
    assert (
        compare_titles(
            "DNA Chisel, a versatile sequence optimizer",
            "DNA chisel: A VERSATILE sequence optimizer",
        )
        == "match"
    )
    assert (
        compare_titles(
            "Codon optimization for lung tissue",
            "De novo design of miniproteins",
        )
        == "mismatch"
    )
    assert compare_titles("", "anything") == "unknown"


def test_verify_quotes_accepts_whitespace_and_ellipsis_variation() -> None:
    spec = load_fixture_spec("dnachisel-num1")
    paper_text = " ".join(
        evidence.quote for item in spec.constraints for evidence in item.evidence
    )

    checks = verify_quotes(spec, paper_text)

    constraint_checks = [check for check in checks if check.component.startswith("constraint")]
    assert constraint_checks
    assert all(check.found for check in constraint_checks)


def test_verify_quotes_flags_absent_text() -> None:
    spec = load_fixture_spec("dnachisel-num1")

    checks = verify_quotes(spec, "an unrelated document about something else entirely")

    assert checks
    assert not any(check.found for check in checks)


def test_review_uses_explicit_text_override(tmp_path: Path) -> None:
    spec = load_fixture_spec("dnachisel-num1")
    quotes = [evidence.quote for item in spec.constraints for evidence in item.evidence]
    source = tmp_path / "methods.txt"
    source.write_text(" ".join(quotes))

    review = build_paper_review("dnachisel-num1", offline=True, text_path=source)

    assert review.lookup_status == "offline"
    assert review.full_text_words > 0
    assert not any(
        check.component.startswith("constraint") and not check.found
        for check in review.quote_checks
    )


def test_review_reports_non_doi_identifier_offline() -> None:
    review = build_paper_review("esm2-protein-maturation", offline=True)

    assert review.lookup_status == "not_a_doi"
    assert any("not a DOI" in note for note in review.notes)


def test_format_review_renders_without_network() -> None:
    review = build_paper_review("dnachisel-num1", offline=True)

    rendered = format_review(review)

    assert "PAPER REVIEW — dnachisel-num1" in rendered
    assert "ENCODED COMPONENTS" in rendered


def test_verify_quotes_remote_reports_matching_line_numbers() -> None:
    spec = load_fixture_spec("dnachisel-num1")
    document = {10 * (index + 1): quote for index, quote in enumerate(_constraint_quotes())}

    checks = verify_quotes_remote(spec, "/papers/PMC1", grep=_fake_grep(document))

    constraint_checks = [check for check in checks if check.component.startswith("constraint")]
    assert constraint_checks
    assert all(check.found for check in constraint_checks)
    assert all(check.lines for check in constraint_checks)
    assert set(checks[0].lines) <= set(document)


def test_verify_quotes_remote_rejects_partial_anchor_match() -> None:
    """An anchor hit must not pass a quote whose remaining words are absent."""

    spec = load_fixture_spec("dnachisel-num1")
    quote = _constraint_quotes()[0]
    opening = " ".join(quote.split()[:3])
    document = {7: f"{opening} and then something completely unrelated"}

    checks = verify_quotes_remote(spec, "/papers/PMC1", grep=_fake_grep(document))

    assert not any(check.found for check in checks)


def test_review_falls_back_to_paperclip_without_local_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = {42: " ".join(_constraint_quotes())}
    monkeypatch.setattr(paper_review_module, "fetch_paper_record", lambda *a, **k: None)
    monkeypatch.setattr(paper_review_module, "paperclip_document_path", lambda doi: "/papers/PMC1")
    monkeypatch.setattr(paper_review_module, "paperclip_grep", _fake_grep(document))

    review = build_paper_review("dnachisel-num1", text_path=tmp_path / "absent.txt")

    assert review.quote_source == "paperclip:/papers/PMC1"
    assert review.full_text_path is None
    assert any(check.found for check in review.quote_checks)
    rendered = format_review(review)
    assert "searched in Paperclip at /papers/PMC1" in rendered
    assert "verbatim in Paperclip full text" in rendered
    assert "L42" in rendered


def test_review_reports_search_failure_as_unverified_not_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A backend outage must never be rendered as quotes missing from the paper."""

    def failing_grep(document_path: str, pattern: str, **kwargs: object) -> list[tuple[int, str]]:
        raise PaperSearchError("Slab service unavailable for PMC1")

    monkeypatch.setattr(paper_review_module, "fetch_paper_record", lambda *a, **k: None)
    monkeypatch.setattr(paper_review_module, "paperclip_document_path", lambda doi: "/papers/PMC1")
    monkeypatch.setattr(paper_review_module, "paperclip_grep", failing_grep)

    review = build_paper_review("dnachisel-num1", text_path=tmp_path / "absent.txt")

    assert review.quote_checks
    assert review.errored_quotes == review.quote_checks
    assert review.missing_quotes == []
    assert any("unverified rather than absent" in note for note in review.notes)
    rendered = format_review(review)
    assert "MISS" not in rendered
    assert "unverified (search failed)" in rendered


def test_verify_quotes_remote_keeps_confirmed_quotes_when_later_searches_fail() -> None:
    """One flaky search must not discard quotes already confirmed present."""

    spec = load_fixture_spec("dnachisel-num1")
    document = {5: " ".join(_all_quotes())}
    working = _fake_grep(document)
    calls = {"count": 0}

    def flaky_grep(document_path: str, pattern: str, **kwargs: object) -> list[tuple[int, str]]:
        calls["count"] += 1
        if calls["count"] > 1:
            raise PaperSearchError("Slab service unavailable for PMC1")
        return working(document_path, pattern)

    checks = verify_quotes_remote(spec, "/papers/PMC1", grep=flaky_grep)

    assert any(check.found for check in checks)
    assert any(check.error for check in checks)
    assert all(check.error is None for check in checks if check.found)


def test_review_advises_authentication_when_paperclip_has_no_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(paper_review_module, "fetch_paper_record", lambda *a, **k: None)
    monkeypatch.setattr(paper_review_module, "paperclip_document_path", lambda doi: None)

    review = build_paper_review("dnachisel-num1", text_path=tmp_path / "absent.txt")

    assert review.quote_checks == []
    assert any("PAPERCLIP_API_KEY" in note for note in review.notes)
