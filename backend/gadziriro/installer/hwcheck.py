"""Installer hardware check (FR-27).

Detects GPU/CPU/RAM/disk on the target host and derives which fine-tuning
methods and model sizes the box can support, following the sizing table in
BRD §20 and the recommended SME-server thresholds.

All ``nvidia-smi`` interaction is isolated behind an injectable ``runner``
callable so this module imports and runs on any host (including machines with
no NVIDIA GPU and no ``nvidia-smi`` binary), and so tests can feed canned
output without a real GPU.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable, Optional

import psutil

from gadziriro.core.config import Settings
from gadziriro.gateway.schemas import HardwareReport

# Type of the nvidia-smi runner: takes nothing, returns the raw stdout string.
GpuRunner = Callable[[], str]

# nvidia-smi query that prints one integer (total MB) per GPU, no header/units.
_NVIDIA_SMI_CMD = [
    "nvidia-smi",
    "--query-gpu=memory.total",
    "--format=csv,noheader,nounits",
]

# Sizing / warning thresholds (MB). Tolerances absorb vendor rounding of the
# nominal 24 / 48 / 80 GB cards.
_VRAM_24GB = 23000
_VRAM_48GB = 47000
_VRAM_80GB = 79000
_RECOMMENDED_RAM_MB = 128000
_MIN_FREE_DISK_GB = 100

_MB = 1024 * 1024


def _default_runner() -> str:
    """Run the real ``nvidia-smi`` and return its stdout.

    Raises ``FileNotFoundError`` when the binary is absent and
    ``subprocess.CalledProcessError`` on a non-zero exit; ``detect_gpus``
    catches both and treats them as "no GPU".
    """
    completed = subprocess.run(
        _NVIDIA_SMI_CMD,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout


def detect_gpus(runner: Optional[GpuRunner] = None) -> list[int]:
    """Return total memory (MB) of each detected NVIDIA GPU.

    ``runner`` is a callable returning raw ``nvidia-smi`` stdout; it defaults to
    a real ``nvidia-smi`` subprocess. If the binary is missing
    (``FileNotFoundError``) or exits non-zero (``CalledProcessError``), this
    returns an empty list, meaning "no GPU" rather than raising.

    The injection point lets tests feed canned output on a host with no GPU.
    """
    run = runner or _default_runner
    try:
        stdout = run()
    except (FileNotFoundError, subprocess.CalledProcessError, OSError):
        return []

    memory_mb: list[int] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            memory_mb.append(int(float(line)))
        except ValueError:
            # Ignore unparseable lines rather than failing the whole check.
            continue
    return memory_mb


def _disk_free_gb(data_dir: Path) -> float:
    """Free space (GB) on the drive that holds ``data_dir``.

    Walks up to the nearest existing ancestor so the check works even before the
    data dir is created; falls back to the current working directory.
    """
    probe = data_dir.resolve()
    while not probe.exists():
        parent = probe.parent
        if parent == probe:
            probe = Path.cwd()
            break
        probe = parent
    usage = psutil.disk_usage(str(probe))
    return round(usage.free / (1000 * 1000 * 1000), 2)


def _derive_sizing(
    gpu_memory_mb: list[int],
) -> tuple[list[str], list[str], list[str]]:
    """Map detected VRAM to (supported_methods, recommended_model_sizes, warnings).

    Sizing follows BRD §20, keyed off the LARGEST single GPU's memory.
    """
    methods: list[str] = []
    sizes: list[str] = []
    warnings: list[str] = []

    if not gpu_memory_mb:
        methods.append("cpu-only (no fine-tuning)")
        warnings.append("No NVIDIA GPU detected; fine-tuning unavailable.")
        return methods, sizes, warnings

    largest = max(gpu_memory_mb)
    gpu_count = len(gpu_memory_mb)

    if largest >= _VRAM_24GB:
        methods.append("QLoRA")
        sizes.extend(["7B", "13B"])
    if largest >= _VRAM_48GB:
        methods.append("LoRA (small models)")
        sizes.extend(["30B", "70B (with care)"])
    if largest >= _VRAM_80GB:
        methods.append("Full fine-tune (mid-size)")
        if gpu_count > 1:
            warnings.append(
                f"{gpu_count} GPUs detected; multi-GPU training can target "
                "larger models with the right framework."
            )

    if not methods:
        # GPU present but below the smallest supported tier.
        methods.append("cpu-only (no fine-tuning)")
        warnings.append("GPU VRAM below 24 GB; fine-tuning not supported on this GPU.")

    return methods, sizes, warnings


def check_hardware(
    settings: Optional[Settings] = None,
    gpu_runner: Optional[GpuRunner] = None,
) -> HardwareReport:
    """Probe the host and return a :class:`HardwareReport` (FR-27).

    Gathers GPU memory (via :func:`detect_gpus`), logical CPU count, total RAM,
    and free disk on the data dir's drive, then derives supported fine-tuning
    methods and recommended model sizes per BRD §20. Never raises for missing
    hardware: a GPU-less host yields a CPU-only report with a warning.
    """
    settings = settings or Settings()

    gpu_memory_mb = detect_gpus(gpu_runner)
    cpu_count = psutil.cpu_count(logical=True) or 1
    ram_mb = psutil.virtual_memory().total // _MB
    disk_free_gb = _disk_free_gb(settings.data_dir)

    methods, sizes, warnings = _derive_sizing(gpu_memory_mb)

    if ram_mb < _RECOMMENDED_RAM_MB:
        warnings.append("Less than recommended 128 GB system RAM.")
    if disk_free_gb < _MIN_FREE_DISK_GB:
        warnings.append("Low free disk for model storage.")

    return HardwareReport(
        gpu_present=bool(gpu_memory_mb),
        gpu_count=len(gpu_memory_mb),
        gpu_memory_mb=gpu_memory_mb,
        cpu_count=cpu_count,
        ram_mb=ram_mb,
        disk_free_gb=disk_free_gb,
        supported_methods=methods,
        recommended_model_sizes=sizes,
        warnings=warnings,
    )
