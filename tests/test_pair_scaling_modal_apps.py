from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOLTZ_APP = ROOT / "scripts" / "pair_scaling_modal_app.py"
AF3_APP = ROOT / "scripts" / "pair_scaling_af3_modal_app.py"
AF3_BACKEND = ROOT / "src" / "protofuse" / "phillip" / "pair_scaling_alphafold3.py"


def _module(path: Path) -> ast.Module:
    return ast.parse(path.read_text(), filename=str(path))


def _string_assignment(path: Path, name: str) -> str:
    for node in _module(path).body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id == name:
            value = ast.literal_eval(node.value)
            assert isinstance(value, str)
            return value
    raise AssertionError(f"{name} was not assigned in {path}")


def _class_names(path: Path) -> set[str]:
    return {
        node.name
        for node in _module(path).body
        if isinstance(node, ast.ClassDef)
    }


def test_required_boltz_app_does_not_build_optional_alphafold3() -> None:
    source = BOLTZ_APP.read_text().lower()

    assert "alphafold" not in source
    assert "af3_" not in source
    assert _class_names(BOLTZ_APP) == {"PairScalingBoltz2Service"}


def test_alphafold3_backend_resolves_the_separate_optional_app() -> None:
    assert _string_assignment(AF3_APP, "APP_NAME") == "protofuse-pair-scaling-af3"
    assert _string_assignment(AF3_BACKEND, "PAIR_SCALING_MODAL_APP") == (
        "protofuse-pair-scaling-af3"
    )
    assert _class_names(AF3_APP) == {"PairScalingAlphaFold3Service"}
