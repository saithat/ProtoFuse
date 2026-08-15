from pathlib import Path

import pytest

from protofuse.contracts import IntegrationCatalog, MethodologySpec
from protofuse.integration import DNA_BASELINE_REGISTRY, DNA_CHISEL_REGISTRY, validate_integrations
from protofuse.integration.scenarios import load_scenario_manifest, load_scenario_methodology
from protofuse.phillip import build_handoff_bundle, run_pipeline, write_handoff_bundle
from protofuse.sai import (
    load_handoff_bundle,
    propose_protocstage_optimization,
    recommend_topologies,
    write_optimization_proposal,
)
from protofuse.scientific_agent import ScientificAgent

REPO_ROOT = Path(__file__).resolve().parents[1]
HANDOFF_ROOT = REPO_ROOT / "philip-sai-workflow-dump"
DECISION_ID = "dnachisel-v1"


class FakeBackend:
    def __init__(self, spec: MethodologySpec) -> None:
        self.spec = spec

    def extract_json(self, *, system: str, prompt: str) -> str:
        assert "untrusted content" in system
        assert "<paper>" in prompt
        return self.spec.model_dump_json()


def test_integration_catalog_lists_two_scenarios() -> None:
    catalog = IntegrationCatalog.model_validate_json(
        (REPO_ROOT / "philip-sai-integrations/v1/catalog.json").read_text()
    )
    scenario_ids = {entry.scenario_id for entry in catalog.scenarios}
    assert scenario_ids == {"balanced-gc", "dnachisel-gc-optimization"}


def test_validate_integrations_catalog() -> None:
    messages = validate_integrations(version="1")
    assert len(messages) == 2
    assert all(message.startswith("ok sai/") for message in messages)


def test_pipeline_1_balanced_gc_is_executable() -> None:
    scenario_dir = REPO_ROOT / "philip-sai-integrations/v1/sai/balanced-gc"
    manifest = load_scenario_manifest(scenario_dir)
    spec = load_scenario_methodology(scenario_dir, manifest)
    result = run_pipeline(
        "synthetic paper text",
        ScientificAgent(FakeBackend(spec)),
        registry=DNA_BASELINE_REGISTRY,
    )
    assert result.plan.executable
    assert result.recommendations[0].topology.value in {
        "iterative_refinement",
        "multiobjective_search",
        "staged_filter",
    }


def test_pipeline_2_dnachisel_is_executable() -> None:
    scenario_dir = REPO_ROOT / "philip-sai-integrations/v1/sai/dnachisel-gc-optimization"
    manifest = load_scenario_manifest(scenario_dir)
    spec = load_scenario_methodology(scenario_dir, manifest)
    result = run_pipeline(
        Path("data/papers/dnachisel.txt").read_text(),
        ScientificAgent(FakeBackend(spec)),
        registry=DNA_CHISEL_REGISTRY,
    )
    assert result.plan.executable
    assert manifest.handoff_decision_id == DECISION_ID
    recommendations = recommend_topologies(spec)
    assert recommendations[0].topology.value in {
        "iterative_refinement",
        "staged_filter",
        "multiobjective_search",
    }


def test_extracted_spec_matches_committed_methodology() -> None:
    spec_path = REPO_ROOT / "data/specs/dnachisel.json"
    scenario_path = (
        REPO_ROOT
        / "philip-sai-integrations/v1/sai/dnachisel-gc-optimization/methodology.json"
    )
    assert spec_path.exists()
    spec_from_data = MethodologySpec.model_validate_json(spec_path.read_text())
    spec_from_scenario = MethodologySpec.model_validate_json(scenario_path.read_text())
    assert spec_from_data == spec_from_scenario


def test_paper_text_is_available_for_ingest() -> None:
    paper_path = REPO_ROOT / "data/papers/dnachisel.txt"
    text = paper_path.read_text()
    assert "DNA Chisel" in text
    assert "BsaI restriction sites will be removed" in text


def test_phillip_handoff_bundle_for_pipeline_2() -> None:
    scenario_dir = REPO_ROOT / "philip-sai-integrations/v1/sai/dnachisel-gc-optimization"
    manifest = load_scenario_manifest(scenario_dir)
    spec = load_scenario_methodology(scenario_dir, manifest)
    result = run_pipeline(
        "paper text",
        ScientificAgent(FakeBackend(spec)),
        registry=DNA_CHISEL_REGISTRY,
    )
    bundle = build_handoff_bundle(
        spec,
        result.plan,
        scenario_id=manifest.scenario_id,
        decision_id=DECISION_ID,
    )
    assert bundle.graph["scenario_id"] == "dnachisel-gc-optimization"
    assert bundle.profile["headline_bottleneck_node_id"].startswith("cst:")
    assert (HANDOFF_ROOT / "phillip_to_sai" / DECISION_ID / "graph.json").exists()


def test_sai_optimization_proposal_for_pipeline_2() -> None:
    bundle = load_handoff_bundle(HANDOFF_ROOT, DECISION_ID)
    proposal = propose_protocstage_optimization(bundle, decision_id=DECISION_ID)
    assert proposal.prepared_module_plan["target_node_id"].startswith("cst:")
    assert proposal.graph_patch["changes"][0]["operation"] == "insert_prepared_module"
    assert (HANDOFF_ROOT / "sai_to_phillip" / DECISION_ID / "graph_patch.json").exists()


@pytest.fixture(scope="session", autouse=True)
def ensure_handoff_artifacts() -> None:
    scenario_dir = REPO_ROOT / "philip-sai-integrations/v1/sai/dnachisel-gc-optimization"
    manifest = load_scenario_manifest(scenario_dir)
    spec = load_scenario_methodology(scenario_dir, manifest)
    result = run_pipeline(
        "paper text",
        ScientificAgent(FakeBackend(spec)),
        registry=DNA_CHISEL_REGISTRY,
    )
    write_handoff_bundle(
        build_handoff_bundle(
            spec,
            result.plan,
            scenario_id=manifest.scenario_id,
            decision_id=DECISION_ID,
        ),
        HANDOFF_ROOT,
    )
    bundle = load_handoff_bundle(HANDOFF_ROOT, DECISION_ID)
    write_optimization_proposal(
        propose_protocstage_optimization(bundle, decision_id=DECISION_ID),
        HANDOFF_ROOT,
    )
