# Phase 4 acceptance tests

Phase 4 "Market launch" (BRD §12). Exit: plug-in kit, evidence exports, vendor SOC 2.
Code deliverables are tested below; vendor SOC 2 and the external pen-test are
human-run engagements that consume the evidence surfaces this phase ships.

| Req | Capability | Test(s) | Status |
| --- | --- | --- | --- |
| FR-32 | Signed, sandboxed plug-in kit (vision/speech/tabular) | `test_plugins.py`, `acceptance/test_fr32_plugins.py`, `integration/test_gateway_phase4.py` | PASS |
| FR-26 | Auditor evidence-pack export | `test_evidence.py`, `acceptance/test_fr26_evidence.py`, `integration/test_gateway_phase4.py` | PASS |
| NFR-18 | SBOM (software bill of materials) | `test_sbom.py` | PASS |
| FR-44 | English / Shona / Ndebele i18n | `frontend/src/i18n/` + language switcher (nav + common actions translated; English fallback elsewhere, `// TODO native review`) | PASS (build) |
| SOC 2 | Vendor SOC 2 evidence surfaces | evidence pack bundles audit-integrity proof + policy packs + egress report + ROPA + SBOM (human audit runs on top) | SURFACES READY |

Surfaced over the gateway (80 routes; `/api/plugins*`, `/api/evidence*`) and the
React UI (Plugins, Evidence admin tabs; language switcher).

## Phase 4 status (2026-11-12)
Backend suite: **404 passed, 4 skipped** (`target_hardware`). ruff/black/isort clean.
Frontend typecheck + build clean. OpenAPI regenerated (68 paths).

## Product-complete
Phases 0–4 of the BRD are implemented and tested off-target. The standing
target-hardware gate (`pytest -q -m target_hardware`) — kernel no-egress, gVisor,
real `nvidia-smi` sizing, a real QLoRA fine-tune, a real K8s/Slurm cluster — plus the
external penetration test and vendor SOC 2 audit are the remaining human/hardware
steps before a production pilot sign-off.
