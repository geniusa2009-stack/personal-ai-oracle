"""Scope-isolated episodic and procedural memory layers.

Semantic fact/preference/goal records remain in memory.py for backward
compatibility. This module adds explicit event memory and reusable procedures.
Procedures are candidates until explicitly marked validated; retrieval defaults
to validated procedures only.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Mapping, Sequence

from database import init_database
from db import get_conn


MAX_SCOPE_LENGTH = 255
MAX_SOURCE_LENGTH = 255
MAX_EVENT_TYPE_LENGTH = 80
MAX_SUMMARY_LENGTH = 1000
MAX_EVENT_DETAILS_LENGTH = 4000
MAX_PROCEDURE_NAME_LENGTH = 200
MAX_PROCEDURE_DESCRIPTION_LENGTH = 1200
MAX_PROCEDURE_STEPS = 24
MAX_PROCEDURE_STEP_LENGTH = 600
MAX_PROCEDURE_TOTAL_LENGTH = 8000
VALID_PROCEDURE_STATUSES = frozenset({"candidate", "validated", "retired"})
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]{2,}|[\u0600-\u06FF]{2,}")


class MemoryLayerError(ValueError):
    """Raised when an episodic or procedural memory contract is invalid."""


@dataclass(frozen=True)
class EpisodicMemory:
    id: int
    scope: str
    event_type: str
    summary: str
    details: Mapping[str, Any]
    source: str
    happened_at: str
    recorded_at: str


@dataclass(frozen=True)
class ProceduralMemory:
    id: int
    scope: str
    name: str
    description: str
    steps: tuple[str, ...]
    source: str
    status: str
    success_count: int
    failure_count: int
    created_at: str
    updated_at: str


def _identifier(value: Any, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MemoryLayerError(f"{field} is required")
    normalized = value.strip()
    if len(normalized) > maximum:
        raise MemoryLayerError(f"{field} must be at most {maximum} characters")
    return normalized


def _text(value: Any, field: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise MemoryLayerError(f"{field} must be text")
    normalized = " ".join(value.split()).strip()
    if not normalized:
        raise MemoryLayerError(f"{field} is required")
    if len(normalized) > maximum:
        raise MemoryLayerError(f"{field} must be at most {maximum} characters")
    if _looks_like_secret(normalized):
        raise MemoryLayerError("credentials and secrets cannot be stored in memory")
    return normalized


def _looks_like_secret(value: str) -> bool:
    return bool(
        re.search(
            r"\b(?:api[_ -]?key|access[_ -]?token|authorization|password|private[_ -]?key)\b"
            r"\s*(?:[:=]|\bis\b)",
            value,
            flags=re.IGNORECASE,
        )
        or re.search(r"\bBearer\s+\S+", value, flags=re.IGNORECASE)
        or re.search(r"\bsk-[A-Za-z0-9_-]{8,}\b", value)
    )


def _timestamp(value: Any, *, field: str) -> str:
    if value is None:
        parsed = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise MemoryLayerError(f"{field} must be a valid ISO date or datetime") from exc
    else:
        raise MemoryLayerError(f"{field} must be a date, datetime, or ISO string")

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _tokens(value: str) -> set[str]:
    stop_words = {
        "the", "and", "for", "with", "that", "this", "from", "have", "you", "your",
        "are", "was", "were", "what", "when", "where", "how", "can", "could",
        "من", "في", "على", "إلى", "الى", "عن", "مع", "ده", "دي", "دا", "هو",
        "هي", "أنا", "انا", "انت", "أنت", "منه", "فيه", "اللي", "هذا", "هذه",
    }
    return {
        item.casefold()
        for item in _TOKEN_PATTERN.findall(value or "")
        if item.casefold() not in stop_words
    }


def _score(query_tokens: set[str], candidate_text: str) -> float:
    candidate_tokens = _tokens(candidate_text)
    if not query_tokens or not candidate_tokens:
        return 0.0
    overlap = query_tokens & candidate_tokens
    if not overlap:
        return 0.0
    return len(overlap) / ((len(query_tokens) * len(candidate_tokens)) ** 0.5)


def _event_from_row(row: Any) -> EpisodicMemory:
    try:
        details = json.loads(row["details_json"])
    except (TypeError, ValueError):
        details = {}
    if not isinstance(details, dict):
        details = {}
    return EpisodicMemory(
        id=int(row["id"]),
        scope=row["scope"],
        event_type=row["event_type"],
        summary=row["summary"],
        details=details,
        source=row["source"],
        happened_at=row["happened_at"],
        recorded_at=row["recorded_at"],
    )


def _procedure_from_row(row: Any) -> ProceduralMemory:
    try:
        steps = json.loads(row["steps_json"])
    except (TypeError, ValueError):
        steps = []
    if not isinstance(steps, list):
        steps = []
    return ProceduralMemory(
        id=int(row["id"]),
        scope=row["scope"],
        name=row["name"],
        description=row["description"],
        steps=tuple(str(step) for step in steps),
        source=row["source"],
        status=row["status"],
        success_count=int(row["success_count"]),
        failure_count=int(row["failure_count"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def record_event(
    scope: str,
    event_type: str,
    summary: str,
    source: str,
    *,
    happened_at: date | datetime | str | None = None,
    details: Mapping[str, Any] | None = None,
) -> EpisodicMemory:
    """Record an explicit event and return its deterministic duplicate if present."""
    scope = _identifier(scope, "scope", MAX_SCOPE_LENGTH)
    event_type = _identifier(event_type, "event_type", MAX_EVENT_TYPE_LENGTH)
    summary = _text(summary, "summary", MAX_SUMMARY_LENGTH)
    source = _identifier(source, "source", MAX_SOURCE_LENGTH)
    happened = _timestamp(happened_at, field="happened_at")

    if details is None:
        details_payload: dict[str, Any] = {}
    elif isinstance(details, Mapping):
        details_payload = dict(details)
    else:
        raise MemoryLayerError("details must be a mapping")

    try:
        details_json = json.dumps(
            details_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise MemoryLayerError("details must contain JSON-serializable values") from exc
    if len(details_json) > MAX_EVENT_DETAILS_LENGTH:
        raise MemoryLayerError("event details are too large")
    if _looks_like_secret(details_json):
        raise MemoryLayerError("credentials and secrets cannot be stored in memory")

    normalized_summary = " ".join(summary.casefold().split())
    recorded = _timestamp(None, field="recorded_at")
    init_database()
    conn = get_conn()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO memory_events
               (scope, event_type, summary, normalized_summary, details_json,
                source, happened_at, recorded_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (
                scope, event_type, summary, normalized_summary, details_json,
                source, happened, recorded,
            ),
        )
        conn.commit()
        row = conn.execute(
            """SELECT id, scope, event_type, summary, details_json, source,
                      happened_at, recorded_at
               FROM memory_events
               WHERE scope = ? AND event_type = ?
                 AND normalized_summary = ? AND happened_at = ?""",
            (scope, event_type, normalized_summary, happened),
        ).fetchone()
        if row is None:
            raise MemoryLayerError("event could not be persisted")
        return _event_from_row(row)
    finally:
        conn.close()


def list_events(
    scope: str,
    *,
    event_type: str | None = None,
    limit: int = 50,
) -> list[EpisodicMemory]:
    scope = _identifier(scope, "scope", MAX_SCOPE_LENGTH)
    if event_type is not None:
        event_type = _identifier(event_type, "event_type", MAX_EVENT_TYPE_LENGTH)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        raise MemoryLayerError("limit must be an integer from 1 to 500")

    clauses = ["scope = ?"]
    params: list[Any] = [scope]
    if event_type:
        clauses.append("event_type = ?")
        params.append(event_type)
    params.append(limit)

    init_database()
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT id, scope, event_type, summary, details_json, source,
                      happened_at, recorded_at
               FROM memory_events WHERE """
            + " AND ".join(clauses)
            + " ORDER BY happened_at DESC, id DESC LIMIT ?",
            params,
        ).fetchall()
        return [_event_from_row(row) for row in rows]
    finally:
        conn.close()


