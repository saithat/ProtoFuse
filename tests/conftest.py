import json
from pathlib import Path
from typing import Any

import pytest

from protofuse.contracts import MethodologySpec

EXAMPLE = Path(__file__).parents[1] / "examples" / "toy_methodology.json"


@pytest.fixture
def example_payload() -> dict[str, Any]:
    return json.loads(EXAMPLE.read_text())


@pytest.fixture
def example_spec(example_payload: dict[str, Any]) -> MethodologySpec:
    return MethodologySpec.model_validate(example_payload)
