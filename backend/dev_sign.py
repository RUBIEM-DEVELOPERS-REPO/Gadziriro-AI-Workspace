"""Mint signed update + plug-in bundles the running dev server will accept.

Requires GADZIRIRO_DEV_SIGNING_SEED set to the SAME value the server runs with.
Prints a base64 update bundle (for the Updates tab) and a plug-in install JSON
(for the Plugins tab / POST /api/plugins/install).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os

from nacl.signing import SigningKey

from gadziriro.plugins.kit import sign_plugin
from gadziriro.updates.signing import build_update


def _key(purpose: str) -> SigningKey:
    seed = os.environ["GADZIRIRO_DEV_SIGNING_SEED"]
    return SigningKey(hashlib.sha256(f"{seed}:{purpose}".encode("utf-8")).digest())


def main() -> int:
    # Signed update, version above the server's 0.1.0 start.
    bundle, _ = build_update("0.2.0", b"demo release payload", _key("update"))
    print("=== UPDATES tab: paste this base64 into 'bundle' ===")
    print(base64.b64encode(bundle).decode())
    print()

    # Signed plug-in (vision).
    manifest = {
        "name": "demo-vision",
        "kind": "vision",
        "version": "1.0.0",
        "entrypoint": "plugin:main",
        "api_version": "1",
    }
    pb = sign_plugin(manifest, b"demo plugin payload", _key("plugin"))
    install = {
        "manifest": pb.manifest,
        "payload_b64": base64.b64encode(pb.payload).decode(),
        "sig": pb.sig,
    }
    print("=== PLUGINS tab: POST /api/plugins/install body ===")
    print(json.dumps(install))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