def retrieve_events(
    scope: str,
    query: str,
    *,
    limit: int = 4,
    candidate_limit: int = 200,
) -> list[EpisodicMemory]:
    """Lexically retrieve relevant events; never inject unrelated recent events."""
    scope = _identifier(scope, "scope", MAX_SCOPE_LENGTH)
    if not isinstance(query, str):
        raise MemoryLayerError("query must be text")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 12:
        raise MemoryLayerError("limit must be an integer from 1 to 12")
    if (
        isinstance(candidate_limit, bool)
        or not isinstance(candidate_limit, int)
        or not 1 <= candidate_limit <= 500
    ):
        raise MemoryLayerError("candidate_limit must be an integer from 1 to 500")
    query_tokens = _tokens(query[-12000:])
    if not query_tokens:
        return []

    candidates = list_events(scope, limit=candidate_limit)
    scored = []
    for position, item in enumerate(candidates):
        score = _score(
            query_tokens,
            f"{item.event_type} {item.summary} {json.dumps(item.details, ensure_ascii=False)}",
        )
        if score > 0:
            scored.append((score, -position, item))
    scored.sort(key=lambda value: (value[0], value[1]), reverse=True)
    return [item for _, _, item in scored[:limit]]


def record_procedure(
    scope: str,
    name: str,
    description: str,
    steps: Sequence[str],
    source: str,
) -> ProceduralMemory:
    """Record a procedure as a candidate; it is not retrievable until validated."""
    scope = _identifier(scope, "scope", MAX_SCOPE_LENGTH)
    name = _text(name, "name", MAX_PROCEDURE_NAME_LENGTH)
    description = _text(description, "description", MAX_PROCEDURE_DESCRIPTION_LENGTH)
    source = _identifier(source, "source", MAX_SOURCE_LENGTH)
    if not isinstance(steps, Sequence) or isinstance(steps, (str, bytes)):
        raise MemoryLayerError("steps must be a sequence of text steps")
    normalized_steps = tuple(
        _text(step, "step", MAX_PROCEDURE_STEP_LENGTH) for step in steps
    )
    if not 1 <= len(normalized_steps) <= MAX_PROCEDURE_STEPS:
        raise MemoryLayerError(f"steps must contain 1 to {MAX_PROCEDURE_STEPS} items")
    total = len(name) + len(description) + sum(len(step) for step in normalized_steps)
    if total > MAX_PROCEDURE_TOTAL_LENGTH:
        raise MemoryLayerError("procedure content is too large")

    steps_json = json.dumps(normalized_steps, ensure_ascii=False, separators=(",", ":"))
    normalized_name = " ".join(name.casefold().split())
    now = _timestamp(None, field="created_at")
    init_database()
    conn = get_conn()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO memory_procedures
               (scope, name, normalized_name, description, steps_json, source,
                status, success_count, failure_count, created_at, updated_at)
               VALUES(?,?,?,?,?,?,'candidate',0,0,?,?)""",
            (
                scope, name, normalized_name, description, steps_json, source,
                now, now,
            ),
        )
        conn.commit()
        row = conn.execute(
            """SELECT id, scope, name, description, steps_json, source, status,
                      success_count, failure_count, created_at, updated_at
               FROM memory_procedures WHERE scope = ? AND normalized_name = ?""",
            (scope, normalized_name),
        ).fetchone()
        if row is None:
            raise MemoryLayerError("procedure could not be persisted")
        return _procedure_from_row(row)
    finally:
        conn.close()


def list_procedures(
    scope: str,
    *,
    status: str | None = "validated",
    limit: int = 50,
) -> list[ProceduralMemory]:
    scope = _identifier(scope, "scope", MAX_SCOPE_LENGTH)
    if status is not None and status not in VALID_PROCEDURE_STATUSES:
        raise MemoryLayerError("status must be candidate, validated, retired, or None")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
        raise MemoryLayerError("limit must be an integer from 1 to 200")

    clauses = ["scope = ?"]
    params: list[Any] = [scope]
    if status is not None:
        clauses.append("status = ?")
        params.append(status)
    params.append(limit)

    init_database()
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT id, scope, name, description, steps_json, source, status,
                      success_count, failure_count, created_at, updated_at
               FROM memory_procedures WHERE """
            + " AND ".join(clauses)
            + " ORDER BY updated_at DESC, id DESC LIMIT ?",
            params,
        ).fetchall()
        return [_procedure_from_row(row) for row in rows]
    finally:
        conn.close()


