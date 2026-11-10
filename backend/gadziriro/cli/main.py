"""``gadziriro`` command-line tool (automation, CI/CD, air-gapped ops).

A thin :mod:`argparse` front end over the same building blocks the HTTP gateway
uses, so operators can drive the workspace without a browser:

* ``gadziriro hw-check``      — probe the host and print a hardware report.
* ``gadziriro audit verify``  — verify the tamper-evident audit hash chain.
* ``gadziriro openapi``       — emit the OpenAPI document for the Phase-0 API.
* ``gadziriro serve``         — launch the uvicorn-hosted gateway.
* ``gadziriro model-card``    — render a model version's card (FR-36, FR-35).
* ``gadziriro policy effective`` — print the effective policy for packs (FR-24).
* ``gadziriro incidents``     — list tracked incidents (FR-38, FR-35).

The Phase 2 subcommands (``model-card``, ``policy``, ``incidents``) build the
same services the gateway wires, rooted at ``--data-dir`` (default: the
``GADZIRIRO_DATA_DIR`` setting), so they run without a server.

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

from ..core.config import Settings, load_settings
from ..core.objectstore import LocalObjectStore
from ..gateway.app import app
from ..incident.response import IncidentService
from ..installer.hwcheck import check_hardware
from ..modelcards.card import build_model_card, render_markdown
from ..policy.packs import describe_precedence, merge_packs
from ..registry.store import ObjectStoreRegistry
from .audit_cmd import verify_cmd


def _settings_for(args: argparse.Namespace) -> Settings:
    """Resolve settings for a Phase 2 subcommand (honouring ``--data-dir``)."""
    data_dir: Optional[str] = getattr(args, "data_dir", None)
    if data_dir:
        return Settings(data_dir=Path(data_dir))
    return load_settings()


def _registry_for(settings: Settings) -> ObjectStoreRegistry:
    """Build a registry over the workspace object store (gateway key layout)."""
    return ObjectStoreRegistry(LocalObjectStore(settings.data_dir / "objectstore"))


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


def _cmd_model_card(args: argparse.Namespace) -> int:
    """Render a model version's card to stdout (FR-36, FR-35)."""
    settings = _settings_for(args)
    registry = _registry_for(settings)
    card = build_model_card(
        registry, f"{args.name}@{args.version}", licence=args.licence
    )
    print(render_markdown(card))
    return 0


def _cmd_policy_effective(args: argparse.Namespace) -> int:
    """Print the effective policy + provenance for the enabled packs (FR-24)."""
    effective = merge_packs(args.packs)
    provenance = describe_precedence(args.packs)
    settings = effective.settings

    print("Gadziriro effective policy")
    print("==========================")
    print(f"Enabled packs     : {', '.join(effective.enabled) or 'none'}")
    labels = ", ".join(sorted(la.value for la in settings.export_approval_labels))
    fields = {
        "allow_egress": settings.allow_egress,
        "require_mfa": settings.require_mfa,
        "audit_retention_days": settings.audit_retention_days,
        "data_retention_max_days": settings.data_retention_max_days,
        "export_approval_labels": labels or "none",
        "min_session_timeout_s": settings.min_session_timeout_s,
        "cross_border_transfer_allowed": settings.cross_border_transfer_allowed,
    }
    for name, value in fields.items():
        src = provenance.get(name)
        src_text = ", ".join(src) if isinstance(src, list) else src
        print(f"{name:<32}: {value}  (from: {src_text})")
    return 0


def _cmd_incidents(args: argparse.Namespace) -> int:
    """List tracked incidents from a transient incident service (FR-38, FR-35)."""
    service = IncidentService()
    incidents = service.list_incidents()
    print("Gadziriro incidents")
    print("===================")
    if not incidents:
        print("No incidents recorded.")
        return 0
    for incident in incidents:
        print(
            f"{incident.incident_id}  [{incident.status}]  "
            f"{incident.severity}  {incident.title}"
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

    model_card = subparsers.add_parser(
        "model-card", help="Render a model version's card (FR-36)."
    )
    model_card.add_argument("name", help="Model name.")
    model_card.add_argument("version", help="Model version (integer).")
    model_card.add_argument(
        "--licence", default="unknown", help="Licence to state on the card."
    )
    model_card.add_argument(
        "--data-dir", default=None, help="Workspace data dir (default: settings)."
    )
    model_card.set_defaults(func=_cmd_model_card)

    policy = subparsers.add_parser("policy", help="Compliance policy operations.")
    policy_sub = policy.add_subparsers(dest="policy_command", required=True)
    policy_effective = policy_sub.add_parser(
        "effective", help="Print the effective policy for the enabled packs."
    )
    policy_effective.add_argument(
        "packs", nargs="+", help="Pack names (e.g. hipaa gdpr soc2 zw-dpa)."
    )
    policy_effective.set_defaults(func=_cmd_policy_effective)

    incidents = subparsers.add_parser(
        "incidents", help="List tracked security incidents (FR-38)."
    )
    incidents.add_argument(
        "--data-dir", default=None, help="Workspace data dir (default: settings)."
    )
    incidents.set_defaults(func=_cmd_incidents)

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
