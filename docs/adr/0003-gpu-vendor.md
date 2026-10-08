# ADR-0003: GPU vendor support

- **Status:** Accepted for Phase 0 (revisit Phase 3)
- **Owner:** Architect
- **Phase:** 0

## Decision
**NVIDIA only** for v1 (CUDA 12+). Hardware detection uses `nvidia-smi`. AMD/ROCm is
assessed later (NFR-14). The installer and runtime adapter degrade gracefully to CPU-only
(mock allocation) when no NVIDIA GPU is present, so development and CI work anywhere.

## Consequences
`backend/gadziriro/installer/hwcheck.py` targets `nvidia-smi`; non-NVIDIA hosts get a
warning and CPU-only capability, not a hard failure.