def retrieve_procedures(
    scope: str,
    query: str,
    *,
    limit: int = 3,
    candidate_limit: int = 100,
) -> list[ProceduralMemory]:
    """Retrieve only validated procedures relevant to the current task."""
    scope = _identifier(scope, "scope", MAX_SCOPE_LENGTH)
    if not isinstance(query, str):
        raise MemoryLayerError("query must be text")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10:
        raise MemoryLayerError("limit must be an integer from 1 to 10")
    if (
        isinstance(candidate_limit, bool)
        or not isinstance(candidate_limit, int)
        or not 1 <= candidate_limit <= 200
    ):
        raise MemoryLayerError("candidate_limit must be an integer from 1 to 200")
    query_tokens = _tokens(query[-12000:])
    if not query_tokens:
        return []

    candidates = list_procedures(scope, status="validated", limit=candidate_limit)
    scored = []
    for position, item in enumerate(candidates):
        searchable = " ".join((item.name, item.description, *item.steps))
        score = _score(query_tokens, searchable)
        if score > 0:
            scored.append((score, -position, item))
    scored.sort(key=lambda value: (value[0], value[1]), reverse=True)
    return [item for _, _, item in scored[:limit]]


def set_procedure_status(scope: str, procedure_id: int, status: str) -> ProceduralMemory | None:
    """Explicitly validate or retire a candidate procedure within its owning scope."""
    scope = _identifier(scope, "scope", MAX_SCOPE_LENGTH)
    if isinstance(procedure_id, bool) or not isinstance(procedure_id, int) or procedure_id < 1:
        raise MemoryLayerError("procedure_id must be a positive integer")
    if status not in VALID_PROCEDURE_STATUSES:
        raise MemoryLayerError("status must be candidate, validated, or retired")

    now = _timestamp(None, field="updated_at")
    init_database()
    conn = get_conn()
    try:
        conn.execute(
            """UPDATE memory_procedures SET status = ?, updated_at = ?
               WHERE id = ? AND scope = ?""",
            (status, now, procedure_id, scope),
        )
        conn.commit()
        row = conn.execute(
            """SELECT id, scope, name, description, steps_json, source, status,
                      success_count, failure_count, created_at, updated_at
               FROM memory_procedures WHERE id = ? AND scope = ?""",
            (procedure_id, scope),
        ).fetchone()
        return _procedure_from_row(row) if row else None
    finally:
        conn.close()


def record_procedure_outcome(
    scope: str,
    procedure_id: int,
    *,
    success: bool,
) -> ProceduralMemory | None:
    """Record an observed outcome without automatically validating a procedure."""
    scope = _identifier(scope, "scope", MAX_SCOPE_LENGTH)
    if isinstance(procedure_id, bool) or not isinstance(procedure_id, int) or procedure_id < 1:
        raise MemoryLayerError("procedure_id must be a positive integer")
    if not isinstance(success, bool):
        raise MemoryLayerError("success must be a boolean")
    column = "success_count" if success else "failure_count"
    now = _timestamp(None, field="updated_at")

    init_database()
    conn = get_conn()
    try:
        conn.execute(
            f"""UPDATE memory_procedures
                SET {column} = {column} + 1, updated_at = ?
                WHERE id = ? AND scope = ?""",
            (now, procedure_id, scope),
        )
        conn.commit()
        row = conn.execute(
            """SELECT id, scope, name, description, steps_json, source, status,
                      success_count, failure_count, created_at, updated_at
               FROM memory_procedures WHERE id = ? AND scope = ?""",
            (procedure_id, scope),
        ).fetchone()
        return _procedure_from_row(row) if row else None
    finally:
        conn.close()
