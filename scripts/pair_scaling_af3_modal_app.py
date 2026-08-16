"""Private Modal service for ProtoFuse's optional pair-scaled AlphaFold 3 backend."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import subprocess
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import modal
from proto_tools.modal.app import MODEL_CACHE, SCALEDOWN_WINDOW, get_app
from proto_tools.modal.base_images import with_dependencies, with_proto_tools

APP_NAME = "protofuse-pair-scaling-af3"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

AF3_SERVICE_NAME = "PairScalingAlphaFold3Service"
AF3_GPU = "H100:1"
AF3_CUDA_BASE_IMAGE = "nvidia/cuda:12.6.0-base-ubuntu22.04"
AF3_UPSTREAM_REPOSITORY = "https://github.com/google-deepmind/alphafold3.git"
AF3_UPSTREAM_TAG = "v3.0.1"
AF3_UPSTREAM_COMMIT = "231efc9bb9c13b45cc59e43f7107869084ee9624"
AF3_ROOT = "/opt/alphafold3"
AF3_VENV_ROOT = "/alphafold3_venv"
AF3_PYTHON = f"{AF3_VENV_ROOT}/bin/python"
AF3_MODEL_DIR = "/models"
AF3_MODEL_FILENAME = "af3.bin.zst"
AF3_MODEL_PROVENANCE_FILENAME = f"{AF3_MODEL_FILENAME}.provenance.json"
AF3_MODEL_GCS_GENERATION = "1780568696389861"
AF3_MODEL_SIZE_BYTES = 1_020_545_840
AF3_MODEL_VOLUME_SUBPATH = f"alphafold3/generation-{AF3_MODEL_GCS_GENERATION}"
AF3_MODEL_GCS_URL = (
    "https://storage.googleapis.com/alphafold3/"
    f"{AF3_MODEL_FILENAME}?generation={AF3_MODEL_GCS_GENERATION}"
)
AF3_PROVISION_VOLUME_ROOT = "/private-model-cache"
AF3_PAIR_SCALING_PATCH_SHA256 = "339c4f9f9a8fe607eb01c6e898a57ee3d03b1823b40d8efe99c02e6a8d0cfead"
AF3_STANDALONE_SHA256 = "e163f793c1609522174f89d9ef535920acd7f9dede1b429ee3512c426cf5da86"
AF3_PATCHED_SOURCE_SHA256 = {
    "run_alphafold.py": ("950c4f9b4ebe4265a69b361d76f755268274da023e5fa0f01f2255734b0c09b9"),
    "src/alphafold3/model/model.py": (
        "eb6a1901015c14b40ef22e6fcec45f2df61f0b93780776013e3ef12c526805ac"
    ),
    "src/alphafold3/model/network/evoformer.py": (
        "671d49e0c6b548842dc17d1144096f35dbbe31223d4ea7a9a6ffe056945ca8ac"
    ),
}
AF3_PAPER_BETAS = (
    -0.75,
    -0.60,
    -0.45,
    -0.30,
    -0.15,
    0.15,
    0.30,
    0.45,
    0.60,
    0.75,
)
CONTAINER_AF3_STANDALONE = "/root/pair_scaled_alphafold3_inference.py"
CONTAINER_AF3_PATCH = "/root/alphafold3_v3_0_1_pair_scaling.patch"
LOCAL_AF3_STANDALONE = (
    REPOSITORY_ROOT
    / "src"
    / "protofuse"
    / "phillip"
    / "standalone"
    / "pair_scaled_alphafold3_inference.py"
)
LOCAL_AF3_PATCH = (
    REPOSITORY_ROOT
    / "src"
    / "protofuse"
    / "phillip"
    / "patches"
    / "alphafold3_v3_0_1_pair_scaling.patch"
)

# This mirrors the official v3.0.1 container recipe while pinning the source by
# immutable commit.  The licensed parameters are never part of an image layer.
af3_image = modal.Image.from_registry(
    AF3_CUDA_BASE_IMAGE,
    add_python="3.11",
).apt_install(
    "git",
    "wget",
    "gcc",
    "g++",
    "make",
    "patch",
    "zlib1g-dev",
    "zstd",
)
af3_image = with_dependencies(af3_image)
af3_image = with_proto_tools(af3_image)
af3_image = af3_image.run_commands(
    f"mkdir -p {AF3_ROOT}",
    f"git -C {AF3_ROOT} init",
    f"git -C {AF3_ROOT} remote add origin {AF3_UPSTREAM_REPOSITORY}",
    f"git -C {AF3_ROOT} fetch --depth 1 origin {AF3_UPSTREAM_COMMIT}",
    f"git -C {AF3_ROOT} checkout --detach {AF3_UPSTREAM_COMMIT}",
    f"git -C {AF3_ROOT} rev-parse HEAD | grep -Fx {AF3_UPSTREAM_COMMIT}",
    "mkdir -p /hmmer_build /hmmer",
    (
        "wget --quiet http://eddylab.org/software/hmmer/hmmer-3.4.tar.gz "
        "--directory-prefix /hmmer_build"
    ),
    (
        "echo 'ca70d94fd0cf271bd7063423aabb116d42de533117343a9b27a65c17ff06fbf3  "
        "/hmmer_build/hmmer-3.4.tar.gz' | sha256sum --check --strict"
    ),
    "tar -xzf /hmmer_build/hmmer-3.4.tar.gz -C /hmmer_build",
    "cd /hmmer_build/hmmer-3.4 && ./configure --prefix=/hmmer",
    "make -C /hmmer_build/hmmer-3.4 -j",
    "make -C /hmmer_build/hmmer-3.4 install",
    "make -C /hmmer_build/hmmer-3.4/easel install",
    "rm -rf /hmmer_build",
)
af3_image = af3_image.add_local_file(
    LOCAL_AF3_PATCH,
    CONTAINER_AF3_PATCH,
    copy=True,
)
af3_image = af3_image.run_commands(
    (f"echo '{AF3_PAIR_SCALING_PATCH_SHA256}  {CONTAINER_AF3_PATCH}' | sha256sum --check --strict"),
    f"git -C {AF3_ROOT} apply --check {CONTAINER_AF3_PATCH}",
    f"git -C {AF3_ROOT} apply {CONTAINER_AF3_PATCH}",
    *(
        f"echo '{digest}  {AF3_ROOT}/{relative}' | sha256sum --check --strict"
        for relative, digest in AF3_PATCHED_SOURCE_SHA256.items()
    ),
    f"python -m venv {AF3_VENV_ROOT}",
    f"{AF3_PYTHON} -m pip install --upgrade pip",
    f"{AF3_PYTHON} -m pip install -r {AF3_ROOT}/dev-requirements.txt",
    (f"CMAKE_POLICY_VERSION_MINIMUM=3.5 {AF3_PYTHON} -m pip install --no-deps {AF3_ROOT}"),
    f"{AF3_VENV_ROOT}/bin/build_data",
)
af3_image = af3_image.add_local_file(
    LOCAL_AF3_STANDALONE,
    CONTAINER_AF3_STANDALONE,
    copy=True,
)
af3_image = af3_image.run_commands(
    f"echo '{AF3_STANDALONE_SHA256}  {CONTAINER_AF3_STANDALONE}' | sha256sum --check --strict"
)
af3_image = af3_image.env(
    {
        "PATH": "/hmmer/bin:/usr/local/bin:/usr/bin:/bin",
        "XLA_FLAGS": "--xla_gpu_enable_triton_gemm=false",
        "XLA_PYTHON_CLIENT_PREALLOCATE": "true",
        "XLA_CLIENT_MEM_FRACTION": "0.95",
        "PROTOFUSE_AF3_UPSTREAM_COMMIT": AF3_UPSTREAM_COMMIT,
        "PROTOFUSE_AF3_MODEL_GCS_GENERATION": AF3_MODEL_GCS_GENERATION,
    }
)

af3_provision_image = modal.Image.debian_slim(python_version="3.12").apt_install(
    "ca-certificates",
    "curl",
    "zstd",
)

AF3_MODEL_VOLUME = MODEL_CACHE.with_mount_options(
    read_only=True,
    sub_path=AF3_MODEL_VOLUME_SUBPATH,
)

app = get_app(APP_NAME)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validated_gcs_headers(raw_headers: str) -> dict[str, str]:
    blocks: list[tuple[str, dict[str, str]]] = []
    status = ""
    headers: dict[str, str] = {}
    for raw_line in raw_headers.splitlines():
        line = raw_line.strip()
        if line.startswith("HTTP/"):
            if status:
                blocks.append((status, headers))
            status = line
            headers = {}
        elif not line:
            if status:
                blocks.append((status, headers))
                status = ""
                headers = {}
        elif status and ":" in line:
            name, value = line.split(":", 1)
            headers[name.strip().lower()] = value.strip()
    if status:
        blocks.append((status, headers))

    for response_status, response_headers in reversed(blocks):
        status_parts = response_status.split()
        if len(status_parts) < 2 or status_parts[1] != "200":
            continue
        if response_headers.get("x-goog-generation") != AF3_MODEL_GCS_GENERATION:
            continue
        size_headers = {
            name: response_headers[name]
            for name in ("x-goog-stored-content-length", "content-length")
            if name in response_headers
        }
        if not size_headers:
            raise RuntimeError("official AlphaFold 3 response omitted its object size")
        for name, value in size_headers.items():
            try:
                observed_size = int(value)
            except ValueError as error:
                raise RuntimeError(
                    f"official AlphaFold 3 response had an invalid {name}: {value}"
                ) from error
            if observed_size != AF3_MODEL_SIZE_BYTES:
                raise RuntimeError(
                    f"official AlphaFold 3 response {name} was {observed_size}; "
                    f"expected {AF3_MODEL_SIZE_BYTES}"
                )
        return response_headers
    raise RuntimeError(
        "official AlphaFold 3 response did not identify HTTP 200 generation "
        f"{AF3_MODEL_GCS_GENERATION}"
    )


def _validate_af3_provenance(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"AlphaFold 3 provenance sidecar not found: {path}")
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise RuntimeError("AlphaFold 3 provenance sidecar must contain an object")
    if (
        payload.get("gcs_generation") != AF3_MODEL_GCS_GENERATION
        or payload.get("size_bytes") != AF3_MODEL_SIZE_BYTES
        or payload.get("zstd_test") is not True
    ):
        raise RuntimeError("AlphaFold 3 provenance sidecar does not match the pinned object")
    sha256 = payload.get("sha256")
    if (
        not isinstance(sha256, str)
        or len(sha256) != 64
        or any(character not in "0123456789abcdef" for character in sha256)
    ):
        raise RuntimeError("AlphaFold 3 provenance sidecar has an invalid SHA-256")
    return payload


def _canonical_af3_beta(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("AlphaFold 3 pair-scaling beta must be numeric")
    beta = float(value)
    if not math.isfinite(beta):
        raise ValueError("AlphaFold 3 pair-scaling beta must be finite")
    for allowed in AF3_PAPER_BETAS:
        if math.isclose(beta, allowed, rel_tol=0.0, abs_tol=1e-12):
            return allowed
    raise ValueError(
        f"unsupported AlphaFold 3 pair-scaling beta {beta}; expected one of {AF3_PAPER_BETAS}"
    )


def _positive_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _load_af3_worker() -> ModuleType:
    worker_path = Path(CONTAINER_AF3_STANDALONE)
    if not worker_path.is_file():
        raise FileNotFoundError(f"pair-scaled AlphaFold 3 worker not found: {worker_path}")
    spec = importlib.util.spec_from_file_location(
        "_protofuse_pair_scaled_alphafold3",
        worker_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load AlphaFold 3 worker: {worker_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "dispatch", None)):
        raise RuntimeError("pair-scaled AlphaFold 3 worker has no dispatch callable")
    return module


def _validate_af3_runtime() -> dict[str, Any]:
    model_dir = Path(AF3_MODEL_DIR)
    model_path = model_dir / AF3_MODEL_FILENAME
    if not model_dir.is_dir() or not model_path.is_file():
        raise FileNotFoundError(
            "the private AlphaFold 3 parameter volume is not provisioned at "
            f"{model_path} (GCS generation {AF3_MODEL_GCS_GENERATION})"
        )
    parameter_files = sorted(
        child.name
        for child in model_dir.iterdir()
        if child.is_file() and child.name.endswith((".bin", ".bin.zst"))
    )
    if parameter_files != [AF3_MODEL_FILENAME]:
        raise RuntimeError(
            "the pinned AlphaFold 3 model directory must contain exactly "
            f"{AF3_MODEL_FILENAME}; found {parameter_files}"
        )
    observed_size = model_path.stat().st_size
    if observed_size != AF3_MODEL_SIZE_BYTES:
        raise RuntimeError(
            "AlphaFold 3 parameter size mismatch for pinned GCS generation "
            f"{AF3_MODEL_GCS_GENERATION}: observed {observed_size}, "
            f"expected {AF3_MODEL_SIZE_BYTES}"
        )
    model_provenance = _validate_af3_provenance(model_dir / AF3_MODEL_PROVENANCE_FILENAME)
    observed_sha256 = _sha256_file(model_path)
    if observed_sha256 != model_provenance["sha256"]:
        raise RuntimeError("AlphaFold 3 parameter SHA-256 does not match its provenance sidecar")

    patch_path = Path(CONTAINER_AF3_PATCH)
    if _sha256_file(patch_path) != AF3_PAIR_SCALING_PATCH_SHA256:
        raise RuntimeError("reviewed AlphaFold 3 pair-scaling patch digest drifted")
    if _sha256_file(Path(CONTAINER_AF3_STANDALONE)) != AF3_STANDALONE_SHA256:
        raise RuntimeError("reviewed AlphaFold 3 pair-scaling worker digest drifted")
    for relative, expected_digest in AF3_PATCHED_SOURCE_SHA256.items():
        source = Path(AF3_ROOT) / relative
        if not source.is_file() or _sha256_file(source) != expected_digest:
            raise RuntimeError(f"patched AlphaFold 3 source drifted at {relative}")

    commit = subprocess.run(
        ["git", "-C", AF3_ROOT, "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if commit != AF3_UPSTREAM_COMMIT:
        raise RuntimeError(f"AlphaFold 3 checkout is {commit}; expected {AF3_UPSTREAM_COMMIT}")
    gpu_names = subprocess.run(
        ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    if len(gpu_names) != 1 or "H100" not in gpu_names[0]:
        raise RuntimeError(f"pair-scaled AlphaFold 3 requires one H100; found {gpu_names}")
    if not Path(AF3_PYTHON).is_file():
        raise FileNotFoundError(f"pinned AlphaFold 3 interpreter not found: {AF3_PYTHON}")
    return {
        "upstream_tag": AF3_UPSTREAM_TAG,
        "upstream_commit": commit,
        "patch_sha256": AF3_PAIR_SCALING_PATCH_SHA256,
        "model_filename": AF3_MODEL_FILENAME,
        "model_gcs_generation": AF3_MODEL_GCS_GENERATION,
        "model_size_bytes": observed_size,
        "model_sha256": observed_sha256,
        "model_provisioning_source": model_provenance.get("source"),
        "gpu": gpu_names[0],
    }


def _msa_to_a3m(msa: object, *, expected_query: str) -> str:
    if not isinstance(msa, dict):
        raise ValueError("AlphaFold 3 MSA payload must be an object")
    sequences = msa.get("aligned_sequences")
    sequence_ids = msa.get("sequence_ids")
    if (
        not isinstance(sequences, list)
        or not sequences
        or not all(isinstance(sequence, str) for sequence in sequences)
        or not isinstance(sequence_ids, list)
        or len(sequence_ids) != len(sequences)
        or not all(isinstance(sequence_id, str) for sequence_id in sequence_ids)
    ):
        raise ValueError("AlphaFold 3 MSA payload has invalid sequences or identifiers")
    alignment_width = len(sequences[0])
    if any(len(sequence) != alignment_width for sequence in sequences):
        raise ValueError("AlphaFold 3 MSA rows must have equal aligned lengths")
    if sequences[0].replace("-", "").upper() != expected_query.upper():
        raise ValueError("AlphaFold 3 MSA query row does not match the protein sequence")
    query_gap_positions = {index for index, residue in enumerate(sequences[0]) if residue == "-"}
    lines: list[str] = []
    for sequence_id, sequence in zip(sequence_ids, sequences, strict=True):
        if not sequence_id or "\n" in sequence_id or "\r" in sequence_id:
            raise ValueError("AlphaFold 3 MSA identifiers must be non-empty single lines")
        encoded: list[str] = []
        for index, residue in enumerate(sequence):
            if index in query_gap_positions:
                if residue != "-":
                    encoded.append(residue.lower())
            else:
                encoded.append(residue)
        lines.extend((f">{sequence_id}", "".join(encoded)))
    return "\n".join(lines) + "\n"


def _complex_msa_a3m(
    input_dict: dict[str, Any],
    *,
    sequence: str,
    use_msa: bool,
) -> str:
    msas = input_dict.get("msas")
    if not use_msa:
        if msas not in (None, []):
            raise ValueError("AlphaFold 3 use_msa=False cannot carry an MSA payload")
        return ""
    if not isinstance(msas, list) or len(msas) != 1 or not isinstance(msas[0], dict):
        raise ValueError("MSA-backed pair-scaled AlphaFold 3 requires one complex MSA")
    complex_msa = msas[0]
    if complex_msa.get("paired") not in (False, None):
        raise ValueError("the reviewed single-chain AlphaFold 3 path expects an unpaired MSA")
    unpaired = complex_msa.get("unpaired_per_chain")
    per_chain = unpaired if isinstance(unpaired, dict) else complex_msa.get("per_chain")
    if not isinstance(per_chain, dict):
        raise ValueError("AlphaFold 3 complex MSA has no per-chain alignment")
    chain_msa = per_chain.get("0", per_chain.get(0))
    return _msa_to_a3m(chain_msa, expected_query=sequence)


def _native_af3_input(
    input_dict: dict[str, Any],
    config_dict: dict[str, Any],
) -> tuple[dict[str, Any], int, int, str, bool]:
    complexes = input_dict.get("complexes")
    if not isinstance(complexes, list) or len(complexes) != 1:
        raise ValueError("pair-scaled AlphaFold 3 requires exactly one fixed complex")
    complex_payload = complexes[0]
    if not isinstance(complex_payload, dict):
        raise ValueError("AlphaFold 3 complex payload must be an object")
    chains = complex_payload.get("chains")
    if not isinstance(chains, list) or len(chains) != 1 or not isinstance(chains[0], dict):
        raise ValueError("the reviewed AlphaFold 3 pair-scaling path is single-chain")
    chain = chains[0]
    if chain.get("entity_type") != "protein":
        raise ValueError("the reviewed AlphaFold 3 pair-scaling path requires protein input")
    sequence = chain.get("sequence")
    if not isinstance(sequence, str) or not sequence:
        raise ValueError("AlphaFold 3 protein sequence must be non-empty")

    device = config_dict.get("device")
    if device != "cuda" and not (
        isinstance(device, str) and device.startswith("cuda:") and device[5:].isdigit()
    ):
        raise ValueError("pair-scaled AlphaFold 3 requires a CUDA device")
    if config_dict.get("sif_path") not in (None, ""):
        raise ValueError("pair-scaled AlphaFold 3 refuses an opaque SIF runtime")
    if config_dict.get("model_dir") not in (None, "", AF3_MODEL_DIR):
        raise ValueError("pair-scaled AlphaFold 3 refuses an unpinned model directory")

    model_seed = config_dict.get("seed")
    if model_seed is None:
        configured_seeds = config_dict.get("seeds")
        if not isinstance(configured_seeds, list) or len(configured_seeds) != 1:
            raise ValueError("pair-scaled AlphaFold 3 requires exactly one model seed")
        model_seed = configured_seeds[0]
    if isinstance(model_seed, bool) or not isinstance(model_seed, int) or model_seed < 0:
        raise ValueError("AlphaFold 3 model seed must be a non-negative integer")

    num_recycles = _positive_int(config_dict.get("num_recycles"), label="num_recycles")
    num_diffusion_samples = _positive_int(
        config_dict.get("num_diffusion_samples"),
        label="num_diffusion_samples",
    )
    use_msa = config_dict.get("use_msa")
    if not isinstance(use_msa, bool):
        raise ValueError("AlphaFold 3 use_msa must be a boolean")
    unpaired_msa = _complex_msa_a3m(
        input_dict,
        sequence=sequence,
        use_msa=use_msa,
    )

    chain_id = chain.get("id") or "A"
    if not isinstance(chain_id, str) or not chain_id:
        raise ValueError("AlphaFold 3 chain id must be a non-empty string")
    protein: dict[str, Any] = {
        "id": chain_id,
        "sequence": sequence,
        "pairedMsa": "",
        "unpairedMsa": unpaired_msa,
        "templates": [],
    }
    modifications = chain.get("modifications")
    if modifications:
        if not isinstance(modifications, list) or not all(
            isinstance(modification, dict) for modification in modifications
        ):
            raise ValueError("AlphaFold 3 protein modifications are invalid")
        protein["modifications"] = [
            {
                "ptmType": modification["modification_code"],
                "ptmPosition": modification["position"],
            }
            for modification in modifications
        ]
    native_input = {
        "name": str(config_dict.get("name") or "protofuse_pair_scaled_af3"),
        "modelSeeds": [model_seed],
        "sequences": [{"protein": protein}],
        "dialect": "alphafold3",
        "version": 2,
    }
    return (
        native_input,
        num_recycles,
        num_diffusion_samples,
        device,
        bool(config_dict.get("include_pae_matrix")),
    )


def _af3_structure_payload(prediction: object) -> dict[str, Any]:
    if not isinstance(prediction, dict):
        raise RuntimeError("AlphaFold 3 worker returned an invalid prediction")
    structure = prediction.get("structure_cif_output")
    metrics = prediction.get("metrics")
    if not isinstance(structure, str) or not structure or not isinstance(metrics, dict):
        raise RuntimeError("AlphaFold 3 worker returned incomplete structure output")
    if not isinstance(metrics.get("avg_plddt"), (int, float)) or not isinstance(
        metrics.get("avg_pae"), (int, float)
    ):
        raise RuntimeError("AlphaFold 3 worker omitted required confidence metrics")
    metric_payload: dict[str, Any] = {
        "primary_metric": "avg_plddt",
        "metric_type": "AlphaFold3Metrics",
    }
    for name in (
        "avg_plddt",
        "avg_pae",
        "pae",
        "ptm",
        "iptm",
        "chain_pair_iptm",
        "ranking_score",
    ):
        if metrics.get(name) is not None:
            metric_payload[name] = metrics[name]
    return {
        "structure": structure,
        "structure_format": "cif",
        "b_factor_type": "pLDDT",
        "source": "alphafold3-pair-scaled",
        "metrics": metric_payload,
    }


@app.function(
    image=af3_provision_image,
    volumes={AF3_PROVISION_VOLUME_ROOT: MODEL_CACHE},
    cpu=1.0,
    memory=1024,
    timeout=3600,
    retries=0,
    max_containers=1,
    include_source=False,
    serialized=True,
)
def provision_official_af3_model() -> dict[str, Any]:
    """Stream and verify the exact official AF3 object into the private volume."""

    target_dir = Path(AF3_PROVISION_VOLUME_ROOT) / AF3_MODEL_VOLUME_SUBPATH
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / AF3_MODEL_FILENAME
    sidecar = target_dir / AF3_MODEL_PROVENANCE_FILENAME
    lock_path = target_dir / f".{AF3_MODEL_FILENAME}.provision.lock"
    unique = uuid.uuid4().hex
    partial = target_dir / f".{AF3_MODEL_FILENAME}.{unique}.part"
    partial_sidecar = target_dir / f".{AF3_MODEL_PROVENANCE_FILENAME}.{unique}.part"
    header_path = Path("/tmp") / f"af3-{unique}.headers"
    lock_created = False
    installed_target = False
    installed_sidecar = False
    try:
        try:
            lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as error:
            raise RuntimeError("another AlphaFold 3 provisioning call is active") from error
        with os.fdopen(lock_fd, "w") as lock_handle:
            lock_handle.write(f"pid={os.getpid()}\n")
        lock_created = True
        if target.exists() or sidecar.exists():
            raise FileExistsError(
                "pinned AlphaFold 3 parameters or provenance already exist; "
                "refusing to overwrite them"
            )

        download = subprocess.run(
            [
                "curl",
                "--fail",
                "--silent",
                "--show-error",
                "--location",
                "--proto",
                "=https",
                "--tlsv1.2",
                "--retry",
                "5",
                "--retry-all-errors",
                "--connect-timeout",
                "30",
                "--dump-header",
                str(header_path),
                "--output",
                str(partial),
                AF3_MODEL_GCS_URL,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if download.returncode != 0:
            raise RuntimeError(
                "official AlphaFold 3 parameter download failed: "
                f"{download.stderr.strip() or '<no stderr>'}"
            )
        response_headers = _validated_gcs_headers(header_path.read_text())
        observed_size = partial.stat().st_size
        if observed_size != AF3_MODEL_SIZE_BYTES:
            raise RuntimeError(
                f"downloaded AlphaFold 3 object is {observed_size} bytes; "
                f"expected {AF3_MODEL_SIZE_BYTES}"
            )
        zstd_test = subprocess.run(
            ["zstd", "--test", "--quiet", str(partial)],
            check=False,
            capture_output=True,
            text=True,
        )
        if zstd_test.returncode != 0:
            raise RuntimeError(
                "downloaded AlphaFold 3 object failed zstd --test: "
                f"{zstd_test.stderr.strip() or '<no stderr>'}"
            )
        sha256 = _sha256_file(partial)
        provenance: dict[str, Any] = {
            "schema_version": 1,
            "source": "google-deepmind-official-gcs",
            "object": f"gs://alphafold3/{AF3_MODEL_FILENAME}",
            "versioned_url": AF3_MODEL_GCS_URL,
            "gcs_generation": AF3_MODEL_GCS_GENERATION,
            "header_generation": response_headers["x-goog-generation"],
            "size_bytes": observed_size,
            "sha256": sha256,
            "zstd_test": True,
            "fetched_at": datetime.now(UTC).isoformat(),
        }
        partial_sidecar.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
        os.replace(partial, target)
        installed_target = True
        os.replace(partial_sidecar, sidecar)
        installed_sidecar = True
        lock_path.unlink()
        lock_created = False
        MODEL_CACHE.commit()
        return provenance
    except BaseException:
        if installed_sidecar:
            sidecar.unlink(missing_ok=True)
        if installed_target:
            target.unlink(missing_ok=True)
        raise
    finally:
        partial.unlink(missing_ok=True)
        partial_sidecar.unlink(missing_ok=True)
        header_path.unlink(missing_ok=True)
        if lock_created:
            lock_path.unlink(missing_ok=True)


@app.cls(
    include_source=False,
    image=af3_image,
    gpu=AF3_GPU,
    scaledown_window=SCALEDOWN_WINDOW,
    volumes={AF3_MODEL_DIR: AF3_MODEL_VOLUME},
    timeout=3600,
    retries=0,
)
class PairScalingAlphaFold3Service:
    """Private H100 service for the pinned and audited AF3 v3.0.1 patch."""

    @modal.enter()
    def setup(self) -> None:
        self._provenance = _validate_af3_runtime()
        self._worker = _load_af3_worker()

    @modal.method()
    def provenance(self) -> dict[str, Any]:
        """Return runtime pins after setup has validated every local artifact."""

        return dict(self._provenance)

    @modal.method()
    def predict(
        self,
        input_dict: dict[str, Any],
        config_dict: dict[str, Any],
        beta: float,
    ) -> list[dict[str, Any]]:
        canonical_beta = _canonical_af3_beta(beta)
        (
            native_input,
            num_recycles,
            num_diffusion_samples,
            device,
            include_pae_matrix,
        ) = _native_af3_input(input_dict, config_dict)
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "input.json"
            output_dir = temp_path / "output"
            input_path.write_text(json.dumps(native_input))
            output_data = self._worker.dispatch(
                {
                    "operation": "predict_pair_scaled",
                    "alphafold3_root": AF3_ROOT,
                    "patch_path": CONTAINER_AF3_PATCH,
                    "alphafold3_python_path": AF3_PYTHON,
                    "input_json_path": str(input_path),
                    "output_dir": str(output_dir),
                    "model_dir": AF3_MODEL_DIR,
                    "device": device,
                    "verbose": bool(config_dict.get("verbose")),
                    "include_pae_matrix": include_pae_matrix,
                    "num_recycles": num_recycles,
                    "num_diffusion_samples": num_diffusion_samples,
                    "beta": canonical_beta,
                }
            )

        audit = output_data.get("pair_scaling_audit")
        if not isinstance(audit, dict):
            raise RuntimeError("AlphaFold 3 pair-scaling worker returned no audit record")
        expected_invocations = num_recycles + 1
        if (
            audit.get("upstream_commit") != AF3_UPSTREAM_COMMIT
            or audit.get("patch_sha256") != AF3_PAIR_SCALING_PATCH_SHA256
            or audit.get("beta") != canonical_beta
            or audit.get("expected_invocations_per_seed") != expected_invocations
            or audit.get("observed_invocations_per_seed") != expected_invocations
        ):
            raise RuntimeError("AlphaFold 3 pair-scaling audit record did not match the request")
        predictions = output_data.get("predictions")
        if not isinstance(predictions, list) or len(predictions) != num_diffusion_samples:
            raise RuntimeError(
                "AlphaFold 3 pair-scaling worker did not return every requested "
                f"diffusion sample: expected {num_diffusion_samples}"
            )
        sample_indices = [
            prediction.get("sample_index") if isinstance(prediction, dict) else None
            for prediction in predictions
        ]
        if sample_indices != list(range(num_diffusion_samples)):
            raise RuntimeError(
                "AlphaFold 3 pair-scaling worker returned unexpected sample indices: "
                f"{sample_indices}"
            )
        return [_af3_structure_payload(prediction) for prediction in predictions]


@app.local_entrypoint(name="fetch-official-af3-model")
def fetch_official_af3_model() -> None:
    """Run the private, generation-pinned GCS-to-Volume provisioning job."""

    provenance = provision_official_af3_model.remote()
    print(json.dumps(provenance, indent=2, sort_keys=True))


@app.local_entrypoint(name="provision-af3-model")
def provision_af3_model(
    model_path: str,
    generation: str = AF3_MODEL_GCS_GENERATION,
) -> None:
    """Upload user-obtained AF3 parameters into the pinned private volume path."""

    if generation != AF3_MODEL_GCS_GENERATION:
        raise ValueError(f"expected GCS generation {AF3_MODEL_GCS_GENERATION}, got {generation}")
    local_path = Path(model_path).expanduser().resolve()
    if not local_path.is_file():
        raise FileNotFoundError(f"AlphaFold 3 parameter file not found: {local_path}")
    observed_size = local_path.stat().st_size
    if observed_size != AF3_MODEL_SIZE_BYTES:
        raise ValueError(
            f"AlphaFold 3 parameter file is {observed_size} bytes; "
            f"expected {AF3_MODEL_SIZE_BYTES} for generation {generation}"
        )
    try:
        zstd_test = subprocess.run(
            ["zstd", "--test", "--quiet", str(local_path)],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as error:
        raise RuntimeError("zstd is required to validate AlphaFold 3 parameters") from error
    if zstd_test.returncode != 0:
        raise ValueError(
            "AlphaFold 3 parameter file failed zstd --test: "
            f"{zstd_test.stderr.strip() or '<no stderr>'}"
        )
    sha256 = _sha256_file(local_path)
    provenance = {
        "schema_version": 1,
        "source": "user-provided-official-gcs-object",
        "object": f"gs://alphafold3/{AF3_MODEL_FILENAME}",
        "gcs_generation": generation,
        "size_bytes": observed_size,
        "sha256": sha256,
        "zstd_test": True,
        "provisioned_at": datetime.now(UTC).isoformat(),
    }
    remote_path = f"/{AF3_MODEL_VOLUME_SUBPATH}/{AF3_MODEL_FILENAME}"
    remote_sidecar = f"/{AF3_MODEL_VOLUME_SUBPATH}/{AF3_MODEL_PROVENANCE_FILENAME}"
    with tempfile.TemporaryDirectory() as temp_dir:
        local_sidecar = Path(temp_dir) / AF3_MODEL_PROVENANCE_FILENAME
        local_sidecar.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
        with MODEL_CACHE.batch_upload(force=False) as upload:
            upload.put_file(local_path, remote_path)
            upload.put_file(local_sidecar, remote_sidecar)
    print(
        "Provisioned private AlphaFold 3 parameters: "
        f"{MODEL_CACHE.name}:{remote_path} "
        f"(generation={generation}, size={observed_size}, sha256={sha256})"
    )

