"""Execution-local state shared by ordinary and fused program runners."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

ProgramExecutionCache = dict[object, object]

_ACTIVE_PROGRAM_EXECUTION_CACHE: ContextVar[ProgramExecutionCache | None] = ContextVar(
    "protofuse_program_execution_cache",
    default=None,
)


@contextmanager
def program_execution_scope() -> Iterator[None]:
    """Create fresh cache storage whose lifetime is exactly one ``Program.run`` call."""

    token = _ACTIVE_PROGRAM_EXECUTION_CACHE.set({})
    try:
        yield
    finally:
        _ACTIVE_PROGRAM_EXECUTION_CACHE.reset(token)


def active_program_execution_cache() -> ProgramExecutionCache | None:
    """Return the current run's private cache, if execution is managed by ProtoFuse."""

    return _ACTIVE_PROGRAM_EXECUTION_CACHE.get()
