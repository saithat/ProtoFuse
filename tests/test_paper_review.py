from pathlib import Path

from protofuse.phillip.paper_review import (
    build_paper_review,
    compare_titles,
    format_review,
    verify_quotes,
)
from protofuse.phillip.program_builders import load_fixture_spec


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
