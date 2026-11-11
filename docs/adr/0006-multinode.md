# ADR-0006: Multi-node runtime (Kubernetes / Slurm)

- **Status:** Accepted for Phase 3
- **Owner:** Architect
- **Phase:** 3

## Decision
Scale beyond one box by adding Kubernetes and Slurm backends that implement the
same `RuntimeAdapter` ABC (`runtime/base.py`) behind `get_runtime_adapter`
(`runtime/factory.py`). Screens and the policy layer do NOT change (NFR-08). The
single-node and mock backends remain the defaults; K8s/Slurm are selected via
`GADZIRIRO_RUNTIME_BACKEND`. On this dev box they are exercised through simulated
clients (no real cluster); real cluster runs are target-hardware.

## Consequences
Multi-node recovery targets (RTO/RPO) are defined here per NFR-15. The adapter's
5-method surface stays stable; cluster specifics live inside each backend.
