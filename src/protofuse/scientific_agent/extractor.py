"""Backend-neutral extraction orchestration."""

from __future__ import annotations

from typing import Protocol

from protofuse.contracts import MethodologySpec
from protofuse.scientific_agent.prompt import SYSTEM_PROMPT, extraction_prompt


class ExtractionBackend(Protocol):
    """Provider adapter implemented by Anthropic or a deterministic test double."""

    def extract_json(self, *, system: str, prompt: str) -> str: ...


class ScientificAgent:
    def __init__(self, backend: ExtractionBackend) -> None:
        self._backend = backend

    def extract(self, paper_text: str) -> MethodologySpec:
        if not paper_text.strip():
            raise ValueError("paper text is empty")
        payload = self._backend.extract_json(
            system=SYSTEM_PROMPT,
            prompt=extraction_prompt(paper_text),
        )
        return MethodologySpec.model_validate_json(payload)
