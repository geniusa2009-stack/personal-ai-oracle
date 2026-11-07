# Personal AI Oracle — Capability Matrix

**Baseline snapshot ref:** `feature/oracle-answer-quality-benchmark`  
**Baseline snapshot SHA:** `0763f14e006554cb20af4a22526394a4d4ce0ade`  
**Baseline reviewed:** 2026-11-07 UTC  
**Baseline incremental update:** `oracle/phase-01-evidence-foundation`  
**Current update:** `oracle/phase-01-semantic-verifier` (CI passed on head `2592d1818e4753a350f1d223bfb356b2b2736bb8`; documentation update may trigger a fresh CI run)

This matrix records evidence-backed status, not product aspirations. A module's existence or a feature registry label is not sufficient to mark a capability complete.

## Status definitions

- `IMPLEMENTED_AND_VERIFIED`: implementation, relevant tests, and an identifiable execution path are present in the inspected repository.
- `IMPLEMENTED_BUT_UNVERIFIED`: implementation exists, but a required real integration or operational scenario has not been verified.
- `PARTIALLY_IMPLEMENTED`: a useful subset exists, but major requirements or integrations remain.
- `UI_ONLY`: the UI is present without proven working backend execution.
- `DISCONNECTED`: code exists but is not connected to the main execution path.
- `PLANNED`: not evidenced as implemented in the audited revision.
- `BROKEN`: known failing implementation or integration, supported by evidence.
- `NOT_FOUND`: no implementation was found in the inspected inventory.

## Capability inventory

