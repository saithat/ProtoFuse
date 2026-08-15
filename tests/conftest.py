from typing import Any

import pytest

from protofuse.contracts import MethodologySpec


@pytest.fixture
def example_payload() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "paper": {"title": "Contract test methodology"},
        "generators": [
            {
                "name": "generator",
                "description": "Generate candidates.",
                "output": "dna",
            }
        ],
        "constraints": [
            {
                "name": "score_a",
                "description": "Score objective A.",
                "metric": "a",
                "direction": "maximize",
            },
            {
                "name": "score_b",
                "description": "Score objective B.",
                "metric": "b",
                "direction": "minimize",
            },
        ],
        "optimizers": [
            {
                "name": "optimizer",
                "description": "Refine candidates.",
                "strategy": "iterative",
            }
        ],
        "workflow": {
            "steps": [
                {"id": "generate", "operation": "generate"},
                {"id": "score", "operation": "score"},
            ],
            "edges": [{"source": "generate", "target": "score", "artifact": "candidate"}],
        },
        "selection_thresholds": [
            {
                "name": "a threshold",
                "metric": "a",
                "operator": ">=",
                "value": 0.5,
                "applies_to": "candidate",
            },
            {
                "name": "b threshold",
                "metric": "b",
                "operator": "<=",
                "value": 1.0,
                "applies_to": "candidate",
            },
        ],
    }


@pytest.fixture
def example_spec(example_payload: dict[str, Any]) -> MethodologySpec:
    return MethodologySpec.model_validate(example_payload)
