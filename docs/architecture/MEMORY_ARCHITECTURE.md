# Personal AI Oracle — Memory Architecture

**Implementation branch:** `oracle/phase-02-memory-evolution`  
**Parent:** PR #7 — domain-aware research freshness.

## Current layers

### 1. Semantic memory — existing `memory.py`

The original API remains backward-compatible and continues to store explicit:

- `fact`
- `preference`
- `goal`

Records are scope-isolated, deduplicated by normalized content/type/scope, source-tagged, and retrievable through dependency-free Arabic/English lexical overlap. Secret-looking strings are rejected by the existing validation layer.

### 2. Episodic memory — new `memory_layers.py`

Episodic records represent explicit events and milestones.

Fields:

- Scope.
- Event type.
- Summary.
- Optional JSON details.
- Source/provenance label.
- `happened_at`: when the event occurred.
- `recorded_at`: when Oracle stored the event.

The event store normalizes timestamps to UTC, supports deterministic duplicate detection within a scope, and provides bounded lexical retrieval. Retrieval does not inject unrelated recent events when the current query has no meaningful terms.

Events are currently written explicitly through `record_event`; this increment does not automatically infer events from every chat or tool call.

### 3. Procedural memory — new `memory_layers.py`

Procedural records represent reusable workflows and operating playbooks.

Fields:

- Scope.
- Name and description.
- Ordered steps.
- Source/provenance.
- Status.
- Success and failure counters.
- Created/updated timestamps.

New procedures start as `candidate`. They are not included in normal context retrieval until explicitly changed to `validated`. Retrieval excludes retired and candidate procedures by default.

Observed outcomes update counters but do not automatically validate a procedure. This prevents one successful run from silently promoting an unreviewed workflow.

### 4. Working memory — request-scoped

Existing AI request/conversation context remains short-lived and is not automatically persisted into long-term memory by these changes.

### 5. Knowledge graph — existing `knowledge_graph.py`

The explicit SQLite entity/relation graph remains a separate but complementary source of contextual relationships. This increment does not automatically create graph nodes or edges from episodic events or procedures.

## AI Core integration

`ai_core._messages_with_memory` now retrieves a bounded set of:

- Relevant existing facts/preferences/goals.
- Relevant explicitly stored episodic events.
- Relevant validated procedures only.
- Existing explicit knowledge-graph context.

Episodic and procedural data are serialized as JSON and escape markup delimiters before insertion into the prompt context. The system instructions treat stored data as context rather than independent authorization to execute an action.

The new memory layers are fail-soft: if their tables or retrieval path are unavailable, the existing chat path continues without those additions.

## Storage and compatibility

The new tables are created additively by the existing idempotent SQLite initialization:

- `memory_events`
- `memory_procedures`

No existing `memories` records are rewritten or migrated. A regression test constructs a legacy `memories` table, initializes the new layers, and verifies that the legacy row remains available.

This is an additive schema-initialization increment, not yet a general versioned migration framework.

## Retrieval behavior and limitations

- Retrieval currently uses deterministic lexical overlap and recency ordering.
- No embedding/vector index has been introduced.
- There is no cross-layer semantic reranker.
- Events/procedures are explicit records; automatic extraction and consolidation are not implemented.
- Procedure revisions/version history are not implemented.
- Event/procedure-to-knowledge-graph relationships are not automatically inferred.
- No automatic deletion or compaction is performed by the new memory layer.
- Memory deletion behavior in existing APIs still needs to be reviewed against the owner's deletion-approval rule at the application/tool boundary.

## Next memory milestones

1. Add temporal/version metadata and safe revision history.
2. Add optional embeddings with deterministic lexical fallback.
3. Implement hybrid lexical/vector/metadata/temporal ranking.
4. Add provenance-backed links between memories, events, procedures, tasks, and knowledge-graph entities.
5. Add reviewable memory consolidation and entity resolution.
6. Measure retrieval quality with a bilingual evaluation set.
