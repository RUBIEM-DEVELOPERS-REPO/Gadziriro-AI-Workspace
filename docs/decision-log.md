# Decision log

Chronological record of decisions (section 13 governance). ADRs hold the detail.

| Date | Decision | Status | Ref |
| --- | --- | --- | --- |
| 2026-10-07 | Start Phase 0: single-node prototype proving the privacy model | Accepted | BRD §12, §15 |
| 2026-10-07 | Stack: Python/FastAPI control plane + React/TS UI | Accepted | ADR-0001 |
| 2026-10-07 | GPU vendor: NVIDIA only for v1 | Accepted | ADR-0003 |
| 2026-10-07 | OS: Ubuntu 22.04/24.04 Full, RHEL 9 best-effort | Accepted | ADR-0004 |
| 2026-10-07 | SQLite for relational state; JSONL hash chain for audit | Accepted | ADR-0005 |
| TODO | Licensing model + pricing | BLOCKED (before Phase 1) | ADR-0002 |
| TODO | ZW DPA specifics confirmed by local counsel | Open (before any compliance claim) | BRD §9 |
| TODO | Vendor SOC 2 timing | Open (Phase 3) | BRD §14 |
| TODO | Plug-in sandboxing/signing | Open (Phase 4) | BRD §14 |
| 2026-10-14 | Phase 1 pilot foundations delivered (registry/lineage, SSO/MFA/RBAC, scheduler/quotas, mirror, backup/restore, observability, governance, export approval) | Done | PR (stacked on Phase 0) |
| 2026-10-14 | Phase 2 Model Studio delivered (fine-tune/eval/diff/weight-tools/export, model cards, licence+export checks, policy packs, incident response, DSAR export/erase, support bundles, API/CLI+UI) | Done | PR stacked |
