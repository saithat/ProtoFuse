"""Audited Boltz-2 pair-representation scaling worker.

This module runs inside proto-tools' isolated Boltz environment.  It wraps the
installed, official Boltz inference entrypoint and changes one boundary only:
the pair representation passed into Pairformer is multiplied by ``1 + beta``.
The hook is counted and each prediction fails unless it ran once per trunk pass.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any, cast

_base: ModuleType | None = None
_model: Any = None
_loader_installed = False
_active_audit: dict[str, Any] | None = None


def _prepare_output_values(value: Any) -> Any:
    """Match the official worker's JSON conversion for indexed model outputs."""

    if isinstance(value, dict):
        return [_prepare_output_values(value[str(key)]) for key in range(len(value))]
    return value


def _extract_diffusion_samples(
    output_dir: str,
    input_path: str,
    *,
    diffusion_samples: int,
    include_pae_matrix: bool,
) -> list[dict[str, Any]]:
    """Return every Boltz diffusion sample instead of silently keeping model zero."""

    import numpy as np

    input_name = Path(input_path).stem
    prediction_dir = (
        Path(output_dir) / f"boltz_results_{input_name}" / "predictions" / input_name
    )
    if not prediction_dir.is_dir():
        raise FileNotFoundError(
            f"Boltz prediction directory not found: {prediction_dir}"
        )

    outputs: list[dict[str, Any]] = []
    for sample_index in range(diffusion_samples):
        confidence_path = prediction_dir / (
            f"confidence_{input_name}_model_{sample_index}.json"
        )
        cif_path = prediction_dir / f"{input_name}_model_{sample_index}.cif"
        pae_path = prediction_dir / f"pae_{input_name}_model_{sample_index}.npz"
        for required_path in (confidence_path, cif_path, pae_path):
            if not required_path.is_file():
                raise FileNotFoundError(
                    "Boltz did not emit every requested diffusion sample: "
                    f"missing {required_path}"
                )

        confidence_data = json.loads(confidence_path.read_text())
        metrics = {
            key: _prepare_output_values(value)
            for key, value in confidence_data.items()
        }
        with np.load(pae_path) as npz:
            pae_array = npz["pae"]
        metrics["avg_pae"] = float(pae_array.mean())
        metrics["pae"] = (
            pae_array.astype(float).tolist() if include_pae_matrix else None
        )
        outputs.append(
            {
                "sample_index": sample_index,
                "structure_cif_output": cif_path.read_text(),
                "metrics": metrics,
            }
        )
    return outputs


def _load_base(path: str) -> ModuleType:
    global _base
    if _base is not None:
        return _base
    source = Path(path).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"official proto-tools Boltz worker not found: {source}")
    spec = importlib.util.spec_from_file_location("_protofuse_official_boltz2", source)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load official proto-tools Boltz worker: {source}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _base = module
    return module


