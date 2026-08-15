import json
from pathlib import Path

import pytest

from protofuse.contracts import IntegrationCatalog, IntegrationScenarioManifest
from protofuse.integration.scenarios import validate_integrations


def test_integration_catalog_loads() -> None:
    catalog = IntegrationCatalog.model_validate_json(
        Path("philip-sai-integrations/v1/catalog.json").read_text()
    )
    assert catalog.integration_version == "1"
    assert catalog.scenarios == []


def test_integration_template_manifest_loads() -> None:
    manifest = IntegrationScenarioManifest.model_validate_json(
        Path("philip-sai-integrations/v1/sai/_template/manifest.json").read_text()
    )
    assert manifest.source_lane.value == "sai"
    assert manifest.contributors[0].id == "sai"


def test_validate_empty_integrations_catalog() -> None:
    messages = validate_integrations(version="1")
    assert any("catalog is empty" in message for message in messages)


def test_validate_integrations_rejects_catalog_manifest_mismatch(tmp_path: Path) -> None:
    version_dir = tmp_path / "philip-sai-integrations" / "v1"
    scenario_dir = version_dir / "sai" / "demo"
    scenario_dir.mkdir(parents=True)
    manifest = {
        "integration_version": "1",
        "scenario_id": "demo",
        "scenario_version": 1,
        "title": "Demo",
        "source_lane": "sai",
        "contributors": [
            {"id": "sai", "role": "sai", "contributions": ["authored methodology.json"]}
        ],
        "methodology_path": "methodology.json",
        "status": "draft",
    }
    (scenario_dir / "manifest.json").write_text(json.dumps(manifest))
    (version_dir / "catalog.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "integration_version": "1",
                "scenarios": [
                    {
                        "scenario_id": "other",
                        "source_lane": "sai",
                        "path": "sai/demo",
                        "scenario_version": 1,
                        "status": "draft",
                        "contributor_ids": ["sai"],
                    }
                ],
            }
        )
    )

    original_root = Path(__file__).resolve().parents[1]
    import protofuse.integration.scenarios as scenarios

    scenarios.INTEGRATIONS_ROOT = tmp_path / "philip-sai-integrations"
    try:
        with pytest.raises(ValueError, match="scenario_id"):
            validate_integrations(version="1")
    finally:
        scenarios.INTEGRATIONS_ROOT = original_root / "philip-sai-integrations"
