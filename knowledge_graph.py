"""Scope-isolated SQLite knowledge graph for Personal AI Oracle.

The graph stores only explicitly supplied entities and relationships. Retrieval is
bounded, deterministic, and always restricted to the caller's scope.
"""

from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from database import init_database
from db import get_conn


ENTITY_TYPES = frozenset({
    "person", "project", "organization", "skill", "topic", "place",
    "tool", "concept", "event", "custom",
})
MAX_SCOPE_LENGTH = 255
MAX_NAME_LENGTH = 180
MAX_EVIDENCE_LENGTH = 2000
MAX_ATTRIBUTES_LENGTH = 8192
MAX_CONTEXT_LENGTH = 3000
_SECRET_PATTERN = re.compile(
    r"\b(?:api[_ -]?key|access[_ -]?token|authorization|password|private[_ -]?key)\b"
    r"\s*(?:[:=]|\bis\b)|\bBearer\s+\S+|\bsk-[A-Za-z0-9_-]{8,}\b",
    re.IGNORECASE,
)
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]{2,}|[\u0600-\u06FF]{2,}")


class KnowledgeGraphError(ValueError):
    """Raised when graph input is invalid or attempts to cross a scope boundary."""


@dataclass(frozen=True)
class Entity:
    id: int
    name: str
    entity_type: str
    scope: str
    attributes: Mapping[str, Any]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class RelatedEntity:
    entity: Entity
    distance: int
    relation_type: str
    direction: str
    connected_entity_id: int
    evidence: str = ""


@dataclass(frozen=True)
class GraphRetrieval:
    seed_entities: tuple[Entity, ...]
    related_entities: tuple[RelatedEntity, ...]
    expansion_terms: tuple[str, ...]
    context_text: str

    @property
    def seed_count(self) -> int:
        return len(self.seed_entities)

    @property
    def relation_count(self) -> int:
        return len(self.related_entities)


