from __future__ import annotations

from typing import Any

from protofuse.phillip.standalone.pair_scaled_boltz2_inference import (
    _scaled_pairformer_inputs,
)


class _Scalable:
    def __init__(self, value: float) -> None:
        self.value = value

    def __mul__(self, factor: float) -> _Scalable:
        return _Scalable(self.value * factor)


def test_pairformer_hook_scales_only_positional_z() -> None:
    audit: dict[str, Any] = {"invocations": 0}
    args, kwargs = _scaled_pairformer_inputs(
        ("sequence", _Scalable(4.0)),
        {"mask": "unchanged"},
        beta=-0.25,
        audit=audit,
    )

    assert args[0] == "sequence"
    assert isinstance(args[1], _Scalable)
    assert args[1].value == 3.0
    assert kwargs == {"mask": "unchanged"}
    assert audit["invocations"] == 1


def test_pairformer_hook_scales_keyword_z() -> None:
    audit: dict[str, Any] = {"invocations": 0}
    args, kwargs = _scaled_pairformer_inputs(
        (),
        {"s": "sequence", "z": _Scalable(2.0)},
        beta=0.5,
        audit=audit,
    )

    assert args == ()
    assert kwargs["s"] == "sequence"
    assert isinstance(kwargs["z"], _Scalable)
    assert kwargs["z"].value == 3.0
    assert audit["invocations"] == 1
