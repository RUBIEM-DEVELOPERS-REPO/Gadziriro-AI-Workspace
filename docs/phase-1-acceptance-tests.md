# Phase 1 acceptance tests

Phase 1 "Pilot foundations" (BRD §12). Exit: SSO, registry with lineage, run
tracking, quotas, local mirror, backup/restore, monitoring — pilot-ready for one
SME. All tests run off-target against the mock runtime + local object store; the
Phase 0 `target_hardware` tests still gate the GPU/container claims.

| Req | Capability | Test(s) | Status |
| --- | --- | --- | --- |
| FR-04 | Idle sessions release their GPU | `tests/unit/test_idle_reclaim.py` | PASS |
| FR-05 | Background jobs queued + per-user/project quotas | `test_scheduler.py`, `acceptance/test_fr05_quotas.py` | PASS |
| FR-34 | Repeatable pinned environments from the mirror | `test_environments.py` | PASS |
| FR-06 | Dataset/model versioning + rollback | `test_registry.py`, `acceptance/test_fr06_fr07_versioning_lineage.py` | PASS |
| FR-07 | Lineage: model → datasets/code/params/hardware | same as FR-06 | PASS |
| FR-08 | Dataset sensitivity labels | `test_governance_ingest.py`, `acceptance/test_fr08_fr33_labels_ingest.py` | PASS |
| FR-09 | Reproducible run tracking | `test_tracking.py` | PASS |
| FR-33 | Ingestion only from approved sources, labelled | `acceptance/test_fr08_fr33_labels_ingest.py` | PASS |
| FR-16b | SSO (OIDC auth-code) | `test_sso.py` | PASS |
| FR-17 | MFA (TOTP) + short-session auto-logout | `test_mfa.py` | PASS |
| FR-18a | Per-project RBAC | `test_rbac.py` | PASS |
| FR-41 | Customer-held keys + rotation | `test_keys.py`, `acceptance/test_fr41_key_rotation.py` | PASS |
| FR-21 | Export approval when policy requires, logged | `acceptance/test_fr21_export_approval.py` | PASS — exit |
| FR-22 | Per-dataset retention + scheduled deletion w/ proof | `test_retention.py`, `acceptance/test_fr22_retention.py` | PASS |
| FR-23 | Find models built from a subject's data + flag | `test_dsar.py` | PASS |
| FR-28 | Backup + restore of workspace state | `test_backup.py`, `acceptance/test_fr28_backup_restore.py` | PASS |
| FR-29 | Local approved-only mirror, no network fallback | `test_mirror.py`, `acceptance/test_fr29_mirror_offline.py` | PASS |
| FR-31 | Offline licence-key validation | `test_licence.py` | PASS |
| FR-39 | Metrics/logs/traces export (Prometheus + SIEM seam) | `test_metrics.py` | PASS |
| FR-42 | Backups auto test-restored + integrity-checked | `test_backup.py`, `acceptance/test_fr28_backup_restore.py` | PASS |

All surfaced over the gateway API (`GET /metrics`, `/api/datasets`, `/api/models`,
`/api/jobs`, `/api/mirror`, `/api/backups`, `/api/governance/*`, `/api/exports/*`,
`/api/mfa/*`) and in the React UI (Registry, Jobs, Governance, Ops, Exports tabs +
MFA enrolment) — see `tests/integration/test_gateway_phase1.py`.

## Phase 1 status (2026-10-14)
Backend suite: **203 passed, 2 skipped** (the 2 skips are the Phase 0
`target_hardware` stubs). ruff/black/isort clean. Frontend typecheck + build clean.
38 app routes; `docs/openapi.json` regenerated.

Still to close on the Linux+NVIDIA pilot server (carried from Phase 0):
`pytest -q -m target_hardware` for kernel-level no-egress, gVisor isolation, and
real `nvidia-smi` sizing. Phase 1 adds no new target-hardware-only gates.
