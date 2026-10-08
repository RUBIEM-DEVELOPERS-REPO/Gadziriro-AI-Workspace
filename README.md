# Gadziriro AI Workspace

Self-hosted, single-tenant platform that lets regulated organisations build, fine-tune,
evaluate and export their own text AI models **without sensitive data leaving their
premises**. Zero egress by default; every approved transfer is logged and auditable.

> **Status: Phase 0 — single-node prototype.** This phase proves the privacy model. See the
> approved [BRD & Technical Proposal](docs/BRD-and-technical-proposal-v1.0.md) for the full
> product, [`docs/phase-0-acceptance-tests.md`](docs/phase-0-acceptance-tests.md) for the
> exit gate, and [`docs/adr/`](docs/adr/) for key decisions.

## Phase 0 scope

| Req | Capability |
| --- | --- |
| FR-01 / FR-02 | Browser notebooks; existing `.ipynb` open unchanged (Jupyter kernel protocol) |
| FR-03 | Each session runs in its own sealed container with an assigned GPU |
| FR-16a | Local accounts (argon2) |
| FR-19 | Tamper-evident, hash-chained audit log + verifier |
| FR-20 | No outbound internet from user code by default |
| FR-27 | Installer checks hardware and reports supported model sizes/methods |

**Exit gate:** privacy model proven · no-egress test passed · audit hash chain verified.

## Architecture (section 16)

The control plane reaches hardware **only** through the runtime adapter's five commands
(`start_kernel`, `run_job`, `allocate_gpu`, `stop`, `metrics`). The single-node backend
ships first; Kubernetes and Slurm backends plug in later (Phase 3) with no change to screens
or policy. A `mock` backend makes every GPU/container path testable off-target.

```
backend/gadziriro/
  core/       shared: canonical JSON, config, logging, errors, crypto
  audit/      hash-chained JSONL log + verify()                (FR-19)
  auth/       local accounts (argon2), RBAC-per-project         (FR-16a)
  gateway/    FastAPI front door: routes, sessions, rate limit, audit
  sessions/   Jupyter-kernel session & kernel manager           (FR-01/02/03)
  runtime/    RuntimeAdapter ABC + single-node Docker + mock
  compute/    sealed rootless containers, --network none        (FR-20, NFR-05)
  policy/     egress policy (default-deny) + gate
  installer/  hardware check + sizing                           (FR-27)
  cli/        `gadziriro` CLI (audit verify, hw-check, serve)
frontend/     React + TS (Vite): login, notebook shell, admin
```

## Quick start (dev — no GPU/Docker required)

Toolchain: Python 3.11 (`uv`/`py`), Node 20+. On this org's Windows boxes `uv`'s cache
defaults to a missing drive — set `UV_CACHE_DIR` to a local path first.

```bash
# Backend
cd backend
uv venv --python 3.11
uv pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest -q        # Linux/macOS: .venv/bin/python

# Frontend
cd ../frontend
npm ci
npm run dev
```

Everything runs against the `mock` runtime backend. Container/GPU/gVisor acceptance tests
are tagged `target_hardware` and run on the Linux+NVIDIA reference server:
`pytest -q -m target_hardware`.

## Privacy defaults

- `GADZIRIRO_ALLOW_EGRESS=false` — user code has no network unless an admin opens a path (FR-20).
- `GADZIRIRO_TELEMETRY_ENABLED=false` — the product never phones home (NFR-02).

## Compliance note

Controls **support** HIPAA, GDPR, SOC 2 and Zimbabwe's Cyber and Data Protection Act. We say
"supports", never "certified", until an independent audit confirms it, and every compliance
claim passes a legal review gate (BRD §9). This repository is an engineering artifact, not
legal advice.
