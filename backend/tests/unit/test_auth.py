"""Unit tests for the local-account user store (FR-16a, FR-18a)."""

from __future__ import annotations

import pytest
from argon2 import PasswordHasher

from gadziriro.auth.base import Principal, Role
from gadziriro.auth.store import SqlUserStore
from gadziriro.core.errors import AuthError


@pytest.fixture()
def store(tmp_path) -> SqlUserStore:
    """A store on a throwaway sqlite file with cheap argon2 parameters."""
    url = f"sqlite:///{tmp_path / 'auth.db'}"
    cheap = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
    return SqlUserStore(url, hasher=cheap)


def test_create_and_authenticate_good_password(store: SqlUserStore) -> None:
    created = store.create_user("alice", "s3cret!", {Role.ANALYST})
    assert isinstance(created, Principal)
    assert created.username == "alice"

    authed = store.authenticate("alice", "s3cret!")
    assert authed is not None
    assert authed.user_id == created.user_id
    assert authed.username == "alice"


def test_authenticate_bad_password_returns_none(store: SqlUserStore) -> None:
    store.create_user("bob", "correct-horse", {Role.VIEWER})
    assert store.authenticate("bob", "wrong") is None


def test_authenticate_unknown_user_returns_none(store: SqlUserStore) -> None:
    assert store.authenticate("nobody", "whatever") is None


def test_duplicate_username_raises(store: SqlUserStore) -> None:
    store.create_user("carol", "pw1", {Role.ADMIN})
    with pytest.raises(AuthError):
        store.create_user("carol", "pw2", {Role.VIEWER})


def test_password_hash_is_not_plaintext(store: SqlUserStore) -> None:
    # Reach into the ORM to assert the stored hash is not the plaintext.
    from sqlalchemy.orm import Session

    from gadziriro.auth.store import User

    store.create_user("dave", "plaintext-pw", {Role.VIEWER})
    with Session(store._engine) as session:  # noqa: SLF001 - white-box check
        row = session.query(User).filter(User.username == "dave").one()
    assert row.password_hash != "plaintext-pw"
    assert row.password_hash.startswith("$argon2")


def test_roles_round_trip(store: SqlUserStore) -> None:
    store.create_user("erin", "pw", {Role.ADMIN, Role.COMPLIANCE})
    principal = store.authenticate("erin", "pw")
    assert principal is not None
    assert principal.roles == frozenset({Role.ADMIN, Role.COMPLIANCE})


def test_get_by_user_id(store: SqlUserStore) -> None:
    created = store.create_user("frank", "pw", {Role.DATA_SCIENTIST})
    fetched = store.get(created.user_id)
    assert fetched is not None
    assert fetched.username == "frank"
    assert store.get("no-such-id") is None
