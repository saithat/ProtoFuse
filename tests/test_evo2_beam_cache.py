from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from proto_language.core import Constraint, ConstraintOutput, Construct, Segment, Sequence
from proto_language.generator import Evo2Generator, Evo2GeneratorConfig
from proto_language.optimizer import BeamSearchOptimizerConfig
from proto_tools import Evo2KVCacheRef, ToolRegistry
from proto_tools.tools.causal_models.evo2.evo2_sample import Evo2Sample, Evo2SampleOutput

from protofuse.phillip import evo2_beam_cache
from protofuse.phillip.evo2_beam_cache import Evo2PrefixReplayBeamSearchOptimizer


def _score_sequences(input_sequences: Any, config: Any = None) -> list[ConstraintOutput]:
    del config
    return [
        ConstraintOutput(
            score=sequences[0].sequence.count("T") / len(sequences[0].sequence)
        )
        for sequences in input_sequences
    ]


_score_sequences._constraint_supported_sequence_types = ["dna"]  # type: ignore[attr-defined]
_score_sequences._constraint_num_input_sequences_per_tuple = 1  # type: ignore[attr-defined]


def _optimizer() -> tuple[Evo2PrefixReplayBeamSearchOptimizer, Evo2Generator, Segment]:
    target = Segment(length=4, sequence_type="dna")
    generator = Evo2Generator(
        Evo2GeneratorConfig(
            prompts=["ACGT"],
            batch_size=1,
            force_prompt_threshold=3000,
            prepend_prompt=False,
            store_kv_cache=False,
        )
    )
    generator.assign(target)
    optimizer = Evo2PrefixReplayBeamSearchOptimizer(
        target_segment=target,
        constructs=[Construct([target])],
        generators=[generator],
        constraints=[
            Constraint(inputs=[target], function=_score_sequences, function_config={})
        ],
        config=BeamSearchOptimizerConfig(
            prompt="ACGT",
            beam_length=2,
            num_results=1,
            proposals_per_result=6,
            prepend_prompt=False,
            score_by="last",
            seed=7,
            use_kv_caching=True,
        ),
    )
    return optimizer, generator, target


def _fake_sampler(
    calls: list[tuple[Any, Any]],
    *,
    replay_sequence: Callable[[str], str] | None = None,
) -> Callable[..., Evo2SampleOutput]:
    cache_index = 0

    def sample(inputs: Any, config: Any) -> Evo2SampleOutput:
        nonlocal cache_index
        calls.append((inputs, config))
        base = "ACGT"[int(config.seed) % 4]
        sequence = base * config.max_new_tokens
        if (
            replay_sequence is not None
            and config.return_kv_cache
            and config.old_kv_cache is not None
        ):
            sequence = replay_sequence(sequence)
        cache = None
        if config.return_kv_cache:
            cache_index += 1
            cache = Evo2KVCacheRef(cache_id=f"cache-{cache_index}")
        return Evo2SampleOutput(results=[Evo2Sample(sequence=sequence, kv_cache=cache)])

    return sample


def test_prefix_replay_keeps_only_selected_caches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    optimizer, generator, target = _optimizer()
    calls: list[tuple[Any, Any]] = []
    released: list[str] = []
    monkeypatch.setattr(evo2_beam_cache, "run_evo2_sample", _fake_sampler(calls))
    monkeypatch.setattr(
        generator,
        "release_kv_cache",
        lambda cache: released.append(cache.cache_id),
    )

    optimizer.run()

    bootstrap = [config for _, config in calls if config.old_kv_cache is None]
    proposals = [config for _, config in calls if not config.return_kv_cache]
    replays = [
        config
        for _, config in calls
        if config.return_kv_cache and config.old_kv_cache is not None
    ]
    assert len(calls) == 15
    assert len(bootstrap) == 1
    assert bootstrap[0].max_new_tokens == 1
    assert bootstrap[0].force_prompt_threshold == 3000
    assert bootstrap[0].max_seqlen == 8
    assert all(config.max_seqlen == 8 for _, config in calls)
    assert len(proposals) == 12
    assert len(replays) == 2
    assert all(config.old_kv_cache is not None for config in proposals)
    assert len(set(released)) == 3
    assert generator.store_kv_cache is False
    assert len(target.result_sequences) == 1
    assert {len(sequence.sequence) for sequence in target.proposal_sequences} == {4}
    assert all(beam.kv_cache is None for beam in optimizer.beams)


def test_prefix_replay_fails_closed_on_sequence_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    optimizer, generator, _ = _optimizer()
    calls: list[tuple[Any, Any]] = []
    released: list[str] = []
    monkeypatch.setattr(
        evo2_beam_cache,
        "run_evo2_sample",
        _fake_sampler(
            calls,
            replay_sequence=lambda sequence: (
                ("A" if sequence[0] != "A" else "C") + sequence[1:]
            ),
        ),
    )
    monkeypatch.setattr(
        generator,
        "release_kv_cache",
        lambda cache: released.append(cache.cache_id),
    )

    with pytest.raises(RuntimeError, match="not byte-identical"):
        optimizer.run()

    # The mismatched replay cache and the still-current prefix cache are released.
    assert len(set(released)) == 2
    assert all(beam.kv_cache is None for beam in optimizer.beams)


def test_scoring_rejects_a_target_without_the_frozen_prompt() -> None:
    optimizer, _, target = _optimizer()
    target.proposal_sequences = [Sequence(sequence="TT", sequence_type="dna")]

    with pytest.raises(RuntimeError, match="does not begin with the frozen prompt"):
        optimizer.score_energy()


def test_cuda_generator_releases_remotely_when_dispatch_backend_is_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from proto_tools.modal import client as modal_client

    optimizer, generator, _ = _optimizer()
    remote_calls: list[dict[str, Any]] = []

    class FakeRemoteMethod:
        def remote(self, **kwargs: Any) -> None:
            remote_calls.append(kwargs)

    assert generator.device == "cuda"
    monkeypatch.setattr(
        ToolRegistry,
        "dispatch_backend_configured",
        classmethod(lambda _cls: True),
    )
    monkeypatch.setattr(modal_client, "_bound_method", lambda *_args, **_kwargs: FakeRemoteMethod())
    monkeypatch.setattr(
        generator,
        "release_kv_cache",
        lambda _cache: pytest.fail("remote cache was released through the local worker"),
    )

    optimizer._release_cache_handle(Evo2KVCacheRef(cache_id="remote-cache"))

    assert remote_calls == [
        {"kv_caches": [{"type": "evo2_kv_cache", "cache_id": "remote-cache"}]}
    ]
