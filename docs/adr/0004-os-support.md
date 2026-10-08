# ADR-0004: Operating system and driver support

- **Status:** Accepted for Phase 0 (confirm with benchmarks)
- **Owner:** Security/DevOps engineer
- **Phase:** 0

## Decision
Target Ubuntu 22.04 LTS (driver 535+, CUDA 12.2+) and 24.04 LTS (550+, 12.4+) as Full
support; RHEL 9 best-effort. Development happens on any OS via the mock runtime backend;
the Docker runtime backend and gVisor isolation are exercised only on the Linux target.

## Consequences
CI runs on `ubuntu-latest`. Windows/macOS dev boxes run the full test suite against the
mock backend; container/GPU acceptance is tagged `target_hardware` and skipped off-target.
