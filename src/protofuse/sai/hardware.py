"""Pinned compute contexts for reproducible paired experiments."""

from __future__ import annotations

import os
import platform
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

ModalGpu = Literal["H100:1", "H200:1", "B200:1"]
MODAL_GPU_CHOICES: tuple[ModalGpu, ...] = ("H100:1", "H200:1", "B200:1")


@dataclass(frozen=True)
class LocalHostHardware:
    """Hardware visible to a local experiment process."""

    hostname: str
    machine: str
    cpu_model: str | None
    physical_cores: int | None
    hardware_threads: int | None
    memory_bytes: int | None
    memory_scope: Literal["os_visible"] = "os_visible"


@dataclass(frozen=True)
class ExperimentHardware:
    """The compute allocation shared by both arms of one experiment."""

    device: Literal["local", "modal"]
    accelerator: str | None
    context_id: str
    pairing: str
    max_containers_per_service: int | None
    retries: int | None
    scaledown_window_seconds: int | None
    identity_level: Literal["same_process", "accelerator_class"]
    same_physical_accelerator_verified: bool
    local_host: LocalHostHardware | None

    def as_dict(self) -> dict[str, Any]:
        """Return JSON-ready report provenance."""

        return asdict(self)


def _linux_cpu_topology() -> tuple[str | None, int | None]:
    """Return Linux CPU model and physical-core count without external tools."""

    cpuinfo = Path("/proc/cpuinfo")
    if not cpuinfo.is_file():
        return None, None
    try:
        records = tuple(
            {
                key.strip(): value.strip()
                for line in block.splitlines()
                if ":" in line
                for key, value in (line.split(":", 1),)
            }
            for block in cpuinfo.read_text().split("\n\n")
            if block.strip()
        )
    except OSError:
        return None, None
    model = next(
        (
            record[key]
            for record in records
            for key in ("model name", "Hardware", "Processor")
            if record.get(key)
        ),
        None,
    )
    core_ids = {
        (record["physical id"], record["core id"])
        for record in records
        if record.get("physical id") is not None and record.get("core id") is not None
    }
    return model, len(core_ids) or None


def _os_visible_memory_bytes() -> int | None:
    """Return memory visible to the OS, which may be below installed capacity."""

    try:
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        physical_pages = int(os.sysconf("SC_PHYS_PAGES"))
    except (AttributeError, OSError, TypeError, ValueError):
        return None
    return page_size * physical_pages


def local_host_hardware() -> LocalHostHardware:
    """Capture the local hardware fields needed to interpret timing results."""

    linux_model, linux_physical_cores = _linux_cpu_topology()
    processor = platform.processor().strip()
    return LocalHostHardware(
        hostname=platform.node(),
        machine=platform.machine(),
        cpu_model=linux_model or processor or None,
        physical_cores=linux_physical_cores,
        hardware_threads=os.cpu_count(),
        memory_bytes=_os_visible_memory_bytes(),
    )


def experiment_hardware(
    device: Literal["modal"] | None,
    modal_gpu: str | None,
    *,
    context_id: str | None = None,
) -> ExperimentHardware:
    """Validate and create the hardware context used by a paired run."""

    if device is None:
        if modal_gpu is not None:
            raise ValueError("modal_gpu is only valid when device='modal'")
        return ExperimentHardware(
            device="local",
            accelerator=None,
            context_id="local-process",
            pairing="both arms run sequentially in the same process",
            max_containers_per_service=None,
            retries=None,
            scaledown_window_seconds=None,
            identity_level="same_process",
            same_physical_accelerator_verified=True,
            local_host=local_host_hardware(),
        )
    if modal_gpu not in MODAL_GPU_CHOICES:
        choices = ", ".join(MODAL_GPU_CHOICES)
        raise ValueError(f"device='modal' requires modal_gpu to be one of: {choices}")
    return ExperimentHardware(
        device="modal",
        accelerator=modal_gpu,
        context_id=context_id or f"paired-{uuid.uuid4().hex}",
        pairing=(
            "both arms run sequentially through the same isolated Modal option set "
            "and one-container pool per service; the scheduler enforces accelerator class"
        ),
        max_containers_per_service=1,
        retries=0,
        scaledown_window_seconds=3600,
        identity_level="accelerator_class",
        same_physical_accelerator_verified=False,
        local_host=None,
    )


@contextmanager
def pinned_modal_hardware(hardware: ExperimentHardware) -> Iterator[None]:
    """Pin every remote tool call in this scope to one accelerator class and pool."""

    if hardware.device == "local":
        yield
        return

    import modal
    from proto_tools.modal import client as modal_client

    original_bound_method = modal_client._bound_method

    def pinned_bound_method(
        app_name: str,
        service_class: str,
        method_name: str,
        tool_key: str,
        scaledown_window: int | None = None,
        *,
        environment: str | None = None,
        client: Any | None = None,
    ) -> Any:
        del scaledown_window
        try:
            service = modal.Cls.from_name(
                app_name,
                service_class,
                environment_name=environment,
                client=client,
            ).with_options(
                gpu=hardware.accelerator,
                env={
                    "PROTOFUSE_HARDWARE_CONTEXT": hardware.context_id,
                    "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
                },
                max_containers=hardware.max_containers_per_service,
                retries=hardware.retries,
                scaledown_window=hardware.scaledown_window_seconds,
            )
            service.hydrate()
        except modal.exception.NotFoundError as exc:
            raise modal_client._missing_lookup_error(
                tool_key,
                app_name,
                environment,
                client,
            ) from exc
        except modal.exception.AuthError as exc:
            raise modal_client.ModalCredentialsError(
                "Modal rejected them (expired or invalid)"
            ) from exc
        return getattr(service(), method_name)

    modal_client._bound_method = pinned_bound_method
    try:
        yield
    finally:
        modal_client._bound_method = original_bound_method