def _context_atom(value: Any) -> str:
    """Keep graph-owned text inert inside the system-prompt context boundary."""
    return (
        str(value)
        .replace("&", r"\u0026")
        .replace("<", r"\u003c")
        .replace(">", r"\u003e")
        .replace("\\r", " ")
        .replace("\\n", " ")
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _scope(value: str) -> str:
    if not isinstance(value, str) or not (value := value.strip()):
        raise KnowledgeGraphError("scope is required")
    if len(value) > MAX_SCOPE_LENGTH:
        raise KnowledgeGraphError("scope is too long")
    return value


def _name(value: str, field: str = "name") -> str:
    if not isinstance(value, str) or not (value := value.strip()):
        raise KnowledgeGraphError(f"{field} is required")
    if len(value) > MAX_NAME_LENGTH:
        raise KnowledgeGraphError(f"{field} must be at most {MAX_NAME_LENGTH} characters")
    if _SECRET_PATTERN.search(value):
        raise KnowledgeGraphError("credentials and secrets cannot be stored in the graph")
    return value


def _positive_id(value: int, field: str = "entity_id") -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise KnowledgeGraphError(f"{field} must be a positive integer")
    return value


def _entity_type(value: str) -> str:
    if not isinstance(value, str):
        raise KnowledgeGraphError("entity_type must be text")
    normalized = value.strip().lower()
    if normalized not in ENTITY_TYPES:
        raise KnowledgeGraphError("unsupported entity_type")
    return normalized


def _contains_secret(value: Any) -> bool:
    """Inspect both structured field names and nested string values."""
    sensitive_key = re.compile(
        r"(?:^|[_-])(?:api[_-]?key|access[_-]?token|authorization|password|"
        r"private[_-]?key|secret)(?:$|[_-])",
        re.IGNORECASE,
    )
    if isinstance(value, Mapping):
        return any(
            sensitive_key.search(str(key)) is not None or _contains_secret(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_secret(item) for item in value)
    return isinstance(value, str) and _SECRET_PATTERN.search(value) is not None


def _attributes(value: Mapping[str, Any] | None) -> tuple[dict[str, Any], str]:
    if value is None:
        normalized: dict[str, Any] = {}
    elif isinstance(value, Mapping):
        normalized = dict(value)
    else:
        raise KnowledgeGraphError("attributes must be a mapping")
    try:
        serialized = json.dumps(
            normalized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise KnowledgeGraphError("attributes must contain JSON-compatible values") from exc
    if len(serialized) > MAX_ATTRIBUTES_LENGTH:
        raise KnowledgeGraphError("attributes are too large")
    if _contains_secret(normalized):
        raise KnowledgeGraphError("credentials and secrets cannot be stored in the graph")
    return normalized, serialized


def _relation_type(value: str) -> str:
    if not isinstance(value, str):
        raise KnowledgeGraphError("relation_type must be text")
    normalized = value.strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", normalized):
        raise KnowledgeGraphError("relation_type must be a 2-64 character lowercase identifier")
    return normalized


def _entity_from_row(row: Any) -> Entity:
    try:
        attributes = json.loads(row["attributes_json"] or "{}")
    except (TypeError, ValueError):
        attributes = {}
    if not isinstance(attributes, dict):
        attributes = {}
    return Entity(
        id=int(row["id"]),
        name=row["name"],
        entity_type=row["entity_type"],
        scope=row["scope"],
        attributes=attributes,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def add_entity(
    scope: str,
    name: str,
    entity_type: str = "concept",
    *,
    attributes: Mapping[str, Any] | None = None,
) -> Entity:
    """Create an entity or return the existing same-name entity in this scope."""
    scope = _scope(scope)
    name = _name(name)
    entity_type = _entity_type(entity_type)
    normalized_name = " ".join(name.casefold().split())
    normalized_attributes, attributes_json = _attributes(attributes)
    now = _now()

    init_database()
    conn = get_conn()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO knowledge_entities
               (scope, name, normalized_name, entity_type, attributes_json, created_at, updated_at)
               VALUES(?,?,?,?,?,?,?)""",
            (scope, name, normalized_name, entity_type, attributes_json, now, now),
        )
        conn.commit()
        row = conn.execute(
            """SELECT id, name, entity_type, scope, attributes_json, created_at, updated_at
               FROM knowledge_entities WHERE scope = ? AND normalized_name = ?""",
            (scope, normalized_name),
        ).fetchone()
        if row is None:
            raise KnowledgeGraphError("entity could not be persisted")
        return _entity_from_row(row)
    finally:
        conn.close()


def get_entity(scope: str, entity_id: int) -> Entity | None:
    scope = _scope(scope)
    entity_id = _positive_id(entity_id)
    init_database()
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT id, name, entity_type, scope, attributes_json, created_at, updated_at
               FROM knowledge_entities WHERE id = ? AND scope = ?""",
            (entity_id, scope),
        ).fetchone()
        return _entity_from_row(row) if row else None
    finally:
        conn.close()


def list_entities(scope: str, *, limit: int = 100) -> list[Entity]:
    """List recent entities owned by a scope, without exposing other scopes."""
    scope = _scope(scope)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise KnowledgeGraphError("limit must be an integer from 1 to 100")
    init_database()
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT id, name, entity_type, scope, attributes_json, created_at, updated_at
               FROM knowledge_entities WHERE scope = ?
               ORDER BY updated_at DESC, id DESC LIMIT ?""",
            (scope, limit),
        ).fetchall()
        return [_entity_from_row(row) for row in rows]
    finally:
        conn.close()


def list_relations(
    scope: str,
    *,
    entity_id: int | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """List directed relationships within one scope, optionally around one entity."""
    scope = _scope(scope)
    if entity_id is not None:
        entity_id = _positive_id(entity_id)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
        raise KnowledgeGraphError("limit must be an integer from 1 to 200")
    init_database()
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT r.id, r.scope, r.source_entity_id, s.name AS source_name,
                      r.target_entity_id, t.name AS target_name, r.relation_type,
                      r.evidence, r.created_at
               FROM knowledge_relations r
               JOIN knowledge_entities s
                 ON s.id = r.source_entity_id AND s.scope = r.scope
               JOIN knowledge_entities t
                 ON t.id = r.target_entity_id AND t.scope = r.scope
               WHERE r.scope = ?
                 AND (? IS NULL OR r.source_entity_id = ? OR r.target_entity_id = ?)
               ORDER BY r.id DESC LIMIT ?""",
            (scope, entity_id, entity_id, entity_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def search_entities(scope: str, query: str, *, limit: int = 20) -> list[Entity]:
    """Find entities by deterministic token overlap without crossing user scopes."""
    scope = _scope(scope)
    if not isinstance(query, str):
        raise KnowledgeGraphError("query must be text")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise KnowledgeGraphError("limit must be an integer from 1 to 100")
    tokens = {token.casefold() for token in _TOKEN_PATTERN.findall(query)}
    if not tokens:
        return []

    init_database()
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT id, name, entity_type, scope, attributes_json, created_at, updated_at
               FROM knowledge_entities WHERE scope = ?
               ORDER BY updated_at DESC, id DESC LIMIT 500""",
            (scope,),
        ).fetchall()
        scored: list[tuple[float, int, Entity]] = []
        for position, row in enumerate(rows):
            entity = _entity_from_row(row)
            entity_tokens = {token.casefold() for token in _TOKEN_PATTERN.findall(entity.name)}
            overlap = len(tokens & entity_tokens)
            if overlap:
                score = overlap / max(1, len(entity_tokens))
                if entity.name.casefold() in query.casefold():
                    score += 1.0
                scored.append((score, -position, entity))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [item[2] for item in scored[:limit]]
    finally:
        conn.close()


def link_entities(
    scope: str,
    source_entity_id: int,
    target_entity_id: int,
    relation_type: str,
    *,
    evidence: str = "",
) -> bool:
    """Create a directed relation only between entities owned by the same scope."""
    scope = _scope(scope)
    source_entity_id = _positive_id(source_entity_id, "source_entity_id")
    target_entity_id = _positive_id(target_entity_id, "target_entity_id")
    if source_entity_id == target_entity_id:
        raise KnowledgeGraphError("self-relations are not supported")
    relation_type = _relation_type(relation_type)
    if not isinstance(evidence, str):
        raise KnowledgeGraphError("evidence must be text")
    evidence = evidence.strip()
    if len(evidence) > MAX_EVIDENCE_LENGTH:
        raise KnowledgeGraphError("evidence is too long")
    if _SECRET_PATTERN.search(evidence):
        raise KnowledgeGraphError("credentials and secrets cannot be stored as evidence")

    init_database()
    conn = get_conn()
    try:
        placeholders = ",".join("?" for _ in (source_entity_id, target_entity_id))
        rows = conn.execute(
            f"""SELECT id FROM knowledge_entities
                WHERE scope = ? AND id IN ({placeholders})""",
            (scope, source_entity_id, target_entity_id),
        ).fetchall()
        if len(rows) != 2:
            raise KnowledgeGraphError("both entities must exist in the supplied scope")
        cur = conn.execute(
            """INSERT OR IGNORE INTO knowledge_relations
               (scope, source_entity_id, target_entity_id, relation_type, evidence, created_at)
               VALUES(?,?,?,?,?,?)""",
            (scope, source_entity_id, target_entity_id, relation_type, evidence, _now()),
        )
        conn.commit()
        return cur.rowcount == 1
    finally:
        conn.close()


def related_entities(
    scope: str,
    entity_id: int,
    *,
    depth: int = 1,
    limit: int = 50,
) -> list[RelatedEntity]:
    """Traverse outgoing and incoming edges with cycle protection and hard bounds."""
    scope = _scope(scope)
    entity_id = _positive_id(entity_id)
    if isinstance(depth, bool) or not isinstance(depth, int) or not 1 <= depth <= 3:
        raise KnowledgeGraphError("depth must be an integer from 1 to 3")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise KnowledgeGraphError("limit must be an integer from 1 to 100")

    init_database()
    conn = get_conn()
    try:
        start = conn.execute(
            """SELECT id, name, entity_type, scope, attributes_json, created_at, updated_at
               FROM knowledge_entities WHERE id = ? AND scope = ?""",
            (entity_id, scope),
        ).fetchone()
        if start is None:
            return []
        queue = deque([(entity_id, 0)])
        visited = {entity_id}
        results: list[RelatedEntity] = []
        while queue and len(results) < limit:
            current_id, distance = queue.popleft()
            if distance >= depth:
                continue
            outgoing = conn.execute(
                """SELECT r.target_entity_id AS related_id, r.relation_type, r.evidence,
                          r.source_entity_id AS connected_id, e.id, e.name, e.entity_type,
                          e.scope, e.attributes_json, e.created_at, e.updated_at
                   FROM knowledge_relations r
                   JOIN knowledge_entities e
                     ON e.id = r.target_entity_id AND e.scope = r.scope
                   WHERE r.scope = ? AND r.source_entity_id = ?
                   ORDER BY r.id LIMIT ?""",
                (scope, current_id, limit),
            ).fetchall()
            incoming = conn.execute(
                """SELECT r.source_entity_id AS related_id, r.relation_type, r.evidence,
                          r.target_entity_id AS connected_id, e.id, e.name, e.entity_type,
                          e.scope, e.attributes_json, e.created_at, e.updated_at
                   FROM knowledge_relations r
                   JOIN knowledge_entities e
                     ON e.id = r.source_entity_id AND e.scope = r.scope
                   WHERE r.scope = ? AND r.target_entity_id = ?
                   ORDER BY r.id LIMIT ?""",
                (scope, current_id, limit),
            ).fetchall()
            for row, direction in [(row, "outgoing") for row in outgoing] + [
                (row, "incoming") for row in incoming
            ]:
                related_id = int(row["related_id"])
                if related_id in visited:
                    continue
                visited.add(related_id)
                results.append(
                    RelatedEntity(
                        entity=_entity_from_row(row),
                        distance=distance + 1,
                        relation_type=row["relation_type"],
                        direction=direction,
                        connected_entity_id=int(row["connected_id"]),
                        evidence=row["evidence"] or "",
                    )
                )
                queue.append((related_id, distance + 1))
                if len(results) >= limit:
                    break
        return results
    finally:
        conn.close()


def delete_entity(scope: str, entity_id: int) -> bool:
    """Delete an entity and all scoped edges touching it."""
    scope = _scope(scope)
    entity_id = _positive_id(entity_id)
    init_database()
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        exists = conn.execute(
            "SELECT 1 FROM knowledge_entities WHERE id = ? AND scope = ?",
            (entity_id, scope),
        ).fetchone()
        if not exists:
            conn.rollback()
            return False
        conn.execute(
            """DELETE FROM knowledge_relations
               WHERE scope = ? AND (source_entity_id = ? OR target_entity_id = ?)""",
            (scope, entity_id, entity_id),
        )
        conn.execute(
            "DELETE FROM knowledge_entities WHERE id = ? AND scope = ?",
            (entity_id, scope),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def retrieve_graph(
    scope: str,
    query: str,
    *,
    max_entities: int = 5,
    max_relations: int = 12,
) -> GraphRetrieval:
    """Return bounded graph seeds, neighbors, explicit evidence and query terms.

    Only edges explicitly stored in the caller's scope are traversed. The
    expansion terms contain entity names, not inferred associations or
    relationship evidence, so stored evidence cannot silently broaden search.
    """
    scope = _scope(scope)
    if not isinstance(query, str):
        raise KnowledgeGraphError("query must be text")
    if (
        isinstance(max_entities, bool) or not isinstance(max_entities, int)
        or not 1 <= max_entities <= 10
    ):
        raise KnowledgeGraphError("max_entities must be an integer from 1 to 10")
    if (
        isinstance(max_relations, bool) or not isinstance(max_relations, int)
        or not 0 <= max_relations <= 30
    ):
        raise KnowledgeGraphError("max_relations must be an integer from 0 to 30")

    seeds = search_entities(scope, query, limit=max_entities)
    if not seeds:
        return GraphRetrieval((), (), (), "")

    related: list[RelatedEntity] = []
    terms: list[str] = []
    seen_terms: set[str] = set()
    lines: list[str] = []

    def add_term(value: str) -> None:
        normalized = " ".join(value.casefold().split())
        if value.strip() and normalized not in seen_terms and len(terms) < 20:
            seen_terms.add(normalized)
            terms.append(value.strip()[:MAX_NAME_LENGTH])

    for seed in seeds:
        add_term(seed.name)
        lines.append(
            f"- {_context_atom(seed.name)} ({_context_atom(seed.entity_type)})"
        )
        remaining = max_relations - len(related)
        if remaining <= 0:
            continue
        neighbors = related_entities(
            scope,
            seed.id,
            depth=1,
            limit=min(10, remaining),
        )
        for neighbor in neighbors:
            related.append(neighbor)
            add_term(neighbor.entity.name)
            if neighbor.direction == "outgoing":
                relation_line = (
                    f"  {_context_atom(seed.name)} → {neighbor.relation_type}: "
                    f"{_context_atom(neighbor.entity.name)} ({_context_atom(neighbor.entity.entity_type)})"
                )
            else:
                relation_line = (
                    f"  {_context_atom(neighbor.entity.name)} → {neighbor.relation_type}: "
                    f"{_context_atom(seed.name)} ({_context_atom(seed.entity_type)})"
                )
            lines.append(relation_line)
            if neighbor.evidence:
                evidence = neighbor.evidence.replace("\n", " ").strip()[:500]
                lines.append(f"    Stored evidence: {evidence}")
            if len("\n".join(lines)) >= MAX_CONTEXT_LENGTH:
                break
        if len("\n".join(lines)) >= MAX_CONTEXT_LENGTH:
            break

    context_text = "\n".join(lines)[:MAX_CONTEXT_LENGTH]
    return GraphRetrieval(
        seed_entities=tuple(seeds),
        related_entities=tuple(related),
        expansion_terms=tuple(terms),
        context_text=context_text,
    )


def retrieve_context(
    scope: str,
    query: str,
    *,
    max_entities: int = 5,
    max_relations: int = 12,
) -> str:
    """Backward-compatible graph context renderer."""
    return retrieve_graph(
        scope,
        query,
        max_entities=max_entities,
        max_relations=max_relations,
    ).context_text
