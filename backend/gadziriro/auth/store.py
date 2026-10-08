"""SQLAlchemy-backed local-account user store (FR-16a, FR-18a).

A concrete :class:`~gadziriro.auth.base.UserStore` using a single ``users``
table and argon2 password hashing. Passwords are hashed with
:class:`argon2.PasswordHasher`; only the hash is ever stored, and
:meth:`SqlUserStore.authenticate` returns ``None`` for a wrong password
(it never leaks whether the username exists through its return shape).

SSO/MFA (FR-16b, FR-17) are Phase 1; this store only knows local accounts.
"""

from __future__ import annotations

import uuid
from typing import Optional, Union

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import String, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from ..core.config import Settings
from ..core.errors import AuthError
from .base import Principal, Role

# NOTE (Phase 1 TODO): schema is created here with ``Base.metadata.create_all``.
# Replace with Alembic migrations once the schema stabilises past Phase 0.


class Base(DeclarativeBase):
    """Declarative base for the auth schema."""


class User(Base):
    """A local account row.

    ``roles`` is a comma-separated list of :class:`Role` values (e.g.
    ``"admin,analyst"``); it is split/joined when mapping to and from the
    :class:`Principal` dataclass. Per-project roles (FR-18a) are a Phase 1
    extension and are not persisted yet.
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    roles: Mapped[str] = mapped_column(String(255), nullable=False, default="")


def init_db(engine: Engine) -> None:
    """Create the auth tables on ``engine`` if they do not already exist.

    Phase 0 convenience; Alembic migrations replace this in Phase 1.
    """
    Base.metadata.create_all(engine)


def _roles_to_str(roles: set[Role]) -> str:
    """Serialise a set of roles to a stable comma-separated string."""
    return ",".join(sorted(role.value for role in roles))


def _roles_from_str(raw: str) -> frozenset[Role]:
    """Parse a comma-separated role string into a frozenset of :class:`Role`."""
    return frozenset(
        Role(value) for value in (part.strip() for part in raw.split(",")) if value
    )


class SqlUserStore:
    """SQLAlchemy 2.0 ORM implementation of the :class:`UserStore` protocol."""

    def __init__(
        self,
        engine_or_settings: Union[Engine, Settings, None] = None,
        *,
        hasher: Optional[PasswordHasher] = None,
    ) -> None:
        """Build a store from an :class:`Engine`, a :class:`Settings`, or a URL.

        :param engine_or_settings: a SQLAlchemy :class:`Engine`, a
            :class:`Settings` (its ``database_url`` is used), a database URL
            string, or ``None`` (defaults from :class:`Settings`).
        :param hasher: optional argon2 hasher override (tests may lower the
            cost parameters); defaults to a stock :class:`PasswordHasher`.
        """
        if isinstance(engine_or_settings, Engine):
            self._engine = engine_or_settings
        else:
            if isinstance(engine_or_settings, str):
                url = engine_or_settings
            elif isinstance(engine_or_settings, Settings):
                url = engine_or_settings.database_url
            else:
                url = Settings().database_url
            self._engine = create_engine(url, future=True)
        self._hasher = hasher or PasswordHasher()
        init_db(self._engine)

    # -- mapping ---------------------------------------------------------

    @staticmethod
    def _to_principal(row: User) -> Principal:
        """Map a :class:`User` row onto the :class:`Principal` dataclass."""
        return Principal(
            user_id=row.id,
            username=row.username,
            roles=_roles_from_str(row.roles),
        )

    # -- UserStore protocol ---------------------------------------------

    def create_user(self, username: str, password: str, roles: set[Role]) -> Principal:
        """Create a local account and return its :class:`Principal`.

        :raises AuthError: if ``username`` is already taken.
        """
        user = User(
            id=str(uuid.uuid4()),
            username=username,
            password_hash=self._hasher.hash(password),
            roles=_roles_to_str(set(roles)),
        )
        with Session(self._engine) as session:
            session.add(user)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise AuthError(f"username already exists: {username}") from exc
            session.refresh(user)
            return self._to_principal(user)

    def authenticate(self, username: str, password: str) -> Optional[Principal]:
        """Return the :class:`Principal` on valid credentials, else ``None``.

        A wrong password or unknown username both yield ``None``. On a correct
        password stored under outdated argon2 parameters the hash is silently
        upgraded (rehash-on-verify).
        """
        with Session(self._engine) as session:
            row = session.query(User).filter(User.username == username).one_or_none()
            if row is None:
                return None
            try:
                self._hasher.verify(row.password_hash, password)
            except VerifyMismatchError:
                return None
            except Exception:  # noqa: BLE001 - any verify failure is a refusal
                return None
            if self._hasher.check_needs_rehash(row.password_hash):
                row.password_hash = self._hasher.hash(password)
                session.commit()
            return self._to_principal(row)

    def get(self, user_id: str) -> Optional[Principal]:
        """Return the :class:`Principal` for ``user_id``, or ``None``."""
        with Session(self._engine) as session:
            row = session.get(User, user_id)
            return self._to_principal(row) if row is not None else None
