"""Hash-verified genomic context used by the Evo 2 regulatory-design fixture."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class GenomicInterval:
    """One zero-based, half-open reference-genome interval."""

    assembly: str
    chromosome: str
    start: int
    end: int
    expected_sha256: str

    @property
    def length(self) -> int:
        return self.end - self.start


def _interval_from_mapping(payload: dict[str, Any], name: str) -> GenomicInterval:
    interval = GenomicInterval(
        assembly=str(payload["assembly"]),
        chromosome=str(payload["chromosome"]),
        start=int(payload[f"{name}_start_0based"]),
        end=int(payload[f"{name}_end_0based"]),
        expected_sha256=str(payload[f"{name}_sha256"]),
    )
    if interval.start < 0 or interval.end <= interval.start:
        raise ValueError(f"invalid {name} genomic interval: {interval.start}:{interval.end}")
    if len(interval.expected_sha256) != 64:
        raise ValueError(f"invalid {name} SHA-256 digest")
    return interval


@lru_cache(maxsize=4)
def _fetch_ucsc_dna(interval: GenomicInterval) -> str:
    """Fetch and authenticate one interval from the UCSC Genome Browser API."""

    query = urlencode(
        {
            "genome": interval.assembly,
            "chrom": interval.chromosome,
            "start": interval.start,
            "end": interval.end,
        }
    )
    request = Request(
        f"https://api.genome.ucsc.edu/getData/sequence?{query}",
        headers={"User-Agent": "ProtoFuse/0.1 genome-context verifier"},
    )
    with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed HTTPS host
        payload = json.loads(response.read().decode("utf-8"))
    sequence = str(payload.get("dna", "")).upper()
    if len(sequence) != interval.length:
        raise ValueError(
            f"UCSC returned {len(sequence)} bp for an expected {interval.length}-bp interval"
        )
    unsupported = sorted(set(sequence) - set("ACGTN"))
    if unsupported:
        raise ValueError(f"UCSC sequence contains unsupported symbols: {unsupported}")
    digest = sha256(sequence.encode("ascii")).hexdigest()
    if digest != interval.expected_sha256:
        raise ValueError(
            f"UCSC sequence hash mismatch for {interval.chromosome}:{interval.start}-{interval.end}"
        )
    return sequence


def resolve_evo2_genomic_context(payload: dict[str, Any]) -> tuple[str, str, str]:
    """Return full left flank, 40,960-bp generator prompt, and full right flank."""

    left = _fetch_ucsc_dna(_interval_from_mapping(payload, "left_context"))
    right = _fetch_ucsc_dna(_interval_from_mapping(payload, "right_context"))
    prompt_bp = int(payload["generator_prompt_bp"])
    if not 0 < prompt_bp <= len(left):
        raise ValueError(f"invalid Evo 2 generator prompt length: {prompt_bp}")
    prompt = left[-prompt_bp:]
    expected_prompt_hash = str(payload["generator_prompt_sha256"])
    if sha256(prompt.encode("ascii")).hexdigest() != expected_prompt_hash:
        raise ValueError("Evo 2 generator prompt hash does not match the registered interval")
    return left, prompt, right
