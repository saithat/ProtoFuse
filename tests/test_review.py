from protofuse.phillip.review import review_fixture

EXPECTED_CHECKS = {
    "fixture_spec",
    "paper_identity",
    "paper_source",
    "evidence_coverage",
    "disclosure",
    "workload_profile",
    "plan_bindings",
    "source_drift",
    "source_safety",
    "manifest",
    "manifest_metadata",
    "structure_binding",
    "preflight",
}


def test_review_passes_for_committed_dna_collection() -> None:
    report = review_fixture("dnachisel-num1", run_preflight_check=False)

    assert report.ok, report.summary()
    assert {check.name for check in report.checks} == EXPECTED_CHECKS


def test_review_detects_source_drift_and_hash_checks() -> None:
    report = review_fixture("custom-egfp-lung", run_preflight_check=False)
    by_name = {check.name: check for check in report.checks}

    assert by_name["source_drift"].status == "pass"
    assert by_name["source_safety"].status == "pass"
    assert by_name["manifest"].status == "pass"


def test_review_fails_when_collection_is_missing() -> None:
    report = review_fixture(
        "dnachisel-num1",
        collection_id="collection-that-does-not-exist",
        run_preflight_check=False,
    )

    assert not report.ok
    assert [check.name for check in report.failed] == ["collection"]


def test_review_flags_fixtures_without_paper_evidence() -> None:
    report = review_fixture("esm2-protein-maturation", run_preflight_check=False)
    by_name = {check.name: check for check in report.checks}

    assert by_name["evidence_coverage"].status == "fail"
    assert by_name["paper_identity"].status == "warn"
    assert by_name["structure_binding"].status == "skip"


def test_review_validates_pdb_structure_for_binder_fixtures() -> None:
    report = review_fixture("freebindcraft-binder", run_preflight_check=False)
    by_name = {check.name: check for check in report.checks}

    assert by_name["structure_binding"].status == "pass"
    assert "4RWS" in by_name["structure_binding"].detail
    assert "94,259,284" in by_name["structure_binding"].detail or "'94,259,284'" in (
        by_name["structure_binding"].detail
    )


def test_review_skips_structure_binding_without_target_pdb() -> None:
    report = review_fixture("dnachisel-num1", run_preflight_check=False)
    by_name = {check.name: check for check in report.checks}

    assert by_name["structure_binding"].status == "skip"
