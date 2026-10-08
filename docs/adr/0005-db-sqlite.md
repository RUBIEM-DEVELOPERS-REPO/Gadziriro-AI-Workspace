# ADR-0005: SQLite for relational state; JSONL for audit

- **Status:** Accepted
- **Owner:** Backend lead
- **Phase:** 0

## Context
Phase 0 needs to persist users/sessions and keep a tamper-evident audit log. The product
must install on one box with no specialist (O2), so a zero-config store is preferred.

## Decision
- **Relational state (users, sessions, later registry metadata):** SQLite via SQLAlchemy 2.0
  + Alembic. Postgres is a drop-in later for multi-node (NFR-08) with no model changes.
- **Audit log:** append-only hash-chained **JSONL files**, NOT a SQL table. A hash chain
  needs an append-only medium where reordering/deletion is detectable; a mutable SQL table
  undermines tamper-evidence. One file per period/scope, verified by `AuditLog.verify()`.

## Consequences
Audit lives under the encrypted data dir, outside the DB; backup/restore (Phase 1) must
cover both. The relational schema is driven by Alembic migrations from Phase 0 onward.
