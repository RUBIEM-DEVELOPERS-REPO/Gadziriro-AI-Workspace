"""``gadziriro`` command-line tool (automation, CI/CD, air-gapped ops).

A thin :mod:`argparse` front end over the same building blocks the HTTP gateway
uses, so operators can drive the workspace without a browser:

* ``gadziriro hw-check``      — probe the host and print a hardware report.
* ``gadziriro audit verify``  — verify the tamper-evident audit hash chain.
* ``gadziriro openapi``       — emit the OpenAPI document for the Phase-0 API.
* ``gadziriro serve``         — launch the uvicorn-hosted gateway.

:func:`main` returns an integer exit code and is wired as the ``gadziriro``
console script (see ``pyproject.toml``); it is equally callable from tests.
Heavy / side-effecting imports (``uvicorn``) are deferred into their handlers so
merely importing this module never starts a server or requires optional deps.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from ..gateway.app import app
from ..installer.hwcheck import check_hardware
from .audit_cmd import verify_cmd


def _cmd_hw_check(_: argparse.Namespace) -> int:
    """Run the hardware check and print a readable report (FR-27)."""
    report = check_hardware()
    print("Gadziriro hardware check")
    print("========================")
    print(f"GPU present       : {report.gpu_present}")
    print(f"GPU count         : {report.gpu_count}")
    if report.gpu_memory_mb:
        mem = ", ".join(f"{mb} MB" for mb in report.gpu_memory_mb)
        print(f"GPU memory        : {mem}")
    print(f"CPU count         : {report.cpu_count}")
    print(f"System RAM        : {report.ram_mb} MB")
    print(f"Free disk         : {report.disk_free_gb} GB")
    methods = ", ".join(report.supported_methods) or "none"
    print(f"Supported methods : {methods}")
    sizes = ", ".join(report.recommended_model_sizes) or "none"
    print(f"Recommended sizes : {sizes}")
    if report.warnings:
        print("Warnings:")
        for warning in report.warnings:
            print(f"  - {warning}")
    else:
        print("Warnings          : none")
    return 0


def _cmd_audit_verify(args: argparse.Namespace) -> int:
    """Verify the audit hash chain under ``--audit-dir`` (FR-19)."""
    return verify_cmd(Path(args.audit_dir))


def _cmd_openapi(args: argparse.Namespace) -> int:
    """Write the gateway's OpenAPI document as pretty JSON."""
    document = json.dumps(app.openapi(), indent=2, sort_keys=True)
    out: Optional[str] = args.out
    if out is None:
        print(document)
        return 0
    path = Path(out)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document + "\n", encoding="utf-8", newline="\n")
    print(f"openapi: wrote {path}")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    """Launch the uvicorn-hosted gateway (import uvicorn lazily)."""
    import uvicorn  # Local import: only needed when actually serving.

    uvicorn.run(
        "gadziriro.gateway.app:app",
        host=args.host,
        port=args.port,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level argument parser and its subcommands."""
    parser = argparse.ArgumentParser(
        prog="gadziriro",
        description="Gadziriro AI Workspace command-line tool.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    hw = subparsers.add_parser(
        "hw-check", help="Probe the host and print a hardware report."
    )
    hw.set_defaults(func=_cmd_hw_check)

    audit = subparsers.add_parser("audit", help="Audit-log operations.")
    audit_sub = audit.add_subparsers(dest="audit_command", required=True)
    audit_verify = audit_sub.add_parser(
        "verify", help="Verify the tamper-evident audit hash chain."
    )
    audit_verify.add_argument(
        "--audit-dir",
        default=".",
        help="Directory containing audit.jsonl (default: current directory).",
    )
    audit_verify.set_defaults(func=_cmd_audit_verify)

    openapi = subparsers.add_parser(
        "openapi", help="Emit the OpenAPI document for the Phase-0 API."
    )
    openapi.add_argument(
        "--out",
        default=None,
        help="File to write the OpenAPI JSON to (default: stdout).",
    )
    openapi.set_defaults(func=_cmd_openapi)

    serve = subparsers.add_parser("serve", help="Launch the uvicorn gateway.")
    serve.add_argument("--host", default="127.0.0.1", help="Bind host.")
    serve.add_argument("--port", type=int, default=8080, help="Bind port.")
    serve.set_defaults(func=_cmd_serve)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Parse ``argv`` and dispatch to the selected subcommand.

    :param argv: argument vector excluding the program name; defaults to
        ``sys.argv[1:]`` when ``None``.
    :returns: the subcommand's integer exit code.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