| Capability | Owning modules / entry points | Dependencies | Status | Test evidence | Remaining work |
|---|---|---|---|---|---|
| AI request contract | `ai_request.py` | Python dataclasses, validation | `IMPLEMENTED_AND_VERIFIED` | `test_ai_core_provider.py`, `test_multi_provider.py` | Expand contract tests when new metadata is added |
| Provider adapters | `llm_provider.py`, `ai_executor.py` | Provider APIs, environment config | `IMPLEMENTED_AND_VERIFIED` | `test_ai_core_provider.py`, `test_multi_provider.py` | Live credential/provider contract tests remain optional |
| Role-specific profiles | `agent_profiles.py`, `ai_core.py` | Environment configuration | `IMPLEMENTED_AND_VERIFIED` | Covered by multi-provider/core tests | Add role capability validation and UI diagnostics |
| Deterministic router | `model_router.py`, `ai_core.py` | Profile and environment config | `IMPLEMENTED_AND_VERIFIED` | `test_ai_core_provider.py`, `test_multi_provider.py` | Add task complexity and capability-aware route policies |
| Performance-based router | `model_router.py`, `model_benchmark.py`, `model_observability.py` | Evidence-gated benchmark scorecards available; route decision still follows explicit/category/tier policy | `PARTIALLY_IMPLEMENTED` | `test_model_benchmark.py`, `test_model_observability.py`; 288-test CI | Scorecards are advisory; no automatic route change until real provider data, evaluator comparability, and verified cost signals are available |
| Measured model benchmarking | `model_benchmark.py`, `model_observability.py`, `ai_executor.py` | Explicit candidate/case runs, privacy-safe outcomes, latency, optional rubric score, evaluator/suite-isolated scorecards and runtime health floor | `IMPLEMENTED_AND_VERIFIED` | `test_model_benchmark.py`, `test_multi_provider.py`; 288-test Ubuntu/macOS CI | Synthetic phrase rubric is a smoke check only; live provider quality, token usage and cost remain unmeasured |
| Sequential agent tool loop | `agent_orchestrator.py` | AI Core, feature registry, local/browser/research tools | `IMPLEMENTED_AND_VERIFIED` | `test_agent_orchestrator.py` | Evolve without breaking existing bounded behavior |
| Persistent DAG task engine | Not present as a complete subsystem | DB, queue, checkpoint, tool registry | `PLANNED` | Ledger/checkpoint tests are not task-engine tests | Durable task/step state, dependency graph, retries, cancellation, resume |
| Specialist agent contracts | `agent_profiles.py`, `agent_orchestrator.py` | Provider layer | `PARTIALLY_IMPLEMENTED` | Role routing and orchestrator tests | Typed agent inputs/outputs and delegated lifecycle |
| Bounded supervisor/delegation | `agent_orchestrator.py` | Tool catalog, execution policy | `PARTIALLY_IMPLEMENTED` | `test_agent_orchestrator.py` | Multi-agent delegation, depth/concurrency limits, shared task state |
| Deep research | `deep_research.py`, `search.py` | Search providers, AI Core, page extraction | `IMPLEMENTED_BUT_UNVERIFIED` | `test_deep_research.py` | Live-source evaluation and research workflow e2e tests |
| Citation integrity assessment | `answer_quality.py`, `deep_research.py` | Source IDs, final answer claims | `IMPLEMENTED_AND_VERIFIED` | `test_answer_quality.py`, `test_deep_research.py` | Maintain explicit non-entailment limitation |
| Semantic claim verification | `semantic_verifier.py`, `deep_research.py` | Reviewer model, cited evidence excerpts, validated response contract | `IMPLEMENTED_BUT_UNVERIFIED` | `test_semantic_verifier.py`, `test_deep_research.py` | Bounded reviewer-model assessment for cited evidence; requires extracted-page evidence for decisive labels; never proves factual truth; CI for this branch pending |
| Evidence provenance store | Research source objects only; no complete normalized evidence subsystem verified | Source extraction, DB persistence | `PARTIALLY_IMPLEMENTED` | Deep-research tests | Normalize source metadata and claim/source edges; define persistence policy |
| Source contradiction detection | `evidence_verification.py` | Explicit structured subject/predicate/object input | `PARTIALLY_IMPLEMENTED` | `test_evidence_verification.py` | Currently generates potential conflicts only for already-structured claims; no free-text extraction or end-to-end research report integration |
| Domain-aware research freshness | `freshness_policy.py`, `evidence_verification.py`, `deep_research.py` | Publisher/update date metadata and explicit or query-hint policy | `PARTIALLY_IMPLEMENTED` | `test_freshness_policy.py`, `test_deep_research.py` | Integrated per-source freshness labels and report summary; initial heuristic thresholds need calibration; source date authority and supersession are not verified |
| Citation benchmark | `answer_quality_benchmark.py`, `benchmarks/answer_quality_cases.json` | Deterministic fixtures | `IMPLEMENTED_AND_VERIFIED` | `test_answer_quality_benchmark.py`, latest PR #3 CI | Expand beyond 10 synthetic citation-classification cases |
| Representative research benchmark | Not present | Human-reviewed bilingual annotations | `PLANNED` | Synthetic baseline only | Arabic/English evidence and semantic support dataset |
| Explicit fact/preference/goal memory | `memory.py` | SQLite `memories` table; legacy `MemoryRecord` API retained | `IMPLEMENTED_AND_VERIFIED` | `test_memory.py`, `test_memory_retrieval.py` | Add episodic/semantic categorization across more entity types |
| Memory lifecycle metadata | `memory_lifecycle.py`, `memory.py`, `database.py` | SQLite `memory_metadata`: confidence, importance, validity window, access count/time, active/superseded state | `IMPLEMENTED_AND_VERIFIED` | `test_memory_lifecycle.py`; 259-test Ubuntu/macOS CI | Manual metadata, temporal filtering, retrieval weighting and legacy backfill verified; automatic confidence estimation and retention policy remain out of scope |
| Memory revision history | `memory_lifecycle.py`, `database.py` | Append-only snapshots with content hash, metadata snapshot, reason, actor, timestamp | `IMPLEMENTED_AND_VERIFIED` | `test_memory_lifecycle.py`; 259-test Ubuntu/macOS CI | Content revisions create a replacement record and supersede the old record; explicit deletion clears linked history and vector cache |
| Episodic memory | `memory_layers.py`, `ai_core.py` | SQLite `memory_events`, explicit source/time metadata, lexical retrieval | `IMPLEMENTED_AND_VERIFIED` | `test_memory_layers.py`; full 259-test CI | Explicit event capture and bounded scope-local retrieval verified; no automatic extraction or graph linking |
| Procedural memory | `memory_layers.py`, `ai_core.py` | SQLite `memory_procedures`, explicit validation status, outcome counters | `IMPLEMENTED_AND_VERIFIED` | `test_memory_layers.py`; full 259-test CI | Candidate procedures require explicit validation before retrieval; no automatic promotion or generalized history |
| Hybrid/vector/graph retrieval | `memory_embeddings.py`, `hybrid_memory.py`, `knowledge_graph.py`, `ai_core.py` | Lexical + optional vectors + scoped graph expansion; weighted RRF; graph relation evidence | `IMPLEMENTED_AND_VERIFIED` | `test_hybrid_memory.py`, `test_knowledge_graph.py`; 267-test Ubuntu/macOS CI | Graph-linked names expand fact/event/validated-procedure retrieval with lower RRF weight; real embedding provider compatibility and ranking calibration remain unverified |
| Explicit knowledge graph | `knowledge_graph.py`, `hybrid_memory.py` | SQLite scope-bound entity/relation tables, stored relation evidence, bounded graph expansion | `IMPLEMENTED_AND_VERIFIED` | `test_knowledge_graph.py`, `test_hybrid_memory.py`; 267-test Ubuntu/macOS CI | Explicit graph edges now contribute bounded retrieval candidates and provenance; temporal/versioned graph edges remain planned |
| Automatic graph extraction | Not evidenced as integrated | Claim/entity extraction and provenance | `PLANNED` | Explicit graph write tests only | Evidence-backed entity resolution and relation extraction |
| Memory consolidation | `memory_consolidation.py`, `database.py`, `memory.py` | Bounded scope-local candidate discovery; duplicate/related/possible-contradiction proposals; review status and source hashes; scan observations | `IMPLEMENTED_AND_VERIFIED` | `test_memory_consolidation.py`; 276-test Ubuntu/macOS CI | Review-only proposals; no auto-merge/delete; source changes, supersession or expiry surface stale proposals; semantic contradiction verification, entity resolution and retention remain out of scope |
| Workflow metadata ledger | `workflow_ledger.py` | SQLite workflow tables | `IMPLEMENTED_AND_VERIFIED` | `test_workflow_ledger.py` | Link the trace to durable task plans and state transitions |
| Encrypted workflow checkpoint | `workflow_checkpoints.py` | Fernet key and SQLite | `IMPLEMENTED_AND_VERIFIED` | `test_workflow_checkpoints.py` | Generalize to task resume; review automatic expired-record deletion |
| Durable task queue | No complete queue identified | Persistent task table, scheduler/worker | `PLANNED` | No queue-specific test suite found | Atomic claims, leases, retries, priorities, cancellation |
| Model telemetry | `model_observability.py`, `ai_executor.py` | SQLite, execution events | `IMPLEMENTED_AND_VERIFIED` | `test_model_observability.py` | Add token/cost and task-quality correlation where available |
| Cost intelligence | No integrated cost ledger identified | Provider usage metadata/pricing inputs | `PLANNED` | No cost evaluation tests found | Capture actual usage where providers expose it; label estimates |
| Local Mac tools | `local_tools.py` | macOS user account and OS permissions | `IMPLEMENTED_BUT_UNVERIFIED` | `test_local_tools.py` | Physical Mac execution and platform-permission validation |
| Mac policy engine | `mac_intelligence.py`, `execution_policy.py` | Local JSON policy, owner-scoped approvals | `PARTIALLY_IMPLEMENTED` | `test_mac_intelligence.py`, `test_execution_policy.py` | Align all operations with owner policy; enforce deletion approval at every path |
| Cloud control plane | `cloud_control.py` | FastAPI, DB/config, HTTPS deployment | `IMPLEMENTED_BUT_UNVERIFIED` | `test_hybrid_runtime.py` | Live deployment, pairing and operational recovery validation |
| Mac cloud agent | `cloud_agent.py`, `cloud_client.py` | Local runtime, device token, API | `IMPLEMENTED_BUT_UNVERIFIED` | `test_hybrid_runtime.py` | Physical device enrollment, network interruption and sleep/wake tests |
| Isolated browser | `web_browser.py` | Playwright, browser install, network guard | `IMPLEMENTED_BUT_UNVERIFIED` | Hybrid/browser-related tests where present | Validate Chromium setup and actual browser workflow on Mac |
| Streamlit Control Center | `app.py` | Streamlit, Oracle modules | `PARTIALLY_IMPLEMENTED` | Existing app/core tests | Verify and expose live task, memory, research, agent and model state |
| Legacy feature registry | `features.py`, `feature_hub.py` | Feature-specific services | `PARTIALLY_IMPLEMENTED` | Partial feature tests | Audit each feature's actual execution and configuration |
| Database initialization | `db.py`, `database.py` | SQLite | `IMPLEMENTED_BUT_UNVERIFIED` | DB-backed module tests | Versioned migrations, upgrade and restore tests |
| Versioned migrations | Not found in inspected tree | Migration framework/process | `PLANNED` | No migration suite identified | Add migration versioning and backward-compatible upgrades |
| CI Ubuntu/macOS | `.github/workflows/ci.yml` | GitHub Actions, Python 3.11 | `IMPLEMENTED_AND_VERIFIED` | Latest PR #3 workflow runs successful | Add lint/type/security/migration/e2e jobs where supported |
| Full physical-device validation | External operational activity | Owner's Mac and configured services | `NOT_FOUND` in repository evidence | Not performed by this audit | Execute a separately approved device validation plan |

