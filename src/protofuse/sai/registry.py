"""Registry of learned fusions that can recognize and transform Proto programs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class FusionBundle[ProgramT]:
    fusion_id: str
    version: str
    matches: Callable[[ProgramT], bool]
    apply: Callable[[ProgramT], ProgramT]

    @property
    def qualified_id(self) -> str:
        return f"{self.fusion_id}@{self.version}"


class FusionRegistry[ProgramT]:
    def __init__(self) -> None:
        self._bundles: list[FusionBundle[ProgramT]] = []

    @property
    def bundles(self) -> tuple[FusionBundle[ProgramT], ...]:
        return tuple(self._bundles)

    def register(self, bundle: FusionBundle[ProgramT]) -> None:
        if any(existing.qualified_id == bundle.qualified_id for existing in self._bundles):
            raise ValueError(f"fusion is already registered: {bundle.qualified_id}")
        self._bundles.append(bundle)
