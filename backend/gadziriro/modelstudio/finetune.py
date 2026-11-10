"""Fine-tune templates and the (mock) training engine (FR-10, FR-09).

Phase 2 is mock-backed: no real GPU is touched. A "training run" records a
reproducible :class:`~gadziriro.modelstudio.base.TrainingSpec`, derives a
*deterministic* model artifact from that spec, registers it with lineage, and
wraps it in a tracker run. Because the artifact bytes are a pure function of
``(base_model, method, dataset_refs, hyperparams)``, re-running the same spec
reproduces the same registry checksum (FR-09) even though each run gets a fresh
``run_id``.

Two personas reach the *same* engine (BRD O3):

* an **analyst** fills in a form -> :func:`spec_from_form` -> ``TrainingSpec``;
* an **engineer** builds a ``TrainingSpec`` in code, seeding ``hyperparams``
  from the same method template.

Real fine-tuning is a target-hardware concern. The engineer-facing contract and
a ``@pytest.mark.target_hardware`` stub live in the acceptance tests: on the
Linux + NVIDIA box, :func:`run_finetune` would shell out to the real trainer;
off-target it simulates deterministically.
"""

from __future__ import annotations

from typing import Any

from ..core.canonical_json import canonical_bytes
from ..core.crypto import sha256_hex
from ..registry.base import LineageRecord
from ..registry.store import ObjectStoreRegistry
from ..tracking.store import ObjectStoreTracker
from .base import FineTuneMethod, TrainingResult, TrainingSpec

#: The default method on a single 24-48 GB GPU (BRD O3 / NFR-07).
DEFAULT_METHOD = FineTuneMethod.QLORA

#: Hyperparameters every method template shares (merged under method defaults).
_COMMON_DEFAULTS: dict[str, Any] = {
    "epochs": 3,
    "learning_rate": 2e-4,
    "batch_size": 8,
    "max_seq_len": 2048,
    "seed": 42,
}


def lora_template() -> dict[str, Any]:
    """Return sensible default hyperparameters for a LoRA fine-tune (FR-10)."""
    return {
        **_COMMON_DEFAULTS,
        "method": FineTuneMethod.LORA.value,
        "lora_r": 16,
        "lora_alpha": 32,
        "lora_dropout": 0.05,
        "target_modules": ["q_proj", "v_proj"],
    }


def qlora_template() -> dict[str, Any]:
    """Return sensible default hyperparameters for a QLoRA fine-tune (default)."""
    return {
        **_COMMON_DEFAULTS,
        "method": FineTuneMethod.QLORA.value,
        "lora_r": 16,
        "lora_alpha": 32,
        "lora_dropout": 0.05,
        "target_modules": ["q_proj", "v_proj"],
        "quantization": "nf4",
        "double_quant": True,
        "compute_dtype": "bfloat16",
    }


def full_template() -> dict[str, Any]:
    """Return sensible default hyperparameters for a full fine-tune (FR-10)."""
    return {
        **_COMMON_DEFAULTS,
        "method": FineTuneMethod.FULL.value,
        "learning_rate": 1e-5,
        "batch_size": 4,
        "gradient_checkpointing": True,
        "weight_decay": 0.0,
    }


#: Method -> template factory, so form and code paths share one source of truth.
_TEMPLATES = {
    FineTuneMethod.LORA: lora_template,
    FineTuneMethod.QLORA: qlora_template,
    FineTuneMethod.FULL: full_template,
}


def template_for(method: FineTuneMethod) -> dict[str, Any]:
    """Return the default hyperparameter template for ``method``."""
    return _TEMPLATES[method]()


def _coerce_method(value: Any) -> FineTuneMethod:
    """Coerce a form value (enum or string) into a :class:`FineTuneMethod`."""
    if isinstance(value, FineTuneMethod):
        return value
    return FineTuneMethod(str(value).lower())