## Key integration paths

### AI request path

`app / agent / capability → ai_core.chat → memory retrieval + graph context → AIRequest → ModelRouter → AIExecutor → provider adapter → response`

### Agent tool path

`agent_orchestrator → available tool catalog → validated one-step plan → policy/preflight → tool executor → observed result → next plan`

### Research path

`deep_research → multi-query planning → search → source normalization/deduplication → selected page extraction → synthesis with source IDs → answer_quality citation assessment`

### Memory path

`ai_core memory_scope → memory.retrieve_memories + memory_layers.retrieve_events/retrieve_procedures + knowledge_graph.retrieve_context → bounded JSON/context injection`

### Local/cloud path

`cloud dashboard/control plane ↔ authenticated Mac polling agent → local runtime/tool execution`

These are code-level paths; live deployed behavior must be verified independently.

## Immediate engineering priorities

1. Complete claim extraction and evidence-backed semantic verification.
2. Introduce normalized evidence and claim/source relationships.
3. Add contradiction and temporal freshness logic.
4. Add episodic/procedural memory and hybrid retrieval. (Episodic/procedural storage and an opt-in lexical/vector retrieval path are now implemented in stacked PRs; broader memory metadata, graph fusion, and consolidation remain.)
5. Build durable task state and restart-safe execution.
6. Add typed specialist-agent delegation on top of the task engine.
7. Extend telemetry and benchmarks to quality, latency and cost.
8. Align Mac execution policy with the owner's explicit approval contract.
9. Expand integration/e2e/operational validation and Control Center visibility.

