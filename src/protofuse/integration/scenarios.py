"""Load and validate versioned integration scenarios."""

from __future__ import annotations

from pathlib import Path

from protofuse.contracts import IntegrationCatalog, IntegrationScenarioManifest, MethodologySpec

REPO_ROOT = Path(__file__).resolve().parents[3]
INTEGRATIONS_ROOT = REPO_ROOT / "philip-sai-integrations"


def integrations_version_dir(version: str = "1") -> Path:
    return INTEGRATIONS_ROOT / f"v{version}"


def load_catalog(version: str = "1") -> IntegrationCatalog:
    catalog_path = integrations_version_dir(version) / "catalog.json"
    return IntegrationCatalog.model_validate_json(catalog_path.read_text())


def load_scenario_manifest(scenario_dir: Path) -> IntegrationScenarioManifest:
    manifest_path = scenario_dir / "manifest.json"
    return IntegrationScenarioManifest.model_validate_json(manifest_path.read_text())


def load_scenario_methodology(
    scenario_dir: Path,
    manifest: IntegrationScenarioManifest,
) -> MethodologySpec:
    methodology_path = scenario_dir / manifest.methodology_path
    return MethodologySpec.model_validate_json(methodology_path.read_text())


def validate_integrations(version: str = "1") -> list[str]:
    """Validate the catalog and every indexed scenario. Returns human-readable messages."""

    version_dir = integrations_version_dir(version)
    if not version_dir.is_dir():
        raise FileNotFoundError(f"missing integrations directory: {version_dir}")

    catalog = load_catalog(version)
    if catalog.integration_version != version:
        raise ValueError(
            f"catalog integration_version {catalog.integration_version!r} "
            f"does not match requested v{version}"
        )

    messages: list[str] = []
    seen_ids: set[str] = set()
    for entry in catalog.scenarios:
        if entry.scenario_id in seen_ids:
            raise ValueError(f"duplicate scenario_id in catalog: {entry.scenario_id}")
        seen_ids.add(entry.scenario_id)

        scenario_dir = version_dir / entry.path
        manifest = load_scenario_manifest(scenario_dir)
        if manifest.scenario_id != entry.scenario_id:
            raise ValueError(
                f"{entry.path}: manifest scenario_id {manifest.scenario_id!r} "
                f"does not match catalog {entry.scenario_id!r}"
            )
        if manifest.source_lane != entry.source_lane:
            raise ValueError(
                f"{entry.path}: manifest source_lane {manifest.source_lane!r} "
                f"does not match catalog {entry.source_lane!r}"
            )
        if manifest.scenario_version != entry.scenario_version:
            raise ValueError(
                f"{entry.path}: manifest scenario_version {manifest.scenario_version} "
                f"does not match catalog {entry.scenario_version}"
            )
        if manifest.status != entry.status:
            raise ValueError(
                f"{entry.path}: manifest status {manifest.status!r} "
                f"does not match catalog {entry.status!r}"
            )

        contributor_ids = {contributor.id for contributor in manifest.contributors}
        if set(entry.contributor_ids) != contributor_ids:
            raise ValueError(
                f"{entry.path}: catalog contributor_ids {entry.contributor_ids} "
                f"do not match manifest contributors {sorted(contributor_ids)}"
            )

        methodology = load_scenario_methodology(scenario_dir, manifest)
        messages.append(
            f"ok {entry.source_lane.value}/{entry.scenario_id}@v{entry.scenario_version}: "
            f"{methodology.paper.title}"
        )

    if not catalog.scenarios:
        messages.append(
            f"ok philip-sai-integrations/v{version}: catalog is empty (lanes ready for scenarios)"
        )

    return messages
