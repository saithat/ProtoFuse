"""Anthropic adapter for the shared scientific agent."""

from __future__ import annotations

import os

from anthropic import Anthropic
from dotenv import load_dotenv


class AnthropicBackend:
    def __init__(self, model: str | None = None) -> None:
        load_dotenv()
        self._client = Anthropic()
        self._model = model or os.environ.get("PROTOFUSE_ANTHROPIC_MODEL", "claude-sonnet-4-6")

    def extract_json(self, *, system: str, prompt: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=8192,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        text_blocks = [block.text for block in response.content if block.type == "text"]
        if not text_blocks:
            raise RuntimeError("Anthropic returned no text content")
        return "".join(text_blocks)