See `docs/architecture/REPOSITORY_AUDIT.md` for methodology, limitations, GitHub state, and rationale.


## Phase 01 evidence-foundation increment

The `oracle/phase-01-evidence-foundation` branch adds the following additive capabilities. Their status remains `IMPLEMENTED_BUT_UNVERIFIED` until the branch's own Ubuntu/macOS CI completes.

| New increment | Owning module | Status before | Status on this branch | Scope and limitation |
|---|---|---|---|---|
| Structured evidence provenance | `evidence_verification.py`, `deep_research.py` | `PARTIALLY_IMPLEMENTED` | `IMPLEMENTED_BUT_UNVERIFIED` | Normalizes source IDs, URLs, publisher/domain hints, evidence level, and separate source-date timestamps |
| Sentence-level claim candidates | `evidence_verification.py`, `deep_research.py` | `PLANNED` | `IMPLEMENTED_BUT_UNVERIFIED` | Creates bounded sentence candidates with citations; not atomic semantic claim extraction |
| Source freshness assessment primitive | `evidence_verification.py` | `PLANNED` | `IMPLEMENTED_BUT_UNVERIFIED` | Requires explicit max-age policy; uses updated/published date, never retrieval time |
| Structured contradiction candidate detector | `evidence_verification.py` | `PLANNED` | `IMPLEMENTED_BUT_UNVERIFIED` | Flags same-subject/same-predicate/different-value structured pairs for review; no free-text inference or semantic verdict |

The broader semantic verifier, domain policy registry, persistent evidence store, human-reviewed dataset, and live operational validation remain planned. See `docs/architecture/EVIDENCE_VERIFICATION.md`.


## Phase 01 — Semantic verifier increment

The `oracle/phase-01-semantic-verifier` branch builds on PR #5 with a bounded model-assisted semantic evidence assessor.

| New increment | Owning modules | Status on this branch | Scope and limitations |
|---|---|---|---|
| Model-assisted claim/evidence assessment | `semantic_verifier.py`, `deep_research.py` | `IMPLEMENTED_BUT_UNVERIFIED` | Reviews at most 12 sentence-level candidates, only against their cited evidence; schema/ID validation; model failures leave claims unverified |
| Evidence-strength enforcement | `semantic_verifier.py` | `IMPLEMENTED_BUT_UNVERIFIED` | Snippet-only, unavailable, and empty page evidence cannot yield decisive supported/contradicted/partial/conflicting labels |
| Research report integration | `deep_research.py` | `IMPLEMENTED_BUT_UNVERIFIED` | Separate `semantic_verification` object; citation-integrity assessment remains unchanged; factual truth is always reported as not verified |

