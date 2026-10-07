# Phase 0 acceptance tests

Phase 0 exit gate (BRD §12): **privacy model proven; no-egress test passed; audit hash
chain verified.** Each Phase 0 Must requirement has a pass/fail test below. Tests that need
real GPU/containers are tagged `target_hardware` and run on the Linux+NVIDIA reference
server; everything else runs anywhere against the `mock` runtime backend.

| Req | What it means | Test | Where it runs | Status |
| --- | --- | --- | --- | --- |
| FR-01 | Notebooks run cell by cell in the browser | Gateway exec endpoint runs a cell via session mgr (mock kernel), returns output | anywhere (mock) | see tests/ |
| FR-02 | Existing `.ipynb` open unchanged | Load a stock `.ipynb` fixture; cells/metadata preserved round-trip | anywhere | see tests/ |
| FR-03 | Each session = sealed container + assigned GPU | Session mgr requests a KernelSpec; adapter returns a handle with a GPU allocation; two sessions are isolated | mock anywhere; real `target_hardware` | see tests/ |
| FR-16a | Local accounts | Create local user, authenticate good/bad password (argon2) | anywhere | see tests/ |
| FR-19 | Tamper-evident audit log | Append N events; `verify()` ok; then edit/delete/reorder one record on disk; `verify()` reports `broken_at` = first bad seq | anywhere | **exit-gate** |
| FR-20 | No outbound internet from user code by default | (a) default egress policy denies all; (b) KernelSpec.allow_egress defaults False and container spec has no network; (c) mock user-code outbound attempt blocked + audited | anywhere (mock); real `target_hardware` | **exit-gate** |
| FR-27 | Installer checks hardware, reports model sizes/methods | hw-check with mocked `nvidia-smi` + real psutil returns a HardwareReport with methods + recommended sizes; no-GPU host yields CPU-only + warning, not a crash | anywhere | see tests/ |

## Target-hardware acceptance (closes the gate on the pilot server)
- FR-03/FR-20 at the kernel level: start a real rootless container with gVisor and
  `--network none`; prove user code inside cannot reach any external address (DNS + raw IP).
- FR-27: real `nvidia-smi` output parsed into correct sizing on a 24/48/80 GB GPU.

Run locally: `cd backend && pytest -q`. Target-only: `pytest -q -m target_hardware` on the
Linux+NVIDIA box.
