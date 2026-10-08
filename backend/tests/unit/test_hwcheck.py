"""Unit tests for the installer hardware check (FR-27)."""

from __future__ import annotations

import pytest

from gadziriro.installer import hwcheck


def test_single_24gb_gpu_enables_qlora() -> None:
    report = hwcheck.check_hardware(gpu_runner=lambda: "24576\n")

    assert report.gpu_present is True
    assert report.gpu_count == 1
    assert report.gpu_memory_mb == [24576]
    assert "QLoRA" in report.supported_methods
    assert "7B" in report.recommended_model_sizes
    assert "13B" in report.recommended_model_sizes


def test_two_gpus_largest_drives_sizing() -> None:
    # 48 GB + 80 GB: largest (80 GB) unlocks every tier.
    report = hwcheck.check_hardware(gpu_runner=lambda: "49152\n81920\n")

    assert report.gpu_count == 2
    assert report.gpu_present is True
    assert "QLoRA" in report.supported_methods
    assert "LoRA (small models)" in report.supported_methods
    assert "Full fine-tune (mid-size)" in report.supported_methods
    assert "70B (with care)" in report.recommended_model_sizes
    # Multi-GPU note present.
    assert any("GPUs detected" in w for w in report.warnings)


def test_no_nvidia_smi_degrades_gracefully() -> None:
    def runner() -> str:
        raise FileNotFoundError("nvidia-smi not found")

    report = hwcheck.check_hardware(gpu_runner=runner)

    assert report.gpu_present is False
    assert report.gpu_count == 0
    assert report.gpu_memory_mb == []
    assert report.supported_methods == ["cpu-only (no fine-tuning)"]
    assert report.recommended_model_sizes == []
    assert any("No NVIDIA GPU detected" in w for w in report.warnings)


def test_detect_gpus_returns_empty_on_missing_binary() -> None:
    def runner() -> str:
        raise FileNotFoundError

    assert hwcheck.detect_gpus(runner) == []


def test_detect_gpus_parses_and_skips_blank_lines() -> None:
    assert hwcheck.detect_gpus(lambda: "24576\n\n81920\n") == [24576, 81920]


def test_psutil_fields_are_populated() -> None:
    report = hwcheck.check_hardware(gpu_runner=lambda: "")

    assert report.cpu_count > 0
    assert report.ram_mb > 0
    assert report.disk_free_gb > 0


@pytest.mark.parametrize(
    "stdout,expected_count",
    [("49152\n", 1), ("49152\n49152\n", 2)],
)
def test_48gb_adds_lora(stdout: str, expected_count: int) -> None:
    report = hwcheck.check_hardware(gpu_runner=lambda: stdout)

    assert report.gpu_count == expected_count
    assert "LoRA (small models)" in report.supported_methods
    assert "30B" in report.recommended_model_sizes
    assert "Full fine-tune (mid-size)" not in report.supported_methods
