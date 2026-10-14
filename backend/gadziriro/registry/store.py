"""Object-store-backed versioned registry with lineage (FR-06, FR-07).

Datasets and model artifacts are stored as opaque byte blobs alongside a small
JSON metadata document in the shared :class:`~gadziriro.core.objectstore.ObjectStore`.
Versions are monotonic integers starting at ``1`` (the next version is one past
the current maximum), so pinning an older explicit version is a rollback (FR-06).

Key layout (POSIX forward-slash keys, relative to the store root)::

    datasets/<name>/<version>/blob        # raw dataset bytes
    datasets/<name>/<version>/meta.json   # DatasetVersion metadata
    models/<name>/<version>/blob          # raw model bytes
    models/<name>/<version>/meta.json     # ModelVersion metadata (incl. lineage)

Every :class:`~gadziriro.registry.base.ModelVersion` carries the
:class:`~gadziriro.registry.base.LineageRecord` that produced it. Lineage is the
source of truth for the DSAR / reproducibility queries (FR-07, FR-23, FR-09):
``models_from_dataset`` and ``models_for_subject`` are derived by scanning the
persisted model metadata rather than kept in a separate index that could drift.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from ..core.crypto import sha256_hex
from ..core.errors import NotFound
from ..core.objectstore import ObjectStore
from ..governance.labels import SensitivityLabel
from .base import DatasetVersion, LineageRecord, ModelVersion

_DATASETS = "datasets"
_MODELS = "models"


def _now_iso() -> str:
    """Return the current time as an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _blob_key(kind: str, name: str, version: int) -> str:
    """Return the object-store key for a blob of ``kind`` at ``name``/``version``."""
    return f"{kind}/{name}/{version}/blob"


def _meta_key(kind: str, name: str, version: int) -> str:
    """Return the object-store key for the metadata of ``kind``/``name``/``version``."""
    return f"{kind}/{name}/{version}/meta.json"