def _scaled_pairformer_inputs(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    *,
    beta: float,
    audit: dict[str, Any],
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    """Scale only Pairformer's ``z`` input and record one audited invocation."""

    audit["invocations"] = int(audit["invocations"]) + 1
    factor = 1.0 + beta
    if "z" in kwargs:
        updated_kwargs = dict(kwargs)
        updated_kwargs["z"] = kwargs["z"] * factor
        return args, updated_kwargs
    if len(args) < 2:
        raise RuntimeError("Boltz Pairformer call did not expose the expected z input")
    updated_args = list(args)
    updated_args[1] = args[1] * factor
    return tuple(updated_args), kwargs


def _install_pair_scaling_loader(base: ModuleType) -> None:
    """Attach the audited pre-hook whenever official Boltz loads its checkpoint."""

    global _loader_installed
    if _loader_installed:
        return

    base._install_checkpoint_cache()  # noqa: SLF001 - reviewed upstream worker boundary
    from boltz.model.models.boltz2 import Boltz2  # type: ignore[import-not-found]

    cached_load = Boltz2.load_from_checkpoint

    def load_with_pair_scaling(checkpoint: Any, **kwargs: Any) -> Any:
        model = cached_load(checkpoint, **kwargs)
        audit = _active_audit
        if audit is None:
            raise RuntimeError("pair-scaling audit context is missing during checkpoint load")

        previous = getattr(model, "_protofuse_pair_scaling_hook", None)
        if previous is not None:
            previous.remove()

        pairformer = model.pairformer_module
        pairformer = getattr(pairformer, "_orig_mod", pairformer)
        beta = float(audit["beta"])

        def scale_hook(
            _module: Any,
            args: tuple[Any, ...],
            call_kwargs: dict[str, Any],
        ) -> tuple[tuple[Any, ...], dict[str, Any]]:
            return _scaled_pairformer_inputs(
                args,
                call_kwargs,
                beta=beta,
                audit=audit,
            )

        handle = pairformer.register_forward_pre_hook(scale_hook, with_kwargs=True)
        model._protofuse_pair_scaling_hook = handle
        return model

    Boltz2.load_from_checkpoint = load_with_pair_scaling
    _loader_installed = True


def _predict(input_dict: dict[str, Any]) -> dict[str, Any]:
    global _active_audit, _model

    base = _load_base(str(input_dict["base_inference_path"]))
    _install_pair_scaling_loader(base)
    if _model is None:
        _model = base.Boltz2Model()

    recycling_steps = int(input_dict["recycling_steps"])
    audit: dict[str, Any] = {
        "beta": float(input_dict["beta"]),
        "scale_factor": 1.0 + float(input_dict["beta"]),
        "invocations": 0,
        "expected_invocations": recycling_steps + 1,
    }
    _active_audit = audit
    try:
        _model._run_boltz_predict(  # noqa: SLF001 - same reviewed boundary as proto-tools
            input_yaml_path=input_dict["input_yaml_path"],
            output_dir=input_dict["output_dir"],
            device=input_dict["device"],
            recycling_steps=recycling_steps,
            sampling_steps=int(input_dict["sampling_steps"]),
            diffusion_samples=int(input_dict["diffusion_samples"]),
            step_scale=float(input_dict["step_scale"]),
            max_msa_seqs=int(input_dict["max_msa_seqs"]),
            subsample_msa=bool(input_dict["subsample_msa"]),
            num_workers=int(input_dict["num_workers"]),
            seed=input_dict["seed"],
            verbose=bool(input_dict["verbose"]),
        )
    finally:
        _active_audit = None

    if audit["invocations"] != audit["expected_invocations"]:
        raise RuntimeError(
            "Boltz pair scaling did not run at every Pairformer recycle input: "
            f"observed {audit['invocations']}, expected {audit['expected_invocations']}"
        )
    predictions = _extract_diffusion_samples(
        input_dict["output_dir"],
        input_dict["input_yaml_path"],
        diffusion_samples=int(input_dict["diffusion_samples"]),
        include_pae_matrix=bool(input_dict["include_pae_matrix"]),
    )
    return {
        "predictions": predictions,
        "pair_scaling_audit": audit,
    }


def dispatch(input_dict: dict[str, Any]) -> dict[str, Any]:
    """Persistent-worker entrypoint."""

    if input_dict.get("operation") != "predict_pair_scaled":
        raise ValueError("pair-scaled Boltz worker only accepts 'predict_pair_scaled'")
    return _predict(input_dict)


def to_device(device: str) -> dict[str, Any]:
    """Delegate resident-model relocation to the official worker."""

    if _base is None:
        return {"success": True, "device": device, "models_moved": 0}
    return cast(dict[str, Any], _base.to_device(device))


def get_memory_stats() -> dict[str, Any]:
    """Delegate worker memory telemetry to the official worker."""

    if _base is None:
        return {"available": False, "error": "model not loaded"}
    return cast(dict[str, Any], _base.get_memory_stats())
