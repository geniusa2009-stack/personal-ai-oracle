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
        cursor = conn.execute(
            """INSERT OR IGNORE INTO memories
               (content, normalized_content, memory_type, scope, source, created_at)
               VALUES(?,?,?,?,?,?)""",
            (content, normalized_content, memory_type, scope, source, created_at),
        )
        row = conn.execute(
            """SELECT id, content, memory_type, scope, source, created_at
               FROM memories
               WHERE normalized_content = ? AND memory_type = ? AND scope = ?""",
            (normalized_content, memory_type, scope),
        ).fetchone()
        if row is None:
            raise MemoryValidationError("memory could not be persisted")
        if cursor.rowcount == 1:
            import memory_lifecycle
            memory_lifecycle.record_memory_created(
                conn,
                memory_id=int(row["id"]),
                scope=scope,
                content=row["content"],
                created_at=row["created_at"],
                actor=source,
            )
        conn.commit()
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
    include_superseded: bool = False,
) -> list[MemoryRecord]:
    """List one scope's memories newest first with deterministic filters."""
    scope = _validate_identifier(scope, "scope", MAX_SCOPE_LENGTH)
    if memory_type is not None:
        memory_type = _validate_memory_type(memory_type)
    if source is not None:
        source = _validate_identifier(source, "source", MAX_SOURCE_LENGTH)
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > 1000:
        raise MemoryValidationError("limit must be an integer from 1 to 1000")
    if not isinstance(include_superseded, bool):
        raise MemoryValidationError("include_superseded must be a boolean")

    clauses = ["m.scope = ?"]
    params: list[object] = [scope]
    if memory_type is not None:
        clauses.append("m.memory_type = ?")
        params.append(memory_type)
    if source is not None:
        clauses.append("m.source = ?")
        params.append(source)
    params.append(limit)

    init_database()
    conn = get_conn()
    try:
        if not include_superseded:
            clauses.append("(md.status IS NULL OR md.status = 'active')")
        query = (
            "SELECT m.id, m.content, m.memory_type, m.scope, m.source, m.created_at "
            "FROM memories AS m LEFT JOIN memory_metadata AS md "
            "ON md.memory_id = m.id AND md.scope = m.scope WHERE "
            + " AND ".join(clauses)
            + " ORDER BY m.created_at DESC, m.id DESC LIMIT ?"
        )
        rows = conn.execute(
            query,
            params,
        ).fetchall()
        return [_record_from_row(row) for row in rows]
    finally:
        conn.close()



def _memory_tokens(text: str) -> set[str]:
    """Extract simple Arabic/English terms for a dependency-free relevance score."""
    stop_words = {
        "the", "and", "for", "with", "that", "this", "from", "have", "you", "your",
        "are", "was", "were", "what", "when", "where", "how", "can", "could",
        "من", "في", "على", "إلى", "الى", "عن", "مع", "ده", "دي", "دا", "هو",
        "هي", "أنا", "انا", "انت", "أنت", "منه", "فيه", "اللي", "هذا", "هذه",
    }
    return {
        token.casefold()
        for token in re.findall(r"[A-Za-z0-9_]{2,}|[\u0600-\u06FF]{2,}", text or "")
        if token.casefold() not in stop_words
    }


def retrieve_memories(
    scope: str,
    query: str,
    *,
    limit: int = 8,
    candidate_limit: int = 100,
) -> list[MemoryRecord]:
    """Return relevant explicit memories from one scope, with recency as a tie-breaker."""
    scope = _validate_identifier(scope, "scope", MAX_SCOPE_LENGTH)
    if not isinstance(query, str):
        raise MemoryValidationError("query must be text")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 50:
        raise MemoryValidationError("limit must be an integer from 1 to 50")
    if (
        not isinstance(candidate_limit, int)
        or isinstance(candidate_limit, bool)
        or not 1 <= candidate_limit <= 1000
    ):
        raise MemoryValidationError("candidate_limit must be an integer from 1 to 1000")

    candidates = list_memories(scope, limit=candidate_limit)
    if not candidates:
        return []

    import memory_lifecycle

    query_tokens = _memory_tokens(query[-12000:])
    if not query_tokens:
        fallback = [
            (1.0, -position, item)
            for position, item in enumerate(candidates)
            if item.memory_type in {"preference", "goal"}
        ]
        fallback = memory_lifecycle.filter_and_weight(scope, fallback)
        fallback.sort(key=lambda entry: (entry[0], entry[1]), reverse=True)
        selected = [entry[2] for entry in fallback[:min(limit, 2)]]
        memory_lifecycle.record_access(scope, selected)
        return selected

    scored = []
    for position, item in enumerate(candidates):
        content_tokens = _memory_tokens(item.content)
        overlap = query_tokens & content_tokens
        if not overlap:
            continue
        # Reward memories that cover more of the current query without letting
        # a single common word dominate a long stored paragraph.
        score = len(overlap) / ((len(query_tokens) * len(content_tokens)) ** 0.5)
        scored.append((score, -position, item))

    if not scored:
        fallback = [
            (1.0, -position, item)
            for position, item in enumerate(candidates)
            if item.memory_type in {"preference", "goal"}
        ]
        fallback = memory_lifecycle.filter_and_weight(scope, fallback)
        fallback.sort(key=lambda entry: (entry[0], entry[1]), reverse=True)
        selected = [entry[2] for entry in fallback[:min(limit, 2)]]
        memory_lifecycle.record_access(scope, selected)
        return selected

    scored = memory_lifecycle.filter_and_weight(scope, scored)
    scored.sort(key=lambda entry: (entry[0], entry[1]), reverse=True)
    selected = [entry[2] for entry in scored[:limit]]
    memory_lifecycle.record_access(scope, selected)
    return selected


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
