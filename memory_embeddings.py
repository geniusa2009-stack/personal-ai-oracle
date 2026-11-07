"""Optional provider-independent embeddings and a scope-isolated SQLite vector cache.

The embedding layer is opt-in. If no provider/model is configured or a provider
fails, callers can continue using the existing deterministic lexical retrieval.
Only vector values, content hashes, model IDs, and scope metadata are persisted;
raw memory content is not duplicated in the embedding table.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol, Sequence

import requests

from database import init_database
from db import get_conn


ALLOWED_MEMORY_TYPES = frozenset({"fact", "preference", "goal", "event", "procedure"})
MAX_EMBEDDING_DIMENSIONS = 4096
MAX_QUERY_LENGTH = 5000
MAX_INDEX_RECORDS = 1000
MAX_BATCH_SIZE = 32
EMBEDDING_TIMEOUT_SECONDS = 30


class EmbeddingError(RuntimeError):
    """Raised for configuration, provider, or vector validation errors."""


class EmbeddingClientProtocol(Protocol):
    model_name: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


@dataclass(frozen=True)
class MemoryDocument:
    scope: str
    memory_type: str
    record_id: int
    content: str
    record: Any


@dataclass(frozen=True)
class VectorMatch:
    memory_type: str
    record_id: int
    similarity: float
    record: Any


class OpenAICompatibleEmbeddingClient:
    """Client for providers implementing POST /embeddings."""

    def __init__(
        self,
        *,
        base_url: str,
        model_name: str,
        api_key: str = "",
        timeout: int = EMBEDDING_TIMEOUT_SECONDS,
    ) -> None:
        if not isinstance(model_name, str) or not model_name.strip():
            raise EmbeddingError("embedding model is required")
        if not isinstance(base_url, str) or not base_url.startswith(("http://", "https://")):
            raise EmbeddingError("embedding base URL must use HTTP or HTTPS")
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, int)
            or not 1 <= timeout <= 120
        ):
            raise EmbeddingError("embedding timeout must be from 1 to 120 seconds")
        self.model_name = model_name.strip()[:200]
        self.base_url = base_url.rstrip("/")
        self.url = (
            self.base_url
            if self.base_url.endswith("/embeddings")
            else f"{self.base_url}/embeddings"
        )
        self.api_key = api_key
        self.timeout = timeout

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not isinstance(texts, Sequence) or isinstance(texts, (str, bytes)) or not texts:
            raise EmbeddingError("texts must be a non-empty sequence")
        normalized = []
        for value in texts:
            if not isinstance(value, str) or not value.strip():
                raise EmbeddingError("embedding text items must be non-empty strings")
            if len(value) > 12000:
                raise EmbeddingError("embedding text item is too large")
            normalized.append(value)

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            response = requests.post(
                self.url,
                headers=headers,
                json={"model": self.model_name, "input": normalized},
                timeout=self.timeout,
            )
            response.raise_for_status()
            body = response.json()
        except requests.RequestException as exc:
            raise EmbeddingError("embedding provider request failed") from exc
        except ValueError as exc:
            raise EmbeddingError("embedding provider returned invalid JSON") from exc

        data = body.get("data") if isinstance(body, Mapping) else None
        if not isinstance(data, list) or len(data) != len(normalized):
            raise EmbeddingError("embedding provider returned an unexpected item count")

        try:
            indices = [
                item.get("index") if isinstance(item, Mapping) else None
                for item in data
            ]
            if any(
                isinstance(index, bool) or not isinstance(index, int)
                for index in indices
            ):
                raise EmbeddingError("embedding provider returned invalid item indexes")
            if sorted(indices) != list(range(len(normalized))):
                raise EmbeddingError("embedding provider returned duplicate or missing item indexes")
            ordered = sorted(data, key=lambda item: item["index"])
            vectors = [_validate_vector(item.get("embedding")) for item in ordered]
        except (TypeError, AttributeError) as exc:
            raise EmbeddingError("embedding provider returned malformed vectors") from exc

        dimensions = {len(vector) for vector in vectors}
        if len(dimensions) != 1:
            raise EmbeddingError("embedding provider returned inconsistent dimensions")
        return vectors


def embedding_client_from_environment() -> OpenAICompatibleEmbeddingClient | None:
    """Return None unless embeddings are explicitly enabled and a model is configured."""
    enabled = os.environ.get("ORACLE_MEMORY_EMBEDDINGS_ENABLED", "0").strip().lower()
    if enabled not in {"1", "true", "yes", "on"}:
        return None

    provider = os.environ.get("ORACLE_EMBEDDING_PROVIDER", "ollama").strip().lower()
    model_name = os.environ.get("ORACLE_EMBEDDING_MODEL", "").strip()
    if not model_name:
        model_name = os.environ.get("OLLAMA_EMBEDDING_MODEL", "").strip()
    if not model_name:
        return None

    if provider == "ollama":
        base_url = os.environ.get(
            "ORACLE_EMBEDDING_BASE_URL",
            os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1"),
        )
        api_key = os.environ.get("ORACLE_EMBEDDING_API_KEY", "")
    elif provider == "openai_compatible":
        base_url = os.environ.get(
            "ORACLE_EMBEDDING_BASE_URL",
            os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        )
        api_key = os.environ.get(
            "ORACLE_EMBEDDING_API_KEY",
            os.environ.get("OPENAI_API_KEY", ""),
        )
    else:
        raise EmbeddingError("ORACLE_EMBEDDING_PROVIDER must be ollama or openai_compatible")

    return OpenAICompatibleEmbeddingClient(
        base_url=base_url,
        model_name=model_name,
        api_key=api_key,
    )


def _validate_vector(value: Any) -> list[float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise EmbeddingError("embedding vector must be a numeric sequence")
    if not 2 <= len(value) <= MAX_EMBEDDING_DIMENSIONS:
        raise EmbeddingError("embedding dimension count is outside the supported range")
    vector: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise EmbeddingError("embedding vector contains a non-numeric value")
        number = float(item)
        if not math.isfinite(number):
            raise EmbeddingError("embedding vector contains a non-finite value")
        vector.append(number)
    if not any(number != 0.0 for number in vector):
        raise EmbeddingError("embedding vector cannot be all zeros")
    return vector


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(float(a) * float(b) for a, b in zip(left, right))
    norm_left = math.sqrt(sum(float(value) ** 2 for value in left))
    norm_right = math.sqrt(sum(float(value) ** 2 for value in right))
    if norm_left == 0.0 or norm_right == 0.0:
        return 0.0
    return max(-1.0, min(1.0, dot / (norm_left * norm_right)))


def content_hash(content: str) -> str:
    if not isinstance(content, str):
        raise EmbeddingError("content must be text")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _memory_documents(scope: str, *, max_records: int) -> list[MemoryDocument]:
    import memory
    import memory_layers

    documents: list[MemoryDocument] = []
    facts = memory.list_memories(scope, limit=min(max_records, 500))
    for item in facts:
        documents.append(MemoryDocument(
            scope=scope,
            memory_type=item.memory_type,
            record_id=item.id,
            content=item.content,
            record=item,
        ))

    remaining = max(0, max_records - len(documents))
    if remaining:
        events = memory_layers.list_events(scope, limit=min(remaining, 500))
        for item in events:
            detail_json = json.dumps(item.details, ensure_ascii=False, sort_keys=True)
            documents.append(MemoryDocument(
                scope=scope,
                memory_type="event",
                record_id=item.id,
                content=f"{item.event_type}: {item.summary}\n{detail_json}",
                record=item,
            ))

    remaining = max(0, max_records - len(documents))
    if remaining:
        procedures = memory_layers.list_procedures(
            scope, status="validated", limit=min(remaining, 200)
        )
        for item in procedures:
            content = "\n".join((item.name, item.description, *item.steps))
            documents.append(MemoryDocument(
                scope=scope,
                memory_type="procedure",
                record_id=item.id,
                content=content,
                record=item,
            ))
    return documents[:max_records]


def index_memory_scope(
    scope: str,
    *,
    client: EmbeddingClientProtocol | None = None,
    batch_size: int = 16,
    max_records: int = 500,
) -> dict[str, Any]:
    """Index currently stored memories; no records are removed or modified.

    Repeated calls are content-hash aware and only re-embed missing or changed
    records for the selected embedding model.
    """
    if not isinstance(scope, str) or not scope.strip() or len(scope) > 255:
        raise EmbeddingError("scope is required and must be at most 255 characters")
    if (
        isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
        or not 1 <= batch_size <= MAX_BATCH_SIZE
    ):
        raise EmbeddingError(f"batch_size must be from 1 to {MAX_BATCH_SIZE}")
    if (
        isinstance(max_records, bool)
        or not isinstance(max_records, int)
        or not 1 <= max_records <= MAX_INDEX_RECORDS
    ):
        raise EmbeddingError(f"max_records must be from 1 to {MAX_INDEX_RECORDS}")

    selected_client = client or embedding_client_from_environment()
    if selected_client is None:
        return {
            "status": "disabled",
            "scope": scope.strip(),
            "indexed_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "model": None,
        }
    model_name = getattr(selected_client, "model_name", None)
    if not isinstance(model_name, str) or not model_name.strip():
        raise EmbeddingError("embedding client must expose a model_name")

    init_database()
    documents = _memory_documents(scope.strip(), max_records=max_records)
    conn = get_conn()
    try:
        existing_rows = conn.execute(
            """SELECT memory_type, record_id, content_hash
               FROM memory_embeddings
               WHERE scope = ? AND embedding_model = ?""",
            (scope.strip(), model_name),
        ).fetchall()
        existing = {
            (row["memory_type"], int(row["record_id"])): row["content_hash"]
            for row in existing_rows
        }

        pending = []
        skipped = 0
        for document in documents:
            digest = content_hash(document.content)
            key = (document.memory_type, document.record_id)
            if existing.get(key) == digest:
                skipped += 1
                continue
            pending.append((document, digest))

        indexed = 0
        failed = 0
        errors: list[str] = []
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")

        for offset in range(0, len(pending), batch_size):
            batch = pending[offset:offset + batch_size]
            try:
                vectors = selected_client.embed([item.content for item, _ in batch])
                if not isinstance(vectors, list) or len(vectors) != len(batch):
                    raise EmbeddingError("embedding client returned an unexpected vector count")
                validated = [_validate_vector(vector) for vector in vectors]
                dimensions = {len(vector) for vector in validated}
                if len(dimensions) != 1:
                    raise EmbeddingError("embedding client returned inconsistent dimensions")
            except Exception as exc:
                failed += len(batch)
                errors.append(type(exc).__name__)
                continue

            rows = []
            for (document, digest), vector in zip(batch, validated):
                vector_json = json.dumps(vector, separators=(",", ":"), allow_nan=False)
                rows.append((
                    scope.strip(),
                    document.memory_type,
                    document.record_id,
                    model_name,
                    digest,
                    vector_json,
                    len(vector),
                    now,
                    now,
                ))
            conn.executemany(
                """INSERT INTO memory_embeddings
                   (scope, memory_type, record_id, embedding_model, content_hash,
                    vector_json, dimensions, created_at, updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(scope, memory_type, record_id, embedding_model)
                   DO UPDATE SET
                       content_hash = excluded.content_hash,
                       vector_json = excluded.vector_json,
                       dimensions = excluded.dimensions,
                       updated_at = excluded.updated_at""",
                rows,
            )
            conn.commit()
            indexed += len(rows)

        status = "partial" if failed else ("completed" if indexed else "up_to_date")
        return {
            "status": status,
            "scope": scope.strip(),
            "indexed_count": indexed,
            "skipped_count": skipped,
            "failed_count": failed,
            "model": model_name,
            "errors": errors[:5],
        }
    finally:
        conn.close()


def retrieve_vector_matches(
    scope: str,
    query: str,
    *,
    client: EmbeddingClientProtocol | None = None,
    limit: int = 12,
    max_vectors: int = 1500,
    min_similarity: float = 0.2,
) -> list[VectorMatch]:
    """Return semantic matches only for current, scope-owned memory records."""
    if not isinstance(scope, str) or not scope.strip() or len(scope) > 255:
        raise EmbeddingError("scope is required and must be at most 255 characters")
    if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY_LENGTH:
        raise EmbeddingError("query must be non-empty text within the supported length")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
        raise EmbeddingError("limit must be from 1 to 50")
    if (
        isinstance(max_vectors, bool)
        or not isinstance(max_vectors, int)
        or not 1 <= max_vectors <= 3000
    ):
        raise EmbeddingError("max_vectors must be from 1 to 3000")
    if (
        isinstance(min_similarity, bool)
        or not isinstance(min_similarity, (int, float))
        or not math.isfinite(float(min_similarity))
        or not -1.0 <= float(min_similarity) <= 1.0
    ):
        raise EmbeddingError("min_similarity must be a finite number from -1 to 1")

    selected_client = client or embedding_client_from_environment()
    if selected_client is None:
        return []
    model_name = getattr(selected_client, "model_name", None)
    if not isinstance(model_name, str) or not model_name.strip():
        raise EmbeddingError("embedding client must expose a model_name")

    init_database()
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT memory_type, record_id, content_hash, vector_json, dimensions
               FROM memory_embeddings
               WHERE scope = ? AND embedding_model = ?
               ORDER BY updated_at DESC, id DESC LIMIT ?""",
            (scope.strip(), model_name, max_vectors),
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return []

    query_vectors = selected_client.embed([query.strip()])
    if len(query_vectors) != 1:
        raise EmbeddingError("embedding client returned an unexpected query vector count")
    query_vector = _validate_vector(query_vectors[0])

    documents = _memory_documents(scope.strip(), max_records=MAX_INDEX_RECORDS)
    current = {(item.memory_type, item.record_id): item for item in documents}
    matches = []
    for row in rows:
        key = (row["memory_type"], int(row["record_id"]))
        document = current.get(key)
        if document is None or content_hash(document.content) != row["content_hash"]:
            continue
        try:
            vector = _validate_vector(json.loads(row["vector_json"]))
        except (ValueError, TypeError, EmbeddingError):
            continue
        if int(row["dimensions"]) != len(vector) or len(vector) != len(query_vector):
            continue
        similarity = cosine_similarity(query_vector, vector)
        if similarity < float(min_similarity):
            continue
        matches.append(VectorMatch(
            memory_type=document.memory_type,
            record_id=document.record_id,
            similarity=similarity,
            record=document.record,
        ))
    matches.sort(key=lambda item: item.similarity, reverse=True)
    return matches[:limit]
