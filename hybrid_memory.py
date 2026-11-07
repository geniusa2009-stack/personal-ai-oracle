"""Hybrid lexical, semantic and graph-aware memory retrieval.

The lexical channel is deterministic. Vector and graph channels are separate,
bounded ranking signals, and neither may cross the caller's memory scope.
Graph expansion uses only explicitly stored entity names and relationships.
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
    graph_context: str = ""
    graph_seed_count: int = 0
    graph_relation_count: int = 0
    graph_warning_code: str | None = None


_FACT_LIMIT = 8
_EVENT_LIMIT = 4
_PROCEDURE_LIMIT = 2
_RRF_K = 60
_LEXICAL_WEIGHT = 0.7
_SEMANTIC_WEIGHT = 1.0
_GRAPH_WEIGHT = 0.45


def _lexical_records(scope: str, query: str) -> tuple[list, list, list]:
    return (
        memory.retrieve_memories(scope, query, limit=_FACT_LIMIT),
        memory_layers.retrieve_events(scope, query, limit=_EVENT_LIMIT),
        memory_layers.retrieve_procedures(scope, query, limit=_PROCEDURE_LIMIT),
    )


def _record_key(memory_type: str, record: Any) -> tuple[str, int]:
    return memory_type, int(record.id)


def _matches_type(memory_type: str, candidate_type: str) -> bool:
    if memory_type == "semantic":
        return candidate_type in {"fact", "preference", "goal"}
    return candidate_type == memory_type


def _fuse_type(
    memory_type: str,
    lexical_records: list,
    semantic_matches: list[memory_embeddings.VectorMatch],
    *,
    graph_records: list | None = None,
    limit: int,
) -> list:
    """Fuse three independent rankings using weighted reciprocal-rank fusion."""
    scores: dict[tuple[str, int], float] = {}
    records: dict[tuple[str, int], Any] = {}
    lexical_positions: dict[tuple[str, int], int] = {}

    for rank, record in enumerate(lexical_records, start=1):
        record_type = record.memory_type if memory_type == "semantic" else memory_type
        if not _matches_type(memory_type, record_type):
            continue
        key = _record_key(record_type, record)
        records[key] = record
        lexical_positions[key] = rank
        scores[key] = scores.get(key, 0.0) + _LEXICAL_WEIGHT / (_RRF_K + rank)

    semantic_rank = 0
    for match in semantic_matches:
        if not _matches_type(memory_type, match.memory_type):
            continue
        semantic_rank += 1
        key = (match.memory_type, int(match.record_id))
        records[key] = match.record
        scores[key] = scores.get(key, 0.0) + _SEMANTIC_WEIGHT / (_RRF_K + semantic_rank)

    graph_rank = 0
    for record in graph_records or []:
        record_type = record.memory_type if memory_type == "semantic" else memory_type
        if not _matches_type(memory_type, record_type):
            continue
        graph_rank += 1
        key = _record_key(record_type, record)
        records[key] = record
        scores[key] = scores.get(key, 0.0) + _GRAPH_WEIGHT / (_RRF_K + graph_rank)

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
    graph_enabled: bool = True,
    max_graph_entities: int = 5,
    max_graph_relations: int = 12,
) -> HybridMemoryContext:
    """Retrieve memories with lexical fallback and optional vector/graph RRF.

    Embeddings remain disabled unless configured explicitly. Graph lookup uses
    the existing scope-local SQLite graph only; it makes no external call.
    Auto-indexing remains opt-in.
    """
    if not isinstance(scope, str) or not scope.strip() or len(scope) > 255:
        raise ValueError("scope is required and must be at most 255 characters")
    if not isinstance(query, str):
        raise ValueError("query must be text")
    if not isinstance(graph_enabled, bool):
        raise ValueError("graph_enabled must be a boolean")

    normalized_scope = scope.strip()
    lexical_memories, lexical_events, lexical_procedures = _lexical_records(
        normalized_scope, query
    )

    graph_context = ""
    graph_terms: tuple[str, ...] = ()
    graph_seed_count = 0
    graph_relation_count = 0
    graph_warning_code = None
    graph_memories: list = []
    graph_events: list = []
    graph_procedures: list = []

    if graph_enabled:
        try:
            import knowledge_graph

            graph_result = knowledge_graph.retrieve_graph(
                normalized_scope,
                query,
                max_entities=max_graph_entities,
                max_relations=max_graph_relations,
            )
            graph_context = graph_result.context_text
            graph_terms = graph_result.expansion_terms
            graph_seed_count = graph_result.seed_count
            graph_relation_count = graph_result.relation_count
            if graph_terms:
                expanded_query = (query + "\n" + " ".join(graph_terms))[-12000:]
                graph_memories, graph_events, graph_procedures = _lexical_records(
                    normalized_scope, expanded_query
                )
        except Exception as exc:
            # A broken graph must not disable the normal memory retrieval path.
            graph_warning_code = type(exc).__name__
            graph_context = ""
            graph_terms = ()
            graph_memories, graph_events, graph_procedures = [], [], []

    selected_client = client
    warning_code = None
    if selected_client is None:
        try:
            selected_client = memory_embeddings.embedding_client_from_environment()
        except memory_embeddings.EmbeddingError as exc:
            warning_code = type(exc).__name__

    semantic_matches: list[memory_embeddings.VectorMatch] = []
    model_name = getattr(selected_client, "model_name", None) if selected_client else None

    if selected_client is not None:
        should_index = auto_index
        if should_index is None:
            should_index = os.environ.get(
                "ORACLE_MEMORY_EMBEDDINGS_AUTOINDEX", "0"
            ).strip().lower() in {"1", "true", "yes", "on"}

        try:
            if should_index:
                memory_embeddings.index_memory_scope(
                    normalized_scope,
                    client=selected_client,
                )
            semantic_matches = memory_embeddings.retrieve_vector_matches(
                normalized_scope,
                query,
                client=selected_client,
                limit=50,
            )
        except Exception as exc:
            # Keep graph and lexical channels active if the embedding provider fails.
            warning_code = type(exc).__name__
            semantic_matches = []

    has_graph_channel = bool(graph_terms)
    has_semantic_channel = bool(semantic_matches)
    if has_semantic_channel and has_graph_channel:
        retrieval_mode = "hybrid_graph"
    elif has_semantic_channel:
        retrieval_mode = "hybrid"
    elif has_graph_channel:
        retrieval_mode = "graph_lexical"
    else:
        retrieval_mode = "lexical_fallback"

    memories = _fuse_type(
        "semantic",
        lexical_memories,
        semantic_matches,
        graph_records=graph_memories,
        limit=_FACT_LIMIT,
    )
    events = _fuse_type(
        "event",
        lexical_events,
        semantic_matches,
        graph_records=graph_events,
        limit=_EVENT_LIMIT,
    )
    procedures = _fuse_type(
        "procedure",
        lexical_procedures,
        semantic_matches,
        graph_records=graph_procedures,
        limit=_PROCEDURE_LIMIT,
    )

    return HybridMemoryContext(
        memories=tuple(memories),
        events=tuple(events),
        procedures=tuple(procedures),
        retrieval_mode=retrieval_mode,
        semantic_match_count=len(semantic_matches),
        embedding_model=model_name,
        warning_code=warning_code,
        graph_context=graph_context,
        graph_seed_count=graph_seed_count,
        graph_relation_count=graph_relation_count,
        graph_warning_code=graph_warning_code,
    )