class ObjectStoreRegistry:
    """Versioned dataset & model registry backed by an :class:`ObjectStore`.

    Implements the :class:`~gadziriro.registry.base.RegistryStore` protocol.
    All persistence goes through the injected object store, so the same code runs
    on local disk today and on an S3-compatible backend later (Phase 3).
    """

    def __init__(self, store: ObjectStore) -> None:
        self._store = store

    # ------------------------------------------------------------------ #
    # version discovery
    # ------------------------------------------------------------------ #
    def _versions(self, kind: str, name: str) -> list[int]:
        """Return the sorted existing integer versions for ``kind``/``name``."""
        prefix = f"{kind}/{name}/"
        versions: set[int] = set()
        for key in self._store.list(prefix):
            rest = key[len(prefix) :]
            head = rest.split("/", 1)[0]
            try:
                versions.add(int(head))
            except ValueError:
                continue
        return sorted(versions)

    def _names(self, kind: str) -> list[str]:
        """Return the sorted distinct object names registered under ``kind``."""
        prefix = f"{kind}/"
        names: set[str] = set()
        for key in self._store.list(prefix):
            rest = key[len(prefix) :]
            parts = rest.split("/")
            if len(parts) >= 2:
                names.add(parts[0])
        return sorted(names)

    def _next_version(self, kind: str, name: str) -> int:
        """Return the next monotonic version (max existing + 1, or 1)."""
        versions = self._versions(kind, name)
        return (versions[-1] + 1) if versions else 1

    def _resolve_version(self, kind: str, name: str, version: Optional[int]) -> int:
        """Resolve ``version`` (``None`` = latest) or raise :class:`NotFound`."""
        versions = self._versions(kind, name)
        if not versions:
            raise NotFound(f"{kind} not found: {name}")
        if version is None:
            return versions[-1]
        if version not in versions:
            raise NotFound(f"{kind} version not found: {name}@{version}")
        return version

    # ------------------------------------------------------------------ #
    # (de)serialisation
    # ------------------------------------------------------------------ #
    def _write_meta(self, key: str, payload: dict[str, Any]) -> None:
        """Persist ``payload`` as JSON bytes under ``key``."""
        self._store.put(key, json.dumps(payload, sort_keys=True).encode("utf-8"))

    def _read_meta(self, key: str) -> dict[str, Any]:
        """Load and decode the JSON metadata stored at ``key``."""
        return json.loads(self._store.get(key).decode("utf-8"))

    @staticmethod
    def _dataset_from_meta(meta: dict[str, Any]) -> DatasetVersion:
        """Rebuild a :class:`DatasetVersion` from its stored metadata."""
        return DatasetVersion(
            name=meta["name"],
            version=meta["version"],
            sensitivity=SensitivityLabel(meta["sensitivity"]),
            source=meta["source"],
            checksum=meta["checksum"],
            created_at=meta["created_at"],
            subjects=tuple(meta.get("subjects", ())),
            meta=dict(meta.get("meta", {})),
        )

    @staticmethod
    def _model_from_meta(meta: dict[str, Any]) -> ModelVersion:
        """Rebuild a :class:`ModelVersion` (with lineage) from stored metadata."""
        lin = meta["lineage"]
        lineage = LineageRecord(
            dataset_refs=tuple(lin.get("dataset_refs", ())),
            code_ref=lin.get("code_ref", ""),
            params=dict(lin.get("params", {})),
            hardware=lin.get("hardware", ""),
            run_id=lin.get("run_id", ""),
        )
        return ModelVersion(
            name=meta["name"],
            version=meta["version"],
            checksum=meta["checksum"],
            created_at=meta["created_at"],
            lineage=lineage,
            sensitivity=SensitivityLabel(meta["sensitivity"]),
            flagged=meta.get("flagged", False),
            meta=dict(meta.get("meta", {})),
        )

    @staticmethod
    def _model_to_meta(model: ModelVersion) -> dict[str, Any]:
        """Serialise a :class:`ModelVersion` to a JSON-ready dict."""
        return {
            "name": model.name,
            "version": model.version,
            "checksum": model.checksum,
            "created_at": model.created_at,
            "lineage": {
                "dataset_refs": list(model.lineage.dataset_refs),
                "code_ref": model.lineage.code_ref,
                "params": model.lineage.params,
                "hardware": model.lineage.hardware,
                "run_id": model.lineage.run_id,
            },
            "sensitivity": model.sensitivity.value,
            "flagged": model.flagged,
            "meta": model.meta,
        }

    # ------------------------------------------------------------------ #
    # datasets
    # ------------------------------------------------------------------ #
    def add_dataset(
        self,
        name: str,
        data: bytes,
        *,
        sensitivity: SensitivityLabel,
        source: str,
        subjects: tuple[str, ...] = (),
    ) -> DatasetVersion:
        """Store ``data`` as the next version of dataset ``name`` (FR-06)."""
        version = self._next_version(_DATASETS, name)
        dv = DatasetVersion(
            name=name,
            version=version,
            sensitivity=sensitivity,
            source=source,
            checksum=sha256_hex(data),
            created_at=_now_iso(),
            subjects=tuple(subjects),
        )
        self._store.put(_blob_key(_DATASETS, name, version), data)
        self._write_meta(
            _meta_key(_DATASETS, name, version),
            {
                "name": dv.name,
                "version": dv.version,
                "sensitivity": dv.sensitivity.value,
                "source": dv.source,
                "checksum": dv.checksum,
                "created_at": dv.created_at,
                "subjects": list(dv.subjects),
                "meta": dv.meta,
            },
        )
        return dv

    def get_dataset(self, name: str, version: Optional[int] = None) -> DatasetVersion:
        """Return dataset ``name`` at ``version`` (``None`` = latest; rollback)."""
        resolved = self._resolve_version(_DATASETS, name, version)
        return self._dataset_from_meta(
            self._read_meta(_meta_key(_DATASETS, name, resolved))
        )

    def list_dataset_versions(self, name: str) -> list[DatasetVersion]:
        """Return every stored version of dataset ``name`` (ascending)."""
        return [
            self._dataset_from_meta(self._read_meta(_meta_key(_DATASETS, name, v)))
            for v in self._versions(_DATASETS, name)
        ]

    # ------------------------------------------------------------------ #
    # models
    # ------------------------------------------------------------------ #
    def add_model(
        self,
        name: str,
        data: bytes,
        *,
        lineage: LineageRecord,
        sensitivity: SensitivityLabel = SensitivityLabel.INTERNAL,
    ) -> ModelVersion:
        """Store ``data`` as the next version of model ``name`` with lineage (FR-07)."""
        version = self._next_version(_MODELS, name)
        mv = ModelVersion(
            name=name,
            version=version,
            checksum=sha256_hex(data),
            created_at=_now_iso(),
            lineage=lineage,
            sensitivity=sensitivity,
        )
        self._store.put(_blob_key(_MODELS, name, version), data)
        self._write_meta(_meta_key(_MODELS, name, version), self._model_to_meta(mv))
        return mv

    def get_model(self, name: str, version: Optional[int] = None) -> ModelVersion:
        """Return model ``name`` at ``version`` (``None`` = latest; FR-06 rollback)."""
        resolved = self._resolve_version(_MODELS, name, version)
        return self._model_from_meta(
            self._read_meta(_meta_key(_MODELS, name, resolved))
        )

    def list_model_versions(self, name: str) -> list[ModelVersion]:
        """Return every stored version of model ``name`` (ascending)."""
        return [
            self._model_from_meta(self._read_meta(_meta_key(_MODELS, name, v)))
            for v in self._versions(_MODELS, name)
        ]

    def _all_models(self) -> list[ModelVersion]:
        """Return every stored model version across all names (for lineage scans)."""
        out: list[ModelVersion] = []
        for name in self._names(_MODELS):
            out.extend(self.list_model_versions(name))
        return out

    # ------------------------------------------------------------------ #
    # lineage / DSAR (FR-07, FR-23)
    # ------------------------------------------------------------------ #
    def models_from_dataset(self, dataset_ref: str) -> list[ModelVersion]:
        """Return every model version whose lineage references ``dataset_ref``.

        ``dataset_ref`` is a pinned reference like ``"patients@3"``.
        """
        return [m for m in self._all_models() if dataset_ref in m.lineage.dataset_refs]

    def models_for_subject(self, subject_id: str) -> list[ModelVersion]:
        """Return every model built from any dataset containing ``subject_id``.

        Resolves each model's ``lineage.dataset_refs`` back to the exact
        :class:`DatasetVersion` and checks its ``subjects`` — the query path a
        DSAR erasure (FR-23) walks to find models to flag.
        """
        out: list[ModelVersion] = []
        for model in self._all_models():
            if self._lineage_touches_subject(model.lineage, subject_id):
                out.append(model)
        return out

    def _lineage_touches_subject(self, lineage: LineageRecord, subject_id: str) -> bool:
        """Return True if any dataset in ``lineage`` lists ``subject_id``."""
        for ref in lineage.dataset_refs:
            name, _, version = ref.rpartition("@")
            if not name or not version:
                continue
            try:
                dv = self.get_dataset(name, int(version))
            except (NotFound, ValueError):
                continue
            if subject_id in dv.subjects:
                return True
        return False

    def flag_model(self, name: str, version: int, reason: str) -> ModelVersion:
        """Flag model ``name``@``version`` (DSAR erasure, FR-23) and persist it.

        Sets ``flagged=True``, records the ``reason`` in metadata, and returns
        the updated :class:`ModelVersion`. Raises :class:`NotFound` if missing.
        """
        resolved = self._resolve_version(_MODELS, name, version)
        current = self._model_from_meta(
            self._read_meta(_meta_key(_MODELS, name, resolved))
        )
        new_meta = dict(current.meta)
        new_meta["flag_reason"] = reason
        flagged = ModelVersion(
            name=current.name,
            version=current.version,
            checksum=current.checksum,
            created_at=current.created_at,
            lineage=current.lineage,
            sensitivity=current.sensitivity,
            flagged=True,
            meta=new_meta,
        )
        self._write_meta(
            _meta_key(_MODELS, name, resolved), self._model_to_meta(flagged)
        )
        return flagged
