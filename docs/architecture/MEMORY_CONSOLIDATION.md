# Memory Consolidation: Review-Only Candidate Discovery

**Branch:** \`oracle/phase-02-memory-consolidation\`  
**Depends on:** PR #11 (graph-aware retrieval), PR #10 (lifecycle metadata), PR #9 (hybrid retrieval).

## Purpose

This phase identifies memory records that may deserve human review:

- Potential duplicates: high lexical overlap between records of the same memory type.
- Potential contradictions: strong shared context combined with a negation mismatch or different numeric values.
- Related records: meaningful shared terms without enough evidence for a duplicate/contradiction classification.

These labels are candidate classifications. They do not establish that two memories are actually equivalent or contradictory.

## Safety and data-integrity contract

The discovery engine is strictly review-only.

- Scanning does not update, delete, merge, supersede, or rewrite source memories.
- Accepting or dismissing a proposal only records the review decision, reviewer, reason and timestamp.
- A source content hash is captured for every proposal member.
- If a source is deleted, changed, superseded, or outside its validity window, the proposal is surfaced as stale or marked stale during review.
- Explicit deletion of a memory removes proposals that depend on it and their observations in the same database transaction.
- Every query is scoped to the caller's exact memory scope.
- Scan and comparison counts have hard upper bounds.

A future merge operation would require its own explicit, separately authorized workflow. No such operation is implemented here.

## Classification algorithm

The first implementation is deterministic and dependency-free:

1. Load active, currently valid memories in one scope.
2. Group candidates by memory type, so records of different types are not compared as if they were interchangeable.
3. Tokenize Arabic and English content using the existing memory tokenization rules.
4. Compare candidate pairs using cosine-style token overlap and Jaccard similarity.
5. Record shared tokens, memory types, sources, negation indicators and numeric values.
6. Classify pairs according to configurable thresholds.

Default thresholds:

| Setting | Default |
|---|---:|
| Duplicate cosine/Jaccard threshold | 0.84 |
| Related cosine threshold | 0.60 |
| Contradiction cosine threshold | 0.58 |
| Minimum shared tokens | 2 |
| Candidate records per scan | 200 |
| Maximum pair comparisons | 20,000 |
| Maximum proposals per scan | 500 |

The contradiction detector currently uses two narrow lexical indicators:

- Negation presence differs between the two records.
- Both records contain numeric values and the sets of values differ.

For a contradiction proposal, the detector also requires shared non-numeric context. This reduces obvious noise, but it is not semantic claim verification. It can miss paraphrases, units, dates, scope changes, conditional statements, Arabic morphology, and more complex negation. It can also produce false positives.

## Proposal records and provenance

Each proposal contains:

- Scope and proposal type.
- Current status: \`pending_review\`, \`accepted\`, \`dismissed\`, or \`stale\`.
- Similarity score and a plain-language explanation.
- Structured signals used by the classifier.
- Stable proposal key based on algorithm version, memory IDs and content hashes.
- First/last observed timestamps and observation count.
- Last scan ID.
- Member memory IDs and SHA-256 content hashes.
- Current source records, when they still exist and match the stored hashes.
- Stale member IDs where source content changed, the source disappeared, it was superseded, or its validity window ended.

Scan metadata is stored separately from proposal rows. Observations connect a proposal to the scan that detected it, allowing repeated detections to be tracked without rewriting source memories.

## APIs

- \`memory_consolidation.scan_scope(scope, ...)\` — run a bounded scan.
- \`memory_consolidation.get_run(scope, run_id)\` — inspect scan status and counters.
- \`memory_consolidation.list_proposals(scope, ...)\` — list proposals by status/type.
- \`memory_consolidation.get_proposal(scope, proposal_id)\` — inspect proposal members and staleness.
- \`memory_consolidation.review_proposal(scope, proposal_id, decision=..., reviewer=..., reason=...)\` — accept/dismiss a pending proposal only.

A scan can return \`partial\` when a configured work limit is reached. The returned counters make truncation explicit; a partial scan must not be interpreted as exhaustive.

## Stale review protection

Before a decision is recorded, the engine re-reads every source within the same scope and verifies:

- The original memory still exists.
- Its content hash has not changed.
- Its lifecycle status is still active.
- Its validity window includes the current UTC time.

If any check fails, the proposal becomes \`stale\` and the requested accept/dismiss decision is not applied. This prevents a reviewer from acting on a candidate based on source versions that are no longer current.

## Retention and privacy

Proposal tables are included in the explicit sensitive-table wipe allowlist. Explicit deletion of a memory removes dependent proposals and observation rows, in addition to the memory's metadata, revision history and embedding cache.

The proposal stores source IDs and hashes, not a duplicate copy of the raw memory content. Current member content is loaded from the owning memory row at read time.

## Validation

\`test_memory_consolidation.py\` covers:

- Duplicate, related and numeric-conflict candidate generation.
- Source-memory immutability during scans and reviews.
- Scope isolation.
- Stable proposal identity and observation counts across repeated scans.
- Accept/dismiss decisions that do not alter source records.
- Stale detection after content revision or validity expiry.
- Bounded partial scans and validation errors.
- Cleanup of dependent proposals after explicit source deletion.

The full suite is run through GitHub Actions on Ubuntu and macOS.

## Known limitations

- This is lexical candidate discovery, not semantic contradiction detection or factual verification.
- Records are compared only within the same memory type.
- The current classifier is not embedding-based and does not yet use Knowledge Graph edges.
- Negation, numeric and similarity heuristics need a reviewed bilingual benchmark before thresholds can be treated as quality metrics.
- No automatic memory merge, rewrite, supersession, or deletion is implemented.
- No Control Center UI is wired to run scans or review proposals yet.
- There is no automatic recurring scan schedule; callers must explicitly request a scan.
- Retention policies, duplicate cluster formation, entity resolution, and conflict resolution remain future work.
