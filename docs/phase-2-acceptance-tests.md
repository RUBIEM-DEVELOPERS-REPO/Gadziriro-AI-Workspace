# Phase 2 acceptance tests

Phase 2 "Model Studio" (BRD §12, §19). Exit: fine-tune templates, evaluation, model
diff and policy packs working. All tests run off-target against the mock runtime +
local object store; real fine-tuning is a Phase-0 `target_hardware` concern.

| Req | Capability | Test(s) | Status |
| --- | --- | --- | --- |
| FR-10 | Fine-tune templates LoRA/QLoRA/full (form or code) | `test_finetune.py`, `acceptance/test_fr10_finetune.py` | PASS |
| FR-11 | Evaluate vs a question set + side-by-side compare | `test_eval_harness.py`, `acceptance/test_fr11_eval_compare.py` | PASS |
| FR-12 | Merge / quantize (GPTQ,AWQ,GGUF) / prune / inspect | `test_weighttools.py`, `acceptance/test_fr12_weight_tools.py` | PASS |
| FR-13 | Model diff (score delta, sample answers, weights) | `test_model_diff.py`, `acceptance/test_fr13_model_diff.py` | PASS |
| FR-15 | Export safetensors/GGUF/ONNX → vLLM/TGI handoff | `test_export.py`, `acceptance/test_fr15_export.py` | PASS |
| FR-36 | Model cards (licence, data, scores, limits) | `test_model_cards.py`, `acceptance/test_fr36_model_cards.py` | PASS |
| FR-48 | Licence + export-control checks before use/export | `test_licence_checks.py`, `acceptance/test_fr48_licence_checks.py` | PASS |
| FR-24 | Policy packs hipaa/gdpr/soc2/zw-dpa, strictest-wins | `test_policy_packs.py`, `acceptance/test_fr24_policy_packs.py` | PASS |
| FR-38 | Incident response + breach report from audit | `test_incident.py`, `acceptance/test_fr38_incident.py` | PASS |
| FR-45 | DSAR export + erase of a subject's data | `test_dsar_export.py`, `acceptance/test_fr45_dsar_export.py` | PASS |
| FR-40 | PII-stripped support bundles | `test_support_bundle.py`, `acceptance/test_fr40_support_bundle.py` | PASS |
| FR-35 | API + CLI for Model Studio | `integration/test_gateway_phase2.py`, `acceptance/test_fr35_api_cli.py` | PASS |

Surfaced over the gateway (60 routes; `/api/modelstudio/*`, `/api/evaluation/*`,
`/api/weighttools/*`, `/api/modelcards/*`, `/api/licensing/*`, `/api/policy/packs*`,
`/api/incidents*`, `/api/dsar/*`, `/api/support/bundle`), the `gadziriro` CLI
(`model-card`, `policy effective`, `incidents`), and the React UI (Model Studio,
Evaluate, Weight Tools, Model Card, Compliance tabs).

## Phase 2 status (2026-10-14)
Backend suite: **323 passed, 3 skipped** (the 3 skips are `target_hardware` stubs —
Phase 0's two plus a real-fine-tune stub). ruff/black/isort clean. Frontend typecheck
+ build clean. `docs/openapi.json` regenerated (50 paths).

Carried target-hardware gate (Linux+NVIDIA pilot server): `pytest -q -m target_hardware`
— kernel no-egress, gVisor isolation, real `nvidia-smi` sizing, and a real QLoRA
fine-tune on one 24–48 GB GPU (BRD O3/NFR-07).
