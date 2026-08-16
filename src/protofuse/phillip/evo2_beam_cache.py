"""Bounded Evo2 cache lifecycle for long-context paper beam search."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, cast

from proto_language.core import Sequence
from proto_language.generator import Evo2Generator
from proto_language.optimizer import BeamSearchOptimizer, BeamState
from proto_tools import (
    Evo2KVCacheRef,
    Evo2SampleConfig,
    Evo2SampleInput,
    ToolRegistry,
    run_evo2_sample,
)


@dataclass(frozen=True)
class _ReplayPlan:
    """Enough information to recreate one selected branch cache exactly."""

    parent_cache: Evo2KVCacheRef
    prompt: str
    max_new_tokens: int
    seed: int
    expected_sequence: str


class Evo2PrefixReplayBeamSearchOptimizer(BeamSearchOptimizer):
    """Reuse retained prefixes without keeping every proposal cache alive.

    Vortex returns a cache representing all input tokens except the newly sampled
    final token.  We bootstrap the paper prompt once from ``prompt[:-1]`` and use
    that cache to branch.  Proposal caches are ephemeral; after scoring, only the
    selected branches are replayed with their original seeds and retained.  A
    replay mismatch aborts rather than associating a sequence with the wrong
    model state.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if not isinstance(self.generator, Evo2Generator):
            raise TypeError("Evo2PrefixReplayBeamSearchOptimizer requires Evo2Generator")
        if not self.use_kv_caching:
            raise ValueError("Evo2PrefixReplayBeamSearchOptimizer requires use_kv_caching=True")
        if self.generator.batch_size != 1:
            raise ValueError("Evo2 prefix replay requires generator batch_size=1")
        if self.prepend_prompt:
            raise ValueError("Evo2 prefix replay requires prepend_prompt=False")
        if len(self.prompt) < 2:
            raise ValueError("Evo2 prefix replay requires a prompt of at least two bases")

        required_max_seqlen = len(self.prompt) + self.target_segment.sequence_length
        if (
            self.generator.max_seqlen is not None
            and self.generator.max_seqlen < required_max_seqlen
        ):
            raise ValueError(
                "Evo2 max_seqlen must cover the complete prompt and design "
                f"({self.generator.max_seqlen} < {required_max_seqlen})"
            )
        self._max_seqlen = self.generator.max_seqlen or required_max_seqlen

        # The optimizer owns the bounded cache lifecycle. Ordinary proposal calls
        # must never ask the worker to retain a branch cache.
        self.generator.store_kv_cache = False
        self._released_cache_ids: set[str] = set()
        self._modal_release_method: Any | None = None

    @property
    def _evo2(self) -> Evo2Generator:
        return cast(Evo2Generator, self.generator)

    def _sample_config(
        self,
        *,
        seed: int,
        max_new_tokens: int,
        old_kv_cache: Evo2KVCacheRef | None,
        return_kv_cache: bool,
        stop_at_eos: bool | None = None,
    ) -> Evo2SampleConfig:
        generator = self._evo2
        return Evo2SampleConfig(
            prepend_prompt=False,
            model_checkpoint=generator.model_checkpoint,
            local_path=generator.local_path,
            device=generator.device,
            top_k=generator.top_k,
            top_p=generator.top_p,
            temperature=generator.temperature,
            max_new_tokens=max_new_tokens,
            cached_generation=True,
            force_prompt_threshold=generator.force_prompt_threshold,
            max_seqlen=self._max_seqlen,
            verbose=generator.verbose,
            stop_at_eos=generator.stop_at_eos if stop_at_eos is None else stop_at_eos,
            old_kv_cache=old_kv_cache,
            return_kv_cache=return_kv_cache,
            batch_size=1,
            return_logits=False,
            seed=seed,
        )

    def _sample_once(
        self,
        prompt: str,
        *,
        seed: int,
        max_new_tokens: int,
        old_kv_cache: Evo2KVCacheRef | None,
        return_kv_cache: bool,
        stop_at_eos: bool | None = None,
    ) -> tuple[str, Evo2KVCacheRef | None]:
        config = self._sample_config(
            seed=seed,
            max_new_tokens=max_new_tokens,
            old_kv_cache=old_kv_cache,
            return_kv_cache=return_kv_cache,
            stop_at_eos=stop_at_eos,
        )
        with self._cached_generation_context():
            output = run_evo2_sample(Evo2SampleInput(prompts=[prompt]), config)
        if output.errors:
            raise RuntimeError(f"Evo2 sampling failed: {'; '.join(output.errors)}")
        if len(output.results) != 1:
            raise RuntimeError(
                f"Evo2 sampling returned {len(output.results)} results; expected one"
            )
        sample = output.results[0]
        if len(sample.sequence) != max_new_tokens:
            raise RuntimeError(
                f"Evo2 sampled {len(sample.sequence)} bases; expected {max_new_tokens}"
            )
        if return_kv_cache and sample.kv_cache is None:
            raise RuntimeError("Evo2 did not return the requested KV-cache handle")
        if not return_kv_cache and sample.kv_cache is not None:
            self._release_cache_handle(sample.kv_cache)
            raise RuntimeError("Evo2 retained an unexpected proposal KV-cache handle")
        return sample.sequence, sample.kv_cache

    def _prepare_run(self) -> None:
        super()._prepare_run()
        self._released_cache_ids.clear()

        # One generated token leaves Vortex's returned state immediately before
        # that token. Sampling a discarded token from prompt[:-1] therefore gives
        # a reusable cache for prompt[:-1]; real proposals process prompt[-1]
        # before sampling their first designed base.
        _, prefix_cache = self._sample_once(
            self.prompt[:-1],
            seed=0,
            max_new_tokens=1,
            old_kv_cache=None,
            return_kv_cache=True,
            stop_at_eos=False,
        )
        if prefix_cache is None:  # narrowed above; retained for static safety
            raise RuntimeError("Evo2 prefix bootstrap returned no cache")
        for beam in self.beams:
            beam.kv_cache = prefix_cache

    def _generate_proposals_for_beam(
        self,
        beam_idx: int,
        prepend_prompt: bool = False,
        max_new_tokens: int | None = None,
    ) -> list[BeamState]:
        if prepend_prompt:
            raise RuntimeError("Evo2 prefix replay does not support prepending the prompt")
        if max_new_tokens is None:
            raise RuntimeError("Evo2 prefix replay requires an explicit generation length")

        beam = self.beams[beam_idx]
        if not isinstance(beam.kv_cache, Evo2KVCacheRef):
            raise RuntimeError("Evo2 retained beam is missing its worker-local prefix cache")

        proposals: list[BeamState] = []
        for _ in range(self._proposals_per_result):
            self.target_segment.proposal_sequences = [
                Sequence(sequence="", sequence_type=self.target_segment.sequence_type)
            ]
            self._sync_proposal_pools(self.target_segment)

            seed = self._evo2._next_seed()
            if seed is None:
                raise RuntimeError("Evo2 prefix replay requires a deterministic optimizer seed")
            generated, cache = self._sample_once(
                beam.running_sequence,
                seed=seed,
                max_new_tokens=max_new_tokens,
                old_kv_cache=beam.kv_cache,
                return_kv_cache=False,
            )
            if cache is not None:  # narrowed above; retained for static safety
                raise RuntimeError("Evo2 proposal unexpectedly returned a retained cache")
            proposals.append(
                BeamState(
                    running_sequence=beam.running_sequence + generated,
                    kv_cache=_ReplayPlan(
                        parent_cache=beam.kv_cache,
                        prompt=beam.running_sequence,
                        max_new_tokens=max_new_tokens,
                        seed=seed,
                        expected_sequence=generated,
                    ),
                    beam_scores=beam.beam_scores.copy(),
                )
            )
        return proposals

    def _materialize_selected_cache(self, plan: _ReplayPlan) -> Evo2KVCacheRef:
        generated, cache = self._sample_once(
            plan.prompt,
            seed=plan.seed,
            max_new_tokens=plan.max_new_tokens,
            old_kv_cache=plan.parent_cache,
            return_kv_cache=True,
        )
        if cache is None:  # narrowed above; retained for static safety
            raise RuntimeError("Evo2 selected-branch replay returned no cache")
        if generated != plan.expected_sequence:
            self._release_cache_handle(cache)
            raise RuntimeError(
                "Evo2 selected-branch replay was not byte-identical; refusing a mismatched cache"
            )
        return cache

    def score_energy(
        self,
        operation: Literal["add", "multiply"] = "add",
        filter_penalty: float = float("inf"),
    ) -> None:
        """Score only the designed suffix, never the conditioning prompt."""

        designed: list[Sequence] = []
        for proposal in self.target_segment.proposal_sequences:
            if not proposal.sequence.startswith(self.prompt):
                raise RuntimeError("Evo2 proposal does not begin with the frozen prompt")
            suffix = proposal.sequence[len(self.prompt) :]
            if not suffix:
                raise RuntimeError("Evo2 proposal has no designed suffix to score")
            designed.append(
                Sequence(sequence=suffix, sequence_type=self.target_segment.sequence_type)
            )
        self.target_segment.proposal_sequences = designed
        self._sync_proposal_pools(self.target_segment)
        super().score_energy(operation=operation, filter_penalty=filter_penalty)

    def _select_topk_beams(self, proposal_beams: list[BeamState]) -> None:
        if self.num_results is None:
            raise RuntimeError("Evo2 prefix replay requires a finite result count")
        scored = [(beam, self._get_aggregated_score(beam)) for beam in proposal_beams]
        selected = [
            beam
            for beam, _ in sorted(scored, key=lambda item: item[1])[: self.num_results]
        ]
        materialized: list[Evo2KVCacheRef] = []
        try:
            for beam in selected:
                if not isinstance(beam.kv_cache, _ReplayPlan):
                    raise RuntimeError("Evo2 proposal is missing its deterministic replay plan")
                cache = self._materialize_selected_cache(beam.kv_cache)
                beam.kv_cache = cache
                materialized.append(cache)
            super()._select_topk_beams(proposal_beams)
        except Exception:
            for cache in materialized:
                self._release_cache_handle(cache)
            raise

    def _release_kv_cache(self, kv_cache: Any | None) -> None:
        if kv_cache is None or isinstance(kv_cache, _ReplayPlan):
            return
        if not isinstance(kv_cache, Evo2KVCacheRef):
            raise RuntimeError(f"Unexpected Evo2 cache handle type: {type(kv_cache).__name__}")
        self._release_cache_handle(kv_cache)

    def _release_cache_handle(self, cache: Evo2KVCacheRef) -> None:
        if cache.cache_id in self._released_cache_ids:
            return
        # Program.run(device="modal") installs an early dispatch backend without
        # mutating generator.device, which commonly remains "cuda".
        remote_dispatch = (
            self._evo2.device == "modal" or ToolRegistry.dispatch_backend_configured()
        )
        if not remote_dispatch:
            self._evo2.release_kv_cache(cache)
            self._released_cache_ids.add(cache.cache_id)
            return

        if self._modal_release_method is None:
            from proto_tools.modal.app import resolve_environment
            from proto_tools.modal.client import _bound_method

            self._modal_release_method = _bound_method(
                "proto-tools-evo2",
                "Evo2Service",
                "release",
                "evo2-sample",
                environment=resolve_environment(),
            )
        self._modal_release_method.remote(kv_caches=[cache.model_dump(mode="json")])
        self._released_cache_ids.add(cache.cache_id)
