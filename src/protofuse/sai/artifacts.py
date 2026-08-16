"""Reviewed fusion artifact schema, hashing, loading, and discovery."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from protofuse.sai.model import LinearEnsembleModel
from protofuse.sai.registry import FusionBundle, FusionRegistry
from protofuse.sai.signatures import StepGroupSignature


class ArtifactModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FusionManifest(ArtifactModel):
    schema_version: str = "1.0"
    fusion_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    version: str = Field(min_length=1)
    reviewed: bool = False
    optimizer_index: int = Field(ge=0)
    constraint_labels: tuple[str, ...]
    group_signature: StepGroupSignature
    group_signature_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_path: str = "model.json"
    model_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    training_trace_sha256: tuple[str, ...] = ()
    split_manifest_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    final_validation_required: bool = True
    score_only: bool = True

    @field_validator("model_path")
    @classmethod
    def model_path_is_safe(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or path.suffix != ".json":
            raise ValueError("model_path must be a relative JSON file")
        return value

    @model_validator(mode="after")
    def signature_and_labels_match(self) -> FusionManifest:
        if self.group_signature.sha256 != self.group_signature_sha256:
            raise ValueError("group signature hash does not match embedded signature")
        labels = tuple(item.label for item in self.group_signature.constraints)
        if labels != self.constraint_labels:
            raise ValueError("constraint_labels do not match embedded group signature")
        if self.group_signature.optimizer_index != self.optimizer_index:
            raise ValueError("optimizer_index does not match embedded group signature")
        if not self.constraint_labels:
            raise ValueError("fusion must target at least one constraint")
        return self


@dataclass(frozen=True)
class LoadedFusionArtifact:
    root: Path
    manifest: FusionManifest
    model: LinearEnsembleModel


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_fusion_artifact(
    directory: Path,
    *,
    require_reviewed: bool = True,
) -> LoadedFusionArtifact:
    root = directory.resolve()
    manifest_path = root / "manifest.json"
    manifest = FusionManifest.model_validate_json(manifest_path.read_text())
    if require_reviewed and not manifest.reviewed:
        raise ValueError(f"fusion artifact is not reviewed: {manifest.fusion_id}")
    unresolved_model = root / manifest.model_path
    if unresolved_model.is_symlink():
        raise ValueError("fusion model cannot be a symlink")
    model_path = unresolved_model.resolve()
    if not model_path.is_relative_to(root) or not model_path.is_file():
        raise ValueError("fusion model is outside the artifact or missing")
    if file_sha256(model_path) != manifest.model_sha256:
        raise ValueError("fusion model hash mismatch")
    model = LinearEnsembleModel.model_validate_json(model_path.read_text())
    if model.output_labels != manifest.constraint_labels:
        raise ValueError("model outputs do not match fusion constraint labels")
    return LoadedFusionArtifact(root=root, manifest=manifest, model=model)


def write_unreviewed_fusion_artifact(
    directory: Path,
    *,
    manifest: FusionManifest,
    model: LinearEnsembleModel,
) -> LoadedFusionArtifact:
    """Write a generated artifact without self-certifying scientific review."""

    if manifest.reviewed:
        raise ValueError("generated artifacts must start reviewed=False")
    if model.output_labels != manifest.constraint_labels:
        raise ValueError("model outputs do not match manifest constraints")
    directory.mkdir(parents=True, exist_ok=True)
    model_path = directory / manifest.model_path
    model_text = model.model_dump_json(indent=2) + "\n"
    model_path.write_text(model_text)
    actual_hash = file_sha256(model_path)
    if actual_hash != manifest.model_sha256:
        manifest = manifest.model_copy(update={"model_sha256": actual_hash})
    (directory / "manifest.json").write_text(manifest.model_dump_json(indent=2) + "\n")
    return load_fusion_artifact(directory, require_reviewed=False)


def bundle_from_artifact(artifact: LoadedFusionArtifact) -> FusionBundle[object]:
    from protofuse.sai.transform import build_artifact_bundle

    return build_artifact_bundle(artifact)


def discover_fusion_bundles(
    root: Path,
    *,
    require_reviewed: bool = True,
) -> tuple[FusionBundle[object], ...]:
    if not root.is_dir():
        return ()
    bundles: list[FusionBundle[object]] = []
    for manifest_path in sorted(root.glob("*/manifest.json")):
        artifact = load_fusion_artifact(
            manifest_path.parent,
            require_reviewed=require_reviewed,
        )
        bundles.append(bundle_from_artifact(artifact))
    return tuple(bundles)


def register_discovered_fusions(
    root: Path,
    registry: FusionRegistry[object],
) -> tuple[str, ...]:
    registered: list[str] = []
    for bundle in discover_fusion_bundles(root, require_reviewed=True):
        registry.register(bundle)
        registered.append(bundle.qualified_id)
    return tuple(registered)


def json_sha256(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(encoded.encode()).hexdigest()
