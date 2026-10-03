"""Explicit, scope-isolated memory records backed by the existing SQLite DB."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from database import init_database
from db import get_conn


MEMORY_TYPES = frozenset({"fact", "preference", "goal"})
MAX_CONTENT_LENGTH = 4000
MAX_SCOPE_LENGTH = 255
MAX_SOURCE_LENGTH = 255


class MemoryValidationError(ValueError):
    """Raised when an explicit memory record is unsafe or incomplete."""


@dataclass(frozen=True)
class MemoryRecord:
    """An immutable, explicitly written memory owned by one scope."""

    id: int
    content: str
    memory_type: str
    scope: str
    source: str
    created_at: str


def write_memory(content: str, memory_type: str, scope: str, source: str) -> MemoryRecord:
    """Store one explicit memory or return its deterministic duplicate."""
    content, normalized_content = _validate_content(content)
    memory_type = _validate_memory_type(memory_type)
    scope = _validate_identifier(scope, "scope", MAX_SCOPE_LENGTH)
    source = _validate_identifier(source, "source", MAX_SOURCE_LENGTH)

    init_database()
    conn = get_conn()
    try:
        created_at = datetime.now().isoformat(timespec="microseconds")
        conn.execute(
            """INSERT OR IGNORE INTO memories
               (content, normalized_content, memory_type, scope, source, created_at)
               VALUES(?,?,?,?,?,?)""",
            (content, normalized_content, memory_type, scope, source, created_at),
        )
        conn.commit()
        row = conn.execute(
            """SELECT id, content, memory_type, scope, source, created_at
               FROM memories
               WHERE normalized_content = ? AND memory_type = ? AND scope = ?""",
            (normalized_content, memory_type, scope),
        ).fetchone()
        return _record_from_row(row)
    finally:
        conn.close()


def get_memory(memory_id: int, scope: str) -> MemoryRecord | None:
    """Return one memory only when the caller supplies its owning scope."""
    scope = _validate_identifier(scope, "scope", MAX_SCOPE_LENGTH)
    init_database()
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT id, content, memory_type, scope, source, created_at
               FROM memories WHERE id = ? AND scope = ?""",
            (memory_id, scope),
        ).fetchone()
        return _record_from_row(row) if row else None
    finally:
        conn.close()


def list_memories(
    scope: str,
    *,
    memory_type: str | None = None,
    source: str | None = None,
    limit: int = 50,
) -> list[MemoryRecord]:
    """List one scope's memories newest first with deterministic filters."""
    scope = _validate_identifier(scope, "scope", MAX_SCOPE_LENGTH)
    if memory_type is not None:
        memory_type = _validate_memory_type(memory_type)
    if source is not None:
        source = _validate_identifier(source, "source", MAX_SOURCE_LENGTH)
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > 1000:
        raise MemoryValidationError("limit must be an integer from 1 to 1000")

    clauses = ["scope = ?"]
    params: list[object] = [scope]
    if memory_type is not None:
        clauses.append("memory_type = ?")
        params.append(memory_type)
    if source is not None:
        clauses.append("source = ?")
        params.append(source)
    params.append(limit)

    init_database()
    conn = get_conn()
    try:
        query = (
            "SELECT id, content, memory_type, scope, source, created_at "
            "FROM memories WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at DESC, id DESC LIMIT ?"
        )
        rows = conn.execute(
            query,
            params,
        ).fetchall()
        return [_record_from_row(row) for row in rows]
    finally:
        conn.close()


def delete_memory(memory_id: int, scope: str) -> bool:
    """Hard-delete one memory only from the supplied owning scope."""
    scope = _validate_identifier(scope, "scope", MAX_SCOPE_LENGTH)
    init_database()
    conn = get_conn()
    try:
        cur = conn.execute("DELETE FROM memories WHERE id = ? AND scope = ?", (memory_id, scope))
        conn.commit()
        return cur.rowcount == 1
    finally:
        conn.close()


def _validate_content(content: str) -> tuple[str, str]:
    if not isinstance(content, str):
        raise MemoryValidationError("content must be text")
    content = content.strip()
    if not content:
        raise MemoryValidationError("content is required")
    if len(content) > MAX_CONTENT_LENGTH:
        raise MemoryValidationError(f"content must be at most {MAX_CONTENT_LENGTH} characters")
    if _looks_like_secret(content):
        raise MemoryValidationError("credentials and secrets cannot be stored as memory")
    return content, " ".join(content.split())


def _validate_memory_type(memory_type: str) -> str:
    if memory_type not in MEMORY_TYPES:
        raise MemoryValidationError("memory_type must be fact, preference, or goal")
    return memory_type


def _validate_identifier(value: str, field: str, maximum_length: int) -> str:
    if not isinstance(value, str) or not (value := value.strip()):
        raise MemoryValidationError(f"{field} is required")
    if len(value) > maximum_length:
        raise MemoryValidationError(f"{field} must be at most {maximum_length} characters")
    return value


def _looks_like_secret(content: str) -> bool:
    return bool(
        re.search(
            r"\b(?:api[_ -]?key|access[_ -]?token|authorization|password|private[_ -]?key)\b"
            r"\s*(?:[:=]|\bis\b)",
            content,
            flags=re.IGNORECASE,
        )
        or re.search(r"\bBearer\s+\S+", content, flags=re.IGNORECASE)
        or re.search(r"\bsk-[A-Za-z0-9_-]{8,}\b", content)
    )


def _record_from_row(row) -> MemoryRecord:
    return MemoryRecord(
        id=row["id"],
        content=row["content"],
        memory_type=row["memory_type"],
        scope=row["scope"],
        source=row["source"],
        created_at=row["created_at"],
    )
