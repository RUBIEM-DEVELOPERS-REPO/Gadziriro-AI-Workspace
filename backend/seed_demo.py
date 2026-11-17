"""Seed demo users for live testing. Idempotent."""

from __future__ import annotations

from gadziriro.auth.base import Role
from gadziriro.auth.store import SqlUserStore
from gadziriro.core.config import load_settings
from gadziriro.core.errors import AuthError

USERS = [
    ("admin", "admin-pw", {Role.ADMIN}),
    ("scientist", "scientist-pw", {Role.DATA_SCIENTIST}),
    ("analyst", "analyst-pw", {Role.ANALYST}),
    ("dpo", "dpo-pw", {Role.COMPLIANCE}),
]


def main() -> int:
    settings = load_settings()
    settings.ensure_dirs()
    store = SqlUserStore(settings)
    for username, password, roles in USERS:
        try:
            store.create_user(username, password, roles)
            print(f"created {username} ({', '.join(r.value for r in roles)})")
        except AuthError:
            print(f"exists  {username}")
    print(f"db: {settings.database_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
