# Memory Lifecycle Metadata and Revision History

**Branch:** `oracle/phase-02-memory-lifecycle`  
**Depends on:** PR #9 (hybrid retrieval), PR #8 (episodic/procedural memory), then the preceding stacked PRs.

## Compatibility model

The existing `memories` table remains the source of record content. The existing `MemoryRecord` dataclass and the public `write_memory`, `get_memory`, `list_memories`, `retrieve_memories`, and `delete_memory` APIs retain their original record fields.

Lifecycle information is stored separately so existing modules can continue using the legacy API.

## Metadata fields

The additive `memory_metadata` table is keyed by `(memory_id, scope)` and stores:

| Field | Meaning |
|---|---|
| `confidence` | Explicit confidence score from 0 to 1; default 0.5 |
| `importance` | Explicit importance score from 0 to 1; default 0.5 |
| `valid_from` | First instant the memory is valid |
| `valid_until` | Last instant the memory is valid; null means no declared expiry |
| `access_count` | Number of retrieval selections |
| `last_accessed_at` | Timestamp of the most recent retrieval selection |
| `status` | `active` or `superseded` |
| `superseded_by_id` | Replacement memory ID when superseded |
| `updated_at` | Last metadata update time |

Confidence and importance are explicit metadata, not AI-generated truth scores. New and migrated legacy memories receive neutral defaults. No automatic model-based confidence assignment has been introduced.

## Validity-aware retrieval

Lexical retrieval first computes its existing relevance score. The lifecycle layer then:

1. Removes records whose state is superseded.
2. Removes records not yet valid or past their `valid_until`.
3. Weights remaining lexical scores using the recorded confidence and importance values.
4. Updates access statistics for selected results.

The initial multiplier is:

`(0.5 + confidence) * (0.5 + importance)`

This keeps the neutral default (0.5, 0.5) at a multiplier of 1.0. It is a transparent ranking heuristic, not a statistically calibrated probability. Retrieval still falls back to existing lexical behavior where applicable.

## Revision model

Use `memory_lifecycle.revise_memory(...)` to change the content of a memory.

It does not update the original content in place. It:

1. Validates the new content, source and reason.
2. Creates a separate record in the same scope and memory type.
3. Initializes metadata on that new record.
4. Marks the prior record as `superseded`.
5. Records the replacement ID.
6. Appends a revision event for both the new record and the superseded record.

Superseded content remains available through `get_memory` and `list_memories(include_superseded=True)`, and can be reviewed through the revision history. Normal listing and retrieval hide superseded records by default.

## Append-only revision snapshots

The `memory_revision_history` table records:

- Memory ID and scope.
- Revision kind: `created`, `metadata_updated`, `superseded`, or `legacy_baseline`.
- SHA-256 hash of the associated content.
- JSON snapshot of metadata at the time of the change.
- Reason and actor/source.
- Timestamp.

The history stores a content hash rather than a second raw copy of the memory text. Original text remains in the original `memories` row unless the explicit memory deletion API is invoked.

APIs:

- `memory_lifecycle.get_memory_metadata(memory_id, scope)`
- `memory_lifecycle.set_memory_metadata(..., reason=..., actor=...)`
- `memory_lifecycle.revise_memory(..., reason=..., source=...)`
- `memory_lifecycle.get_memory_revision_history(memory_id, scope)`

A metadata edit must identify a reason. Confidence/importance values are restricted to finite numbers between 0 and 1. A validity end cannot precede its start.

## Existing database migration

Database initialization creates the two new tables additively. Existing memory rows without lifecycle metadata receive default values and a one-time `legacy_baseline` revision record. Existing content, IDs, memory types, source values and scopes are not rewritten.

## Deletion and privacy

The explicit `memory.delete_memory` operation removes the selected source memory and its linked metadata, revision snapshots and embedding-cache row in one transaction. Its caller must enforce the configured explicit deletion approval requirement. The database panic-wipe allowlist also includes all memory lifecycle and vector tables so the new tables do not leave behind related user data.

Superseding a memory is not deletion. It preserves the old record and history.

## Limitations

- Confidence and importance are manual metadata; they are not inferred automatically.
- No UI for editing/inspecting memory metadata and history has been connected yet.
- Episodic and procedural memory have their own schemas and do not yet use this same lifecycle metadata table.
- Automatic memory extraction, entity resolution, contradiction review, deduplication across different content, and retention/consolidation policies remain unfinished.
- Access frequency is recorded but is not yet used for ranking.
- The score multiplier is an initial deterministic heuristic and needs evaluation against a reviewed bilingual memory-retrieval benchmark.
- New lifecycle validity starts are written as explicit UTC timestamps. Legacy `created_at` values are timezone-naive, so their baseline validity start is interpreted as UTC; the original timezone cannot be reconstructed reliably from the old schema.
- Revision history stores metadata and content hashes, not full historical content snapshots. Prior content remains present as its own memory row unless explicitly deleted.
- The memory-revision API has not yet been exercised against a real production database workload.

