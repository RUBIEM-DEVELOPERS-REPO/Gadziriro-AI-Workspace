# Deployment notes

- **Dev (any OS):** `docker compose -f deploy/docker-compose.dev.yml up` — runs the gateway
  with the `mock` runtime backend (no GPU needed).
- **Target (Linux + NVIDIA):** install the NVIDIA Container Toolkit and gVisor (`runsc`),
  set `GADZIRIRO_RUNTIME_BACKEND=docker`, and run session containers rootless with
  `--network none` (FR-20) and `--runtime=runsc` (NFR-05). GPU acceptance tests:
  `pytest -q -m target_hardware`.
