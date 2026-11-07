# Graph-Aware Memory Retrieval

**Branch:** \`oracle/phase-02-graph-aware-retrieval\`  
**Depends on:** PR #10 (memory lifecycle), PR #9 (hybrid vectors), PR #8 (episodic/procedural memory).

## Objective

Use explicitly stored Knowledge Graph links to improve memory recall when a user refers to a project or entity but does not mention the name of a relevant component, tool, person, or event.

Example:

- User asks: "How does AgriSmart work?"
- Stored graph says: \`AgriSmart —uses→ ESP32 soil sensor\`.
- Memory contains: "ESP32 soil sensor measures field moisture and temperature."
- Graph-expanded lexical search can retrieve this memory even though the user's original query never mentioned the sensor.

This is a retrieval mechanism, not automatic fact creation. It does not infer or add graph edges.

## Graph retrieval contract

\`knowledge_graph.retrieve_graph(scope, query, ...)\` returns a typed \`GraphRetrieval\`:

- \`seed_entities\`: entities matching the original query.
- \`related_entities\`: bounded incoming/outgoing neighbors, with relation type, direction, distance and stored evidence.
- \`expansion_terms\`: unique names of the seed entities and their linked neighbors.
- \`context_text\`: compact readable graph context.
- \`seed_count\` and \`relation_count\`: convenience counts.

All graph operations remain scoped to the caller's exact memory scope. The default bounds are five seed entities and twelve graph relations. The graph expansion-term list is capped at twenty names.

Only entity names are used as search expansion terms. The relation evidence is retained for provenance display, but it is not fed back into the query expansion. This prevents arbitrary evidence text from silently broadening memory search.

## Three-channel ranking

\`hybrid_memory.retrieve_memory_context\` now builds three independent ranked result lists:

1. **Lexical channel** — existing memory retrieval against the original user query.
2. **Semantic channel** — optional vector retrieval against the original user query only.
3. **Graph channel** — lexical retrieval against the original query plus explicitly linked entity names.

The channels are combined through weighted Reciprocal Rank Fusion (RRF):

| Channel | Weight | Purpose |
|---|---:|---|
| Vector/semantic | 1.00 | Semantic similarity where an embeddings model is explicitly configured |
| Lexical | 0.70 | Exact Arabic/English term overlap from the original request |
| Graph-expanded lexical | 0.45 | Recall of memories related through explicitly stored graph links |

The graph weight is deliberately lower than both other channels. A graph-expanded candidate should contribute recall, but should not overrule a direct lexical match or a strong semantic match by itself.

Each ranking channel is bounded by the existing per-category candidate limits. Result limits remain eight semantic facts/preferences/goals, four episodic events, and two validated procedures.

## Retrieval modes

The context reports one of:

- \`lexical_fallback\`: no useful vector or graph expansion channel was available.
- \`graph_lexical\`: graph names expanded lexical retrieval, without vector matches.
- \`hybrid\`: vector retrieval contributed, without graph expansion.
- \`hybrid_graph\`: both vector and graph channels contributed.

The returned context also records:

- \`semantic_match_count\`
- \`embedding_model\`
- \`graph_seed_count\`
- \`graph_relation_count\`
- \`warning_code\` for the optional embedding provider
- \`graph_warning_code\` for graph retrieval failures

A graph retrieval failure leaves the original lexical and optional semantic paths active. An embeddings provider failure leaves lexical and graph paths active. No external API is called for graph retrieval.

## AI Core integration

\`ai_core._messages_with_memory\` consumes the graph context returned by hybrid retrieval. This avoids performing a second, duplicate graph query. The previous graph renderer remains a compatibility fallback only when the hybrid-memory integration itself fails.

The graph context is explicitly labelled as stored user context, not an instruction. Entity names and relation evidence are escaped at the context boundary so stored markup cannot close the surrounding graph-context section.

## Privacy and provenance

- Entity and relation lookup always includes the exact scope in database queries.
- Expansion terms are derived only from entities reached through explicit stored edges in that scope.
- Relation evidence is displayed as stored provenance and remains untrusted context.
- Graph edges are not upgraded to factual claims about the outside world.
- The graph does not call a provider or incur embedding API cost.
- The vector channel continues embedding only the original query, not the expanded graph query.

## Validation

\`test_knowledge_graph.py\` verifies bounded, scope-isolated graph retrieval, stored relation evidence, and safe prompt-context rendering.

\`test_hybrid_memory.py\` verifies:
- Graph-expanded recall of fact, episodic event and validated procedural memory.
- Scope isolation.
- Optional graph disablement.
- Graph failure fallback.
- Relative channel weights.
- AI Core integration without duplicate graph retrieval.

The full repository test suite is run in GitHub Actions on Ubuntu and macOS for this branch. Test results are recorded in \`docs/engineering/GITHUB_DELIVERY_LOG.md\`.

## Limitations

- Graph entities and edges are still explicitly entered; no automatic extraction or entity resolution is introduced here.
- Search is bounded and lexical over entity names; it does not use a separate graph embedding model.
- Only one-hop graph neighbors are used for query expansion. The graph module supports deeper traversal, but using deeper paths risks noisy expansion and is not enabled in this ranking path.
- The graph weight is an initial conservative heuristic, not a benchmark-calibrated optimum.
- Contradictory graph edges, temporal validity of edges, and evidence freshness are not yet modelled.
- Graph-aware retrieval is not memory consolidation. Duplicate grouping, contradiction review, supersession proposals and controlled consolidation remain separate unfinished work.
