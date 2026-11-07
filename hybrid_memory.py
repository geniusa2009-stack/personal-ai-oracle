"""Hybrid lexical/semantic retrieval for scope-isolated Oracle memory.

Lexical retrieval remains the deterministic baseline. Semantic retrieval is
optional, opt-in, and uses only locally cached vectors for the same scope and
embedding model. Reciprocal-rank fusion combines both result lists without
mixing user scopes or promoting unvalidated procedures.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import memory
import memory_embeddings
import memory_layers


@dataclass(frozen=True)
class HybridMemoryContext:
    memories: tuple[memory.MemoryRecord, ...]
    events: tuple[memory_layers.EpisodicMemory, ...]
    procedures: tuple[memory_layers.ProceduralMemory, ...]
    retrieval_mode: str
    semantic_match_count: int
    embedding_model: str | None
    warning_code: str | None = None


_FACT_LIMIT = 8
_EVENT_LIMIT = 4
_PROCEDURE_LIMIT = 2
_RRF_K = 60
_LEXICAL_WEIGHT = 0.7
_SEMANTIC_WEIGHT = 1.0


def _lexical_records(scope: str, query: str) -> tuple[list, list, list]:
    return (
        memory.retrieve_memories(scope, query, limit=_FACT_LIMIT),
        memory_layers.retrieve_events(scope, query, limit=_EVENT_LIMIT),
        memory_layers.retrieve_procedures(scope, query, limit=_PROCEDURE_LIMIT),
    )


def _record_key(memory_type: str, record: Any) -> tuple[str, int]:
    return memory_type, int(record.id)


def _fuse_type(
    memory_type: str,
    lexical_records: list,
    semantic_matches: list[memory_embeddings.VectorMatch],
    *,
    limit: int,
) -> list:
    scores: dict[tuple[str, int], float] = {}
    records: dict[tuple[str, int], Any] = {}
    lexical_positions: dict[tuple[str, int], int] = {}

    for rank, record in enumerate(lexical_records, start=1):
        record_type = (
            record.memory_type
            if memory_type == "semantic"
            else memory_type
        )
        if memory_type == "semantic" and record_type not in {"fact", "preference", "goal"}:
            continue
        key = _record_key(record_type, record)
        records[key] = record
        lexical_positions[key] = rank
        scores[key] = scores.get(key, 0.0) + _LEXICAL_WEIGHT / (_RRF_K + rank)

    semantic_rank = 0
    for match in semantic_matches:
        if memory_type == "semantic":
            if match.memory_type not in {"fact", "preference", "goal"}:
                continue
        elif match.memory_type != memory_type:
            continue
        semantic_rank += 1
        key = (match.memory_type, int(match.record_id))
        records[key] = match.record
        scores[key] = scores.get(key, 0.0) + _SEMANTIC_WEIGHT / (_RRF_K + semantic_rank)

    ordered = sorted(
        records,
        key=lambda key: (
            scores.get(key, 0.0),
            -lexical_positions.get(key, 10**9),
            -key[1],
        ),
        reverse=True,
    )
    return [records[key] for key in ordered[:limit]]


def retrieve_memory_context(
    scope: str,
    query: str,
    *,
    client: memory_embeddings.EmbeddingClientProtocol | None = None,
    auto_index: bool | None = None,
) -> HybridMemoryContext:
    """Retrieve relevant memories using lexical fallback and optional vector RRF.

    Embeddings are disabled unless configured explicitly. Existing indexes are
    read-only during retrieval. Rebuilding a stale/missing index is available
    only through an explicit auto_index=True argument or the opt-in environment
    setting ORACLE_MEMORY_EMBEDDINGS_AUTOINDEX=1.
    """
    if not isinstance(scope, str) or not scope.strip() or len(scope) > 255:
        raise ValueError("scope is required and must be at most 255 characters")
    if not isinstance(query, str):
        raise ValueError("query must be text")

    lexical_memories, lexical_events, lexical_procedures = _lexical_records(
        scope.strip(), query
    )
    selected_client = client
    warning_code = None

    if selected_client is None:
        try:
            selected_client = memory_embeddings.embedding_client_from_environment()
        except memory_embeddings.EmbeddingError as exc:
            warning_code = type(exc).__name__

    if selected_client is None:
        return HybridMemoryContext(
            memories=tuple(lexical_memories),
            events=tuple(lexical_events),
            procedures=tuple(lexical_procedures),
            retrieval_mode="lexical_fallback",
            semantic_match_count=0,
            embedding_model=None,
            warning_code=warning_code,
        )

    should_index = auto_index
    if should_index is None:
        should_index = os.environ.get(
            "ORACLE_MEMORY_EMBEDDINGS_AUTOINDEX", "0"
        ).strip().lower() in {"1", "true", "yes", "on"}

    try:
        model_name = selected_client.model_name
        if should_index:
            memory_embeddings.index_memory_scope(scope.strip(), client=selected_client)
        semantic_matches = memory_embeddings.retrieve_vector_matches(
            scope.strip(),
            query,
            client=selected_client,
            limit=50,
        )
    except Exception as exc:
        return HybridMemoryContext(
            memories=tuple(lexical_memories),
            events=tuple(lexical_events),
            procedures=tuple(lexical_procedures),
            retrieval_mode="lexical_fallback",
            semantic_match_count=0,
            embedding_model=getattr(selected_client, "model_name", None),
            warning_code=type(exc).__name__,
        )

    if not semantic_matches:
        return HybridMemoryContext(
            memories=tuple(lexical_memories),
            events=tuple(lexical_events),
            procedures=tuple(lexical_procedures),
            retrieval_mode="lexical_fallback",
            semantic_match_count=0,
            embedding_model=model_name,
        )

    return HybridMemoryContext(
        memories=tuple(_fuse_type(
            "semantic", lexical_memories, semantic_matches, limit=_FACT_LIMIT
        )),
        events=tuple(_fuse_type(
            "event", lexical_events, semantic_matches, limit=_EVENT_LIMIT
        )),
        procedures=tuple(_fuse_type(
            "procedure", lexical_procedures, semantic_matches, limit=_PROCEDURE_LIMIT
        )),
        retrieval_mode="hybrid",
        semantic_match_count=len(semantic_matches),
        embedding_model=model_name,
    )
