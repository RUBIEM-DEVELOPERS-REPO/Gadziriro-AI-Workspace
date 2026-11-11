# Phase 3 acceptance tests

Phase 3 "Enterprise scale" (BRD §12). Exit: online assist, signed updates,
multi-node and per-dataset rules working; enterprise-ready and scalable. Tests run
off-target against the mock runtime, simulated clusters, and the local object store;
real cluster/GPU verification stays on the `target_hardware` gate.

| Req | Capability | Test(s) | Status |
| --- | --- | --- | --- |
| NFR-08 | Same control-plane surface on 1 GPU / K8s / Slurm | `test_k8s_adapter.py`, `test_slurm_adapter.py`, `acceptance/test_nfr08_multinode.py` | PASS |
| FR-30 | Signed updates (online + offline) + one-step rollback | `test_update_signing.py`, `test_update_apply.py`, `acceptance/test_fr30_signed_updates.py` | PASS |
| FR-18b | Optional per-dataset access rules | `test_dataset_acl.py`, `acceptance/test_fr18b_dataset_acl.py` | PASS |
| FR-25 | "What left this machine" egress report | `test_egress_report.py`, `acceptance/test_fr25_egress_report.py` | PASS |
| FR-37 | Bias/fairness + red-team | `test_bias.py`, `test_redteam.py`, `acceptance/test_fr37_bias_redteam.py` | PASS |
| FR-46 | ROPA export | `test_ropa.py`, `acceptance/test_fr46_ropa.py` | PASS |
| FR-47 | DPIA template + workflow | `test_dpia.py`, `acceptance/test_fr47_dpia.py` | PASS |
| FR-43 | WCAG 2.1 AA accessibility | `frontend/ACCESSIBILITY.md` + manual (tablist semantics, labels, focus, contrast, lang, aria-live) | PASS (build); screen-reader pass pending |
| §21 | External pen-test readiness | `backend/security/pentest/` (scope README + loopback smoke 4/4) | SCAFFOLD |

Surfaced over the gateway (74 routes; `/api/updates/*`, `/api/datasets/{name}/acl`,
`/api/reports/egress`, `/api/safety/*`, `/api/compliance/ropa|dpia`), the `gadziriro`
CLI (`egress-report`, `ropa`), and the React UI (Updates, Enterprise, Safety tabs +
ROPA/DPIA in Compliance).

## Phase 3 status (2026-11-11)
Backend suite: **382 passed, 4 skipped** (`target_hardware`: kernel no-egress,
gVisor, real `nvidia-smi` sizing, real QLoRA, real multi-node cluster). ruff/black/
isort clean. Frontend typecheck + build clean. OpenAPI regenerated (62 paths).

Process items (not code): the external penetration test (BRD §21) and vendor SOC 2
are run by people — the repo ships the harness scaffold + evidence surfaces (egress
report, audit chain, ROPA/DPIA) those engagements consume.