The following remain incomplete: atomic claim extraction, domain-specific freshness policy integration, free-text contradiction resolution, a persistent evidence store, and a human-reviewed bilingual benchmark. See `docs/architecture/SEMANTIC_VERIFICATION.md`.


### Phase 01b validation update

- Latest verified Phase 01b code head: `2592d1818e4753a350f1d223bfb356b2b2736bb8`.
- GitHub Actions run `42396961333` completed successfully.
- Ubuntu: **213 passed, 1 warning**.
- macOS: **213 passed, 1 warning**.
- The warning is the existing Starlette/httpx TestClient deprecation warning.
- This validates the configured CI suite for this commit. It does not validate a live provider call, a physical Mac, cloud deployment, or factual truth of model assessments.


## Phase 01c — Domain-aware freshness policy

The `oracle/phase-01-temporal-evidence` branch adds the following integrated capability; CI is pending for this branch.

| Increment | Owning modules | Status | Evidence and scope | Remaining work |
|---|---|---|---|---|
| Domain freshness profiles | `freshness_policy.py` | `IMPLEMENTED_BUT_UNVERIFIED` | General, scholarship deadline, event schedule, pricing, government policy, software API, and scientific research profiles | Calibrate initial age thresholds; add settings-based customization and source/jurisdiction overrides |
| Conservative query-hint selection | `freshness_policy.py` | `IMPLEMENTED_BUT_UNVERIFIED` | Bilingual keyword hints; explicit profile override; generic queries remain unassessed | Improve ambiguity handling using reviewed query cases |
| Deep Research freshness integration | `deep_research.py` | `IMPLEMENTED_BUT_UNVERIFIED` | Per-source and citation freshness, top-level assessment, compact report summary, stale/unknown/future-date limitations | Test against real source date providers and UI display |
| Temporal conflict resolution | `evidence_verification.py` structured candidates only | `PARTIALLY_IMPLEMENTED` | Structured same-subject/predicate conflicts with temporal overlap checks | No atomic free-text extraction, source supersession model, or integrated research review workflow |

Freshness compares publisher/update date metadata, not retrieval time. A stale source is not necessarily false. See `docs/architecture/FRESHNESS_POLICY.md`.


## Phase 02 — Episodic and procedural memory increment

The `oracle/phase-02-memory-evolution` branch adds:

| Increment | Owning modules | Status on this branch | Scope and limitations |
|---|---|---|---|
| Episodic event storage | `memory_layers.py`, `database.py` | `IMPLEMENTED_BUT_UNVERIFIED` | Explicit scope-bound events with summary, details, source, occurred/recorded timestamps and deterministic duplicate detection |
| Episodic retrieval | `memory_layers.py`, `ai_core.py` | `IMPLEMENTED_BUT_UNVERIFIED` | Bounded lexical relevance; no unrelated recent-event injection when query tokens are absent |
| Procedural candidate storage | `memory_layers.py`, `database.py` | `IMPLEMENTED_BUT_UNVERIFIED` | Explicit workflow name/description/steps and provenance; new entries start as candidates |
| Validated procedure retrieval | `memory_layers.py`, `ai_core.py` | `IMPLEMENTED_BUT_UNVERIFIED` | Only procedures explicitly marked `validated` are included in AI context; outcome counts do not automatically validate |
| Additive schema initialization | `database.py` | `IMPLEMENTED_BUT_UNVERIFIED` | Adds event/procedure tables without rewriting legacy `memories` rows; not a general migration framework |
| Memory prompt integration | `ai_core.py` | `IMPLEMENTED_BUT_UNVERIFIED` | Bounded JSON context; markup delimiters are escaped; new memory-layer failures are fail-soft |

Vector retrieval, cross-layer semantic ranking, automatic memory extraction, consolidation/version history, and graph links remain planned. See `docs/architecture/MEMORY_ARCHITECTURE.md`.


## Phase 02b — Optional hybrid vector retrieval

The `oracle/phase-02-hybrid-retrieval` branch adds:

