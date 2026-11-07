"""Additive metadata, validity, provenance snapshots, and non-destructive memory revisions."""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Mapping, Sequence

from database import init_database
from db import get_conn


class MemoryLifecycleError(ValueError):
    """Invalid memory metadata or lifecycle operation."""


@dataclass(frozen=True)
class MemoryMetadata:
    memory_id: int
    scope: str
    confidence: float
    importance: float
    valid_from: str | None
    valid_until: str | None
    access_count: int
    last_accessed_at: str | None
    status: str
    superseded_by_id: int | None
    updated_at: str


@dataclass(frozen=True)
class MemoryRevision:
    id: int
    memory_id: int
    scope: str
    revision_kind: str
    content_hash: str
    metadata: Mapping[str, Any]
    reason: str
    actor: str
    created_at: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _scope(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 255:
        raise MemoryLifecycleError("scope is required and must be at most 255 characters")
    return value.strip()


def _text(value: Any, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MemoryLifecycleError(f"{field} is required")
    value = value.strip()
    if len(value) > maximum:
        raise MemoryLifecycleError(f"{field} must be at most {maximum} characters")
    return value


def _score(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or not 0 <= float(value) <= 1:
        raise MemoryLifecycleError(f"{field} must be a finite number from 0 to 1")
    return float(value)


def _timestamp(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        value = datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    elif isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise MemoryLifecycleError(f"{field} must be a valid ISO date or datetime") from exc
    if not isinstance(value, datetime):
        raise MemoryLifecycleError(f"{field} must be a date, datetime, ISO string, or None")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _from_row(row: Any) -> MemoryMetadata:
    return MemoryMetadata(
        memory_id=int(row["memory_id"]), scope=row["scope"],
        confidence=float(row["confidence"]), importance=float(row["importance"]),
        valid_from=row["valid_from"], valid_until=row["valid_until"],
        access_count=int(row["access_count"]), last_accessed_at=row["last_accessed_at"],
        status=row["status"],
        superseded_by_id=int(row["superseded_by_id"]) if row["superseded_by_id"] is not None else None,
        updated_at=row["updated_at"],
    )


def _payload(item: MemoryMetadata) -> dict[str, Any]:
    return {
        "confidence": item.confidence, "importance": item.importance,
        "valid_from": item.valid_from, "valid_until": item.valid_until,
        "access_count": item.access_count, "last_accessed_at": item.last_accessed_at,
        "status": item.status, "superseded_by_id": item.superseded_by_id,
    }


def _get(conn: Any, memory_id: int, scope: str) -> MemoryMetadata | None:
    row = conn.execute(
        """SELECT memory_id,scope,confidence,importance,valid_from,valid_until,
                  access_count,last_accessed_at,status,superseded_by_id,updated_at
           FROM memory_metadata WHERE memory_id=? AND scope=?""",
        (memory_id, scope),
    ).fetchone()
    return _from_row(row) if row else None


def record_memory_created(conn: Any, *, memory_id: int, scope: str, content: str, created_at: str, actor: str) -> None:
    """Insert metadata and its initial revision using the caller's transaction."""
    now = _now()
    metadata = MemoryMetadata(memory_id, scope, 0.5, 0.5, created_at, None, 0, None, "active", None, now)
    conn.execute(
        """INSERT OR IGNORE INTO memory_metadata
           (memory_id,scope,confidence,importance,valid_from,valid_until,access_count,
            last_accessed_at,status,superseded_by_id,updated_at)
           VALUES(?,?,0.5,0.5,?,NULL,0,NULL,'active',NULL,?)""",
        (memory_id, scope, created_at, now),
    )
    conn.execute(
        """INSERT INTO memory_revision_history
           (memory_id,scope,revision_kind,content_hash,metadata_json,reason,actor,created_at)
           VALUES(?,?,'created',?,?,?,?,?)""",
        (memory_id, scope, hashlib.sha256(content.encode("utf-8")).hexdigest(),
         json.dumps(_payload(metadata), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
         "Memory explicitly created", actor, now),
    )


def get_memory_metadata(memory_id: int, scope: str) -> MemoryMetadata | None:
    scope = _scope(scope)
    if isinstance(memory_id, bool) or not isinstance(memory_id, int) or memory_id < 1:
        raise MemoryLifecycleError("memory_id must be a positive integer")
    init_database()
    conn = get_conn()
    try:
        return _get(conn, memory_id, scope)
    finally:
        conn.close()


def set_memory_metadata(
    memory_id: int, scope: str, *, reason: str, actor: str = "manual",
    confidence: float | None = None, importance: float | None = None,
    valid_from: date | datetime | str | None = None,
    valid_until: date | datetime | str | None = None,
) -> MemoryMetadata:
    """Update provenance metadata and append a non-destructive revision snapshot."""
    scope = _scope(scope)
    reason, actor = _text(reason, "reason", 1000), _text(actor, "actor", 255)
    if all(value is None for value in (confidence, importance, valid_from, valid_until)):
        raise MemoryLifecycleError("at least one metadata field must be supplied")
    conf = _score(confidence, "confidence") if confidence is not None else None
    imp = _score(importance, "importance") if importance is not None else None
    vf = _timestamp(valid_from, "valid_from") if valid_from is not None else None
    vu = _timestamp(valid_until, "valid_until") if valid_until is not None else None
    init_database()
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT id,content,created_at FROM memories WHERE id=? AND scope=?",
            (memory_id, scope),
        ).fetchone()
        if row is None:
            raise MemoryLifecycleError("memory was not found in the supplied scope")
        old = _get(conn, memory_id, scope) or MemoryMetadata(
            memory_id, scope, 0.5, 0.5, row["created_at"], None, 0, None, "active", None, _now()
        )
        next_from = vf if vf is not None else old.valid_from
        next_until = vu if vu is not None else old.valid_until
        start, end = _parse(next_from), _parse(next_until)
        if start and end and end < start:
            raise MemoryLifecycleError("valid_until cannot be earlier than valid_from")
        updated = MemoryMetadata(
            memory_id, scope,
            conf if conf is not None else old.confidence,
            imp if imp is not None else old.importance,
            next_from, next_until, old.access_count, old.last_accessed_at,
            old.status, old.superseded_by_id, _now(),
        )
        conn.execute(
            """INSERT INTO memory_metadata
               (memory_id,scope,confidence,importance,valid_from,valid_until,access_count,
                last_accessed_at,status,superseded_by_id,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(memory_id,scope) DO UPDATE SET
                 confidence=excluded.confidence,importance=excluded.importance,
                 valid_from=excluded.valid_from,valid_until=excluded.valid_until,
                 updated_at=excluded.updated_at""",
            (memory_id, scope, updated.confidence, updated.importance, updated.valid_from,
             updated.valid_until, updated.access_count, updated.last_accessed_at,
             updated.status, updated.superseded_by_id, updated.updated_at),
        )
        conn.execute(
            """INSERT INTO memory_revision_history
               (memory_id,scope,revision_kind,content_hash,metadata_json,reason,actor,created_at)
               VALUES(?,?,'metadata_updated',?,?,?,?,?)""",
            (memory_id, scope, hashlib.sha256(row["content"].encode("utf-8")).hexdigest(),
             json.dumps(_payload(updated), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
             reason, actor, updated.updated_at),
        )
        conn.commit()
        return updated
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def revise_memory(
    memory_id: int, scope: str, content: str, *, reason: str, source: str,
    confidence: float | None = None, importance: float | None = None,
    valid_until: date | datetime | str | None = None,
):
    """Create a new memory version and supersede the old one without overwriting it."""
    import memory

    scope, reason = _scope(scope), _text(reason, "reason", 1000)
    source = _text(source, "source", memory.MAX_SOURCE_LENGTH)
    content, normalized = memory._validate_content(content)
    conf = _score(confidence, "confidence") if confidence is not None else None
    imp = _score(importance, "importance") if importance is not None else None
    vu = _timestamp(valid_until, "valid_until")
    proposed_start = datetime.now(timezone.utc)
    proposed_end = _parse(vu)
    if proposed_end is not None and proposed_end < proposed_start:
        raise MemoryLifecycleError("valid_until cannot be earlier than the new version's valid_from")
    init_database()
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        old_row = conn.execute(
            "SELECT id,content,memory_type,scope,source,created_at FROM memories WHERE id=? AND scope=?",
            (memory_id, scope),
        ).fetchone()
        if old_row is None:
            raise MemoryLifecycleError("memory was not found in the supplied scope")
        old_meta = _get(conn, memory_id, scope)
        if old_meta and old_meta.status != "active":
            raise MemoryLifecycleError("only an active memory can be revised")
        created = datetime.now().isoformat(timespec="microseconds")
        cursor = conn.execute(
            """INSERT OR IGNORE INTO memories
               (content,normalized_content,memory_type,scope,source,created_at)
               VALUES(?,?,?,?,?,?)""",
            (content, normalized, old_row["memory_type"], scope, source, created),
        )
        new_row = conn.execute(
            """SELECT id,content,memory_type,scope,source,created_at FROM memories
               WHERE normalized_content=? AND memory_type=? AND scope=?""",
            (normalized, old_row["memory_type"], scope),
        ).fetchone()
        if new_row is None or int(new_row["id"]) == memory_id:
            raise MemoryLifecycleError("revision content must differ from the current memory")
        new_id = int(new_row["id"])
        new_meta = _get(conn, new_id, scope)
        if new_meta and new_meta.status != "active":
            raise MemoryLifecycleError("matching content already exists as a superseded memory")
        if cursor.rowcount == 1 or new_meta is None:
            old_conf, old_imp = (
                (old_meta.confidence, old_meta.importance) if old_meta else (0.5, 0.5)
            )
            new_meta = MemoryMetadata(
                new_id, scope, conf if conf is not None else old_conf,
                imp if imp is not None else old_imp, _now(), vu, 0, None,
                "active", None, _now(),
            )
            conn.execute(
                """INSERT OR IGNORE INTO memory_metadata
                   (memory_id,scope,confidence,importance,valid_from,valid_until,access_count,
                    last_accessed_at,status,superseded_by_id,updated_at)
                   VALUES(?,?,?,?,?,?,0,NULL,'active',NULL,?)""",
                (new_id, scope, new_meta.confidence, new_meta.importance,
                 new_meta.valid_from, new_meta.valid_until, new_meta.updated_at),
            )
            conn.execute(
                """INSERT INTO memory_revision_history
                   (memory_id,scope,revision_kind,content_hash,metadata_json,reason,actor,created_at)
                   VALUES(?,?,'created',?,?,?,?,?)""",
                (new_id, scope, hashlib.sha256(content.encode("utf-8")).hexdigest(),
                 json.dumps(_payload(new_meta), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                 f"Created as revision of memory {memory_id}: {reason}", source, new_meta.updated_at),
            )
        if old_meta is None:
            old_meta = MemoryMetadata(
                memory_id, scope, 0.5, 0.5, old_row["created_at"], None, 0, None, "active", None, _now()
            )
        old_updated = MemoryMetadata(
            memory_id, scope, old_meta.confidence, old_meta.importance, old_meta.valid_from,
            old_meta.valid_until, old_meta.access_count, old_meta.last_accessed_at,
            "superseded", new_id, _now(),
        )
        conn.execute(
            """INSERT INTO memory_metadata
               (memory_id,scope,confidence,importance,valid_from,valid_until,access_count,
                last_accessed_at,status,superseded_by_id,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(memory_id,scope) DO UPDATE SET
                 status='superseded',superseded_by_id=excluded.superseded_by_id,
                 updated_at=excluded.updated_at""",
            (memory_id, scope, old_updated.confidence, old_updated.importance,
             old_updated.valid_from, old_updated.valid_until, old_updated.access_count,
             old_updated.last_accessed_at, old_updated.status, new_id, old_updated.updated_at),
        )
        conn.execute(
            """INSERT INTO memory_revision_history
               (memory_id,scope,revision_kind,content_hash,metadata_json,reason,actor,created_at)
               VALUES(?,?,'superseded',?,?,?,?,?)""",
            (memory_id, scope, hashlib.sha256(old_row["content"].encode("utf-8")).hexdigest(),
             json.dumps(_payload(old_updated), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
             reason, source, old_updated.updated_at),
        )
        conn.commit()
        return memory._record_from_row(new_row)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_memory_revision_history(memory_id: int, scope: str, *, limit: int = 100) -> list[MemoryRevision]:
    scope = _scope(scope)
    if isinstance(memory_id, bool) or not isinstance(memory_id, int) or memory_id < 1:
        raise MemoryLifecycleError("memory_id must be a positive integer")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        raise MemoryLifecycleError("limit must be an integer from 1 to 500")
    init_database()
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT id,memory_id,scope,revision_kind,content_hash,metadata_json,reason,actor,created_at
               FROM memory_revision_history WHERE memory_id=? AND scope=? ORDER BY id DESC LIMIT ?""",
            (memory_id, scope, limit),
        ).fetchall()
        output = []
        for row in rows:
            try:
                metadata = json.loads(row["metadata_json"])
            except (TypeError, ValueError):
                metadata = {}
            output.append(MemoryRevision(
                int(row["id"]), int(row["memory_id"]), row["scope"], row["revision_kind"],
                row["content_hash"], metadata if isinstance(metadata, dict) else {},
                row["reason"], row["actor"], row["created_at"],
            ))
        return output
    finally:
        conn.close()


def filter_and_weight(scope: str, scored: Sequence[tuple[float, int, Any]]) -> list[tuple[float, int, Any]]:
    """Filter superseded/out-of-validity records and weight by confidence and importance."""
    scope = _scope(scope)
    if not scored:
        return []
    ids = [int(entry[2].id) for entry in scored]
    marks = ",".join("?" for _ in ids)
    init_database()
    conn = get_conn()
    try:
        rows = conn.execute(
            f"""SELECT memory_id,scope,confidence,importance,valid_from,valid_until,
                       access_count,last_accessed_at,status,superseded_by_id,updated_at
                FROM memory_metadata WHERE scope=? AND memory_id IN ({marks})""",
            [scope, *ids],
        ).fetchall()
        by_id = {int(row["memory_id"]): _from_row(row) for row in rows}
        now = datetime.now(timezone.utc)
        result = []
        for score, pos, record in scored:
            meta = by_id.get(int(record.id))
            if meta is None or meta.status != "active":
                continue
            start, end = _parse(meta.valid_from), _parse(meta.valid_until)
            if (start and start > now) or (end and end < now):
                continue
            result.append((score * (0.5 + meta.confidence) * (0.5 + meta.importance), pos, record))
        return result
    finally:
        conn.close()


def record_access(scope: str, records: Sequence[Any]) -> None:
    scope = _scope(scope)
    if not records:
        return
    now = _now()
    conn = get_conn()
    try:
        conn.executemany(
            """UPDATE memory_metadata SET access_count=access_count+1,last_accessed_at=?,updated_at=?
               WHERE memory_id=? AND scope=? AND status='active'""",
            [(now, now, int(item.id), scope) for item in records],
        )
        conn.commit()
    finally:
        conn.close()
