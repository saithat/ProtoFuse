"""Exact input-alignment boundary shared by pair-scaled model backends."""

from __future__ import annotations

import os
from pathlib import Path

from proto_tools.entities.msa import MSA
from proto_tools.tools.structure_prediction.shared_data_models import ComplexMSAs

AF3_SERVER_MSA_ENV = "PROTOFUSE_AF3_SERVER_MSA_A3M"


def load_paper_server_msa(sequence: str) -> ComplexMSAs:
    """Load the user-held AF3 Server alignment without changing or regenerating it."""

    raw_path = os.environ.get(AF3_SERVER_MSA_ENV)
    if not raw_path:
        raise RuntimeError(
            "MSA-backed pair scaling requires the paper's exported AlphaFold "
            f"Server alignment via {AF3_SERVER_MSA_ENV}; ProtoFuse refuses to "
            "substitute a new ColabFold/MMseqs2 alignment"
        )
    path = Path(raw_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"AlphaFold Server MSA not found: {path}")
    msa = MSA.from_file(path)
    if msa.original_sequences[0].upper() != sequence.upper():
        raise ValueError("AlphaFold Server MSA query row does not match the target sequence")
    return ComplexMSAs(per_chain={0: msa}, paired=False)