| Increment | Owning modules | Status | Scope | Remaining work |
|---|---|---|---|---|
| Provider-independent embedding interface | `memory_embeddings.py` | `IMPLEMENTED_BUT_UNVERIFIED` | Protocol plus OpenAI-compatible `/embeddings` client; default local Ollama profile; hosted provider is explicit | Live endpoint compatibility and model evaluation |
| Scope-isolated vector cache | `memory_embeddings.py`, `database.py` | `IMPLEMENTED_BUT_UNVERIFIED` | SQLite vector records keyed by scope/type/record/model, hash checked, bounded indexing | Index lifecycle/refresh observability and large-scale performance tests |
| Hybrid lexical/vector ranking | `hybrid_memory.py` | `IMPLEMENTED_BUT_UNVERIFIED` | RRF fusion with weak cosine matches filtered; lexical fallback if disabled, unindexed or unavailable | Calibrate score threshold on reviewed bilingual retrieval benchmark |
| AI Core integration | `ai_core.py` | `IMPLEMENTED_BUT_UNVERIFIED` | Uses hybrid retrieval where configured, preserving base lexical path and existing graph/event/procedure context | Verify UI controls and report retrieval mode/metrics |
| Offline regression tests | `test_hybrid_memory.py` | `IMPLEMENTED_BUT_UNVERIFIED` | Fake vectors, provider response validation, scope isolation, stale-vector rejection, lexical fallback | CI must pass on current branch head |

The feature is opt-in via `ORACLE_MEMORY_EMBEDDINGS_ENABLED=1` and a configured model. Auto-indexing defaults off. See `docs/architecture/HYBRID_MEMORY_RETRIEVAL.md`.


## Phase 02c — Memory lifecycle metadata and revision history

The `oracle/phase-02-memory-lifecycle` branch adds additive SQLite metadata and revision tables while retaining the legacy `MemoryRecord` fields and API shape.

- New memories receive explicit default confidence and importance values of 0.5, an initial validity start, and a `created` history event.
- Historical memory rows are backfilled with neutral metadata and a `legacy_baseline` history event on database initialization.
- Retrieval excludes superseded and out-of-validity records, and weights lexical relevance by confidence and importance.
- Selected retrieval results increment access counters and update last-accessed timestamps; routine access does not create noisy revision entries.
- Metadata edits append a snapshot and require a reason and actor.
- Content revisions insert a new record and mark the old record as superseded; the old content is not overwritten.
- Listing hides superseded records by default; callers may explicitly request them for history/review.
- Explicit memory deletion removes corresponding metadata, revision snapshots and vector-cache rows. The explicit deletion approval must be enforced by the invoking UI/tool policy.

Implementation is being validated by `test_memory_lifecycle.py`; no completion claim is made until CI passes on Ubuntu and macOS. See `docs/architecture/MEMORY_LIFECYCLE.md`.


## Phase 02d — Graph-aware memory retrieval

The `oracle/phase-02-graph-aware-retrieval` branch adds a third retrieval channel:

- The current query finds seed entities in the same memory scope.
- Explicitly linked neighbors contribute entity-name expansion terms.
- The expanded query runs the existing lexical search for semantic facts, episodic events, and validated procedures.
- A weighted RRF channel combines graph-expanded results with original lexical and optional vector results.
- Graph channel weight is `0.45`; lexical is `0.7`; vector is `1.0`.
- Relation evidence is preserved and included in the prompt context as stored provenance, not treated as an instruction or proof of an answer.
- Graph retrieval is bounded by entity and relation counts; provider outages do not disable graph or lexical retrieval.
- Graph expansion can be disabled explicitly for deterministic baseline comparisons.

This closes the graph-aware *retrieval/ranking* part of Phase 2, not all knowledge-graph work. Temporal edge validity, graph conflict handling, graph-aware consolidation and large-scale ranking calibration remain unfinished.


## Phase 03 — Measured model benchmarking

The `oracle/phase-03-model-benchmarking` branch adds:

- A synthetic, deterministic smoke suite with bounded arithmetic, classification, Arabic instruction-following and simple factual questions.
- Explicit provider/model candidate matrices with an opt-in remote-call gate.
- Privacy-safe persisted results: latency, outcome, output length, case ID, evaluator ID and optional numeric quality score; no prompt/completion storage.
- Scorecards separated by evaluator ID so incompatible metrics are not combined.
- Minimum sample and scored-case thresholds before a model becomes recommendation-eligible.
- Conservative use of runtime telemetry: lower observed success rate and higher observed p95 latency are used when sufficient operational samples exist.
- Ranking is advisory and does not change `ModelRouter` automatically.

See `docs/architecture/MODEL_BENCHMARKING.md`. Cost and token usage are not guessed; the provider adapters must first expose verified usage metadata. Live provider benchmarking has not been executed in CI.
