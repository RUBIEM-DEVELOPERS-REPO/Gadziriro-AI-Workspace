"""Acceptance tests for FR-27: installer hardware check.

Verifies the installer surfaces a usable :class:`HardwareReport` both on a
GPU-equipped host (mocked nvidia-smi) and on a GPU-less host, without raising.
"""

from __future__ import annotations

import shutil
import sys

import pytest

from gadziriro.gateway.schemas import HardwareReport
from gadziriro.installer import hwcheck

_ON_TARGET = sys.platform.startswith("linux") and shutil.which("nvidia-smi") is not None


def test_installer_reports_methods_and_sizes_with_24gb_gpu() -> None:
    """With a mocked 24 GB NVIDIA GPU the installer names a method and a size."""
    report = hwcheck.check_hardware(gpu_runner=lambda: "24576\n")

    assert isinstance(report, HardwareReport)
    assert report.gpu_present is True
    assert len(report.supported_methods) >= 1
    assert len(report.recommended_model_sizes) >= 1


def test_installer_no_gpu_host_warns_and_does_not_raise() -> None:
    """A no-GPU host returns a report carrying a warning, never an exception."""

    def no_nvidia_smi() -> str:
        raise FileNotFoundError("nvidia-smi absent on this host")

    report = hwcheck.check_hardware(gpu_runner=no_nvidia_smi)

    assert isinstance(report, HardwareReport)
    assert report.gpu_present is False
    assert len(report.warnings) >= 1


@pytest.mark.target_hardware
@pytest.mark.skipif(
    not _ON_TARGET, reason="requires the Linux+NVIDIA target box (real nvidia-smi)"
)
def test_fr27_real_gpu_detection_on_target() -> None:
    """Real-GPU verification stub (runs on the Linux+NVIDIA box only).

    On target hardware this calls the default runner (real ``nvidia-smi``) and
    asserts at least one GPU with a supported fine-tuning method is detected.
    Skipped off-target via the ``target_hardware`` marker + skipif guard.
    """
    report = hwcheck.check_hardware()

    assert report.gpu_present is True
    assert report.gpu_count >= 1
    assert "QLoRA" in report.supported_methods
