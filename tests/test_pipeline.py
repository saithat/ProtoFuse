from protofuse.contracts import MethodologySpec
from protofuse.integration import DNA_BASELINE_REGISTRY
from protofuse.phillip import run_pipeline
from protofuse.scientific_agent import ScientificAgent


class FakeBackend:
    def __init__(self, spec: MethodologySpec) -> None:
        self.spec = spec

    def extract_json(self, *, system: str, prompt: str) -> str:
        assert "untrusted content" in system
        assert "<paper>" in prompt
        return self.spec.model_dump_json()


def test_pipeline_keeps_unknown_components_non_executable(example_spec: MethodologySpec) -> None:
    result = run_pipeline("synthetic paper text", ScientificAgent(FakeBackend(example_spec)))

    assert not result.plan.executable
    assert set(result.plan.unresolved) == {
        "random nucleotide generator",
        "GC content",
        "homopolymer limit",
        "MCMC",
    }


def test_pipeline_can_use_reviewed_registry(example_spec: MethodologySpec) -> None:
    registry = DNA_BASELINE_REGISTRY
    result = run_pipeline(
        "synthetic paper text",
        ScientificAgent(FakeBackend(example_spec)),
        registry=registry,
    )

    assert result.plan.executable
    assert result.plan.unresolved == []