def spec_from_form(form: dict[str, Any]) -> TrainingSpec:
    """Build a :class:`TrainingSpec` from an analyst's form (FR-10).

    The form is the no-code surface; it hits the *same* engine an engineer does.
    ``method`` defaults to QLoRA. The method's template seeds ``hyperparams``;
    any ``hyperparams`` supplied in the form override individual template keys,
    so the analyst only has to touch what they want to change.

    Required keys: ``base_model``, ``dataset_refs``, ``output_name``.
    Optional keys: ``method``, ``hyperparams``, ``hardware``, ``code_ref``.
    """
    base_model = form["base_model"]
    output_name = form["output_name"]
    dataset_refs = tuple(form["dataset_refs"])

    method = _coerce_method(form.get("method", DEFAULT_METHOD))
    hyperparams = {**template_for(method), **dict(form.get("hyperparams", {}))}

    return TrainingSpec(
        base_model=base_model,
        method=method,
        dataset_refs=dataset_refs,
        output_name=output_name,
        hyperparams=hyperparams,
        hardware=form.get("hardware", "mock"),
        code_ref=form.get("code_ref", ""),
    )


def _artifact_manifest(spec: TrainingSpec) -> dict[str, Any]:
    """Return the canonical, reproducible manifest for a spec's artifact.

    Deliberately excludes anything run-specific (``run_id``, timestamps) so the
    manifest — and therefore the artifact bytes and registry checksum — is a pure
    function of the spec (FR-09).
    """
    return {
        "artifact_type": "gadziriro.finetune.v1",
        "base_model": spec.base_model,
        "method": spec.method.value,
        "dataset_refs": list(spec.dataset_refs),
        "hyperparams": spec.hyperparams,
    }


def _artifact_bytes(spec: TrainingSpec) -> bytes:
    """Derive deterministic model-artifact bytes from ``spec`` (FR-09).

    The "weights" are simulated: a canonical JSON manifest plus a fingerprint of
    that manifest. Identical specs yield byte-identical artifacts (hence an
    identical registry checksum); any change to the inputs changes the bytes.
    """
    manifest = _artifact_manifest(spec)
    fingerprint = sha256_hex(canonical_bytes(manifest))
    artifact = {**manifest, "weights_fingerprint": fingerprint}
    return canonical_bytes(artifact)


def _mock_metrics(spec: TrainingSpec) -> dict[str, Any]:
    """Compute deterministic mock training metrics from ``spec`` (no GPU).

    Derived from the artifact fingerprint so the same spec always reports the
    same numbers — a stand-in for real loss/accuracy curves on target hardware.
    """
    fingerprint = sha256_hex(_artifact_bytes(spec))
    # Map the first bytes of the digest into stable, plausible metric ranges.
    train_loss = round(0.05 + (int(fingerprint[:4], 16) / 0xFFFF) * 0.95, 4)
    eval_accuracy = round(0.70 + (int(fingerprint[4:8], 16) / 0xFFFF) * 0.29, 4)
    return {
        "train_loss": train_loss,
        "eval_accuracy": eval_accuracy,
        "steps": int(spec.hyperparams.get("epochs", 1)) * 100,
    }


def run_finetune(
    registry: ObjectStoreRegistry,
    tracker: ObjectStoreTracker,
    spec: TrainingSpec,
) -> TrainingResult:
    """Run a (mock) fine-tune: track, register with lineage, return a result.

    Steps (FR-10, FR-09, FR-07):

    1. open a tracker run capturing ``hyperparams``, ``dataset_refs``,
       ``code_ref`` and ``hardware`` (the reproducibility context);
    2. derive deterministic artifact bytes from the spec;
    3. register the artifact as the next version of ``spec.output_name`` with a
       :class:`LineageRecord` linking the datasets, code, params, hardware and
       the run that produced it;
    4. log a mock metric and close the run;
    5. return a :class:`TrainingResult` pointing at the registered model.

    On the Linux + NVIDIA target box this is where the real trainer would run;
    off-target the artifact and metrics are simulated deterministically.
    """
    run = tracker.start_run(
        params=dict(spec.hyperparams),
        dataset_refs=spec.dataset_refs,
        code_ref=spec.code_ref,
        hardware=spec.hardware,
    )

    data = _artifact_bytes(spec)
    lineage = LineageRecord(
        dataset_refs=spec.dataset_refs,
        code_ref=spec.code_ref,
        params=spec.hyperparams,
        hardware=spec.hardware,
        run_id=run.run_id,
    )
    model = registry.add_model(spec.output_name, data, lineage=lineage)

    metrics = _mock_metrics(spec)
    for key, value in metrics.items():
        tracker.log_metric(run.run_id, key, value)
    tracker.end_run(run.run_id)

    return TrainingResult(
        model_ref=model.ref,
        run_id=run.run_id,
        method=spec.method,
        base_model=spec.base_model,
        metrics=metrics,
    )
