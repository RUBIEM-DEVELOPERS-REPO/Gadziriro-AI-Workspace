# ADR-0001: Technology stack

- **Status:** Accepted
- **Date:** 2026-10-07
- **Phase:** 0

## Context
Phase 0 needs a stack that is privacy-first, runs on a single Linux+NVIDIA box, matches
RUBIEM conventions, and scales to the section-16 architecture without rewrites.

## Decision
- **Backend / control plane:** Python 3.11 + FastAPI (gateway), SQLAlchemy 2.0 + Alembic,
  Pydantic v2. Deps in `backend/requirements.txt`; tool config in `pyproject.toml`
  (RUBIEM convention).
- **Notebook engine:** Jupyter kernel protocol (`jupyter-client`), native `.ipynb` (FR-01/02).
- **Runtime isolation:** rootless Podman/Docker + gVisor on target; a `mock` backend for
  dev/CI where no GPU/engine exists.
- **Frontend:** React + TypeScript (Vite). CI uses npm (matches RUBIEM frontend CI).
- **Audit:** append-only hash-chained JSONL (not SQL) — see ADR-0005.

## Consequences
GPU/container/gVisor paths are verify-on-target-only; the mock backend keeps the suite
runnable off-target. The runtime adapter ABC (`backend/gadziriro/runtime/base.py`) is the
Phase-3 K8s/Slurm extension point and must stay stable.
