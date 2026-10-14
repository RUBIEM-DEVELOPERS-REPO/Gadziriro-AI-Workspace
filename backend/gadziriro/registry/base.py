"""Registry & lineage contract.

Datasets and models are versioned (monotonic ints, rollback = pin an older
version). Every model version carries a :class:`LineageRecord` naming the exact
datasets, code, params and hardware that produced it — this is what makes DSAR
(FR-23/FR-45) and reproducibility (FR-09) possible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from ..governance.labels import SensitivityLabel


@dataclass(frozen=True)
class DatasetVersion:
    name: str
    version: int
    sensitivity: SensitivityLabel
    source: str  # approved source the data came from (FR-33)
    checksum: str  # content hash of the stored bytes
    created_at: str  # ISO-8601 UTC
    subjects: tuple[str, ...] = ()  # data-subject ids present (for DSAR/FR-23)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def ref(self) -> str:
        return f"{self.name}@{self.version}"


@dataclass(frozen=True)
class LineageRecord:
    """What produced a model version."""

    dataset_refs: tuple[str, ...]  # e.g. ("patients@3", "notes@1")
    code_ref: str = ""  # commit / script id
    params: dict[str, Any] = field(default_factory=dict)
    hardware: str = ""  # e.g. "1xA100-80GB"
    run_id: str = ""  # tracker run that produced it (FR-09)


@dataclass(frozen=True)
class ModelVersion:
    name: str
    version: int
    checksum: str
    created_at: str
    lineage: LineageRecord
    sensitivity: SensitivityLabel = SensitivityLabel.INTERNAL
    flagged: bool = False  # set by DSAR when a subject's data is erased
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def ref(self) -> str:
        return f"{self.name}@{self.version}"


class RegistryStore(Protocol):
    """Versioned storage for datasets and models plus lineage queries."""

    # datasets
    def add_dataset(
        self,
        name: str,
        data: bytes,
        *,
        sensitivity: SensitivityLabel,
        source: str,
        subjects: tuple[str, ...] = (),
    ) -> DatasetVersion: ...

    def get_dataset(
        self, name: str, version: Optional[int] = None
    ) -> DatasetVersion: ...

    def list_dataset_versions(self, name: str) -> list[DatasetVersion]: ...

    # models
    def add_model(
        self,
        name: str,
        data: bytes,
        *,
        lineage: LineageRecord,
        sensitivity: SensitivityLabel = SensitivityLabel.INTERNAL,
    ) -> ModelVersion: ...

    def get_model(self, name: str, version: Optional[int] = None) -> ModelVersion: ...

    def list_model_versions(self, name: str) -> list[ModelVersion]: ...

    # lineage / DSAR
    def models_from_dataset(self, dataset_ref: str) -> list[ModelVersion]: ...

    def models_for_subject(self, subject_id: str) -> list[ModelVersion]: ...

    def flag_model(self, name: str, version: int, reason: str) -> ModelVersion: ...
