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
| Performance-based router | `model_router.py`, `model_benchmark.py`, `model_observability.py` | Evidence-gated benchmark scorecards available; route decision still follows explicit/category/tier policy | `PARTIALLY_IMPLEMENTED` | `test_model_benchmark.py`, `test_model_observability.py`; 290-test CI | Scorecards are advisory; no automatic route change until real provider data, evaluator comparability, and verified cost signals are available |
| Measured model benchmarking | `model_benchmark.py`, `model_observability.py`, `ai_executor.py` | Explicit candidate/case runs, privacy-safe outcomes, latency, optional rubric score, evaluator/suite-isolated scorecards and runtime health floor | `IMPLEMENTED_AND_VERIFIED` | `test_model_benchmark.py`, `test_multi_provider.py`; 290-test Ubuntu/macOS CI | Synthetic phrase rubric is a smoke check only; live provider quality, token usage and cost remain unmeasured |
| Sequential agent tool loop | `agent_orchestrator.py`, `bounded_correction.py` | AI Core, feature registry, local/browser/research tools | `IMPLEMENTED_AND_VERIFIED` | `test_agent_orchestrator.py`, `test_bounded_correction.py`; 313-test CI | Planner JSON repair runs before tool execution; tool actions are never replayed by the correction loop |
| Persistent DAG task engine | `durable_task_engine.py`, `database.py`, `workflow_checkpoints.py` | SQLite graph/task/dependency/attempt tables; owner-scoped encrypted payloads; lease tokens | `PARTIALLY_IMPLEMENTED` | `test_durable_task_engine.py`; CI for the current planner branch pending | Durable DAG storage, dependency gates, claims, leases, bounded retries, pause/resume/cancel and attempt history are implemented; distributed queue, worker supervision and versioned migrations remain |
| Typed task worker adapter | `task_worker.py`, `durable_task_engine.py` | Explicit per-call handler registry, lease heartbeat, cancellation polling, bounded sequential batch | `IMPLEMENTED_AND_VERIFIED` | `test_task_worker.py`; current planner-branch CI pending | Only registered types are claimable; the agent DAG adds typed specialist/reviewer handlers; no daemon or persistent worker is activated |
| Task Queue Control Center | `app.py`, `task_control_center.py`, `agent_task_execution.py` | Scope-local graph/task metadata, specialist result previews, final-review decision, pause/resume/cancel controls | `IMPLEMENTED_BUT_UNVERIFIED` | `test_task_control_center.py`, `test_agent_task_execution.py`; current planner-branch CI pending | Planner form and explicit bounded agent dispatch are integrated; live Streamlit/provider validation and dependency graph visualization remain |
| Explicit research task submission and one-shot dispatch | `task_execution.py`, `task_worker.py`, `durable_task_engine.py`, `app.py` | Encrypted owner-scoped DAG, Deep Research, explicit UI invocation | `IMPLEMENTED_BUT_UNVERIFIED` | `test_task_execution.py`; offline mocked handler integration; full CI pending | Live provider and deployed Streamlit end-to-end validation; no background worker or automatic retry |
| Specialist agent contracts | `agent_profiles.py`, `agent_task_execution.py`, `agent_orchestrator.py` | Provider layer, encrypted DAG task engine | `IMPLEMENTED_AND_VERIFIED` | `test_agent_task_execution.py`, `test_agent_revision_loop.py`; run `42469959196`, 379-test Ubuntu/macOS CI | Typed researcher/coder/writer tasks, encrypted outputs, issue-to-source-task mapping, selective revision, merged-result review and a two-cycle cap pass deterministic tests; live provider quality/cost validation remains |
| Bounded supervisor/delegation | `agent_orchestrator.py`, `agent_task_execution.py` | Typed DAG, task dependencies, explicit bounded batch, revision lineage | `PARTIALLY_IMPLEMENTED` | `test_agent_orchestrator.py`, `test_agent_task_execution.py`, `test_agent_revision_loop.py`; revision-branch CI pending | Static specialist DAG, dependency-aware execution and a two-cycle selective revision loop are implemented; dynamic delegation, parallel/distributed scheduling and physical deployment validation remain |
| Deep research | `deep_research.py`, `search.py`, `bounded_correction.py` | Search providers, AI Core, page extraction, deterministic answer/citation validation | `IMPLEMENTED_BUT_UNVERIFIED` | `test_deep_research.py`, `test_bounded_correction.py` | One bounded synthesis repair for structure/citation issues; live-source quality and factual truth remain unverified |
| Bounded self-correction | bounded_correction.py, agent_orchestrator.py, deep_research.py | One retry by default, hard cap of two, repeated-output/issue loop prevention, non-retryable provider errors | IMPLEMENTED_AND_VERIFIED | test_bounded_correction.py, test_agent_orchestrator.py, test_deep_research.py; 313-test Ubuntu/macOS CI | Text-only planner/synthesis repair before accepting output; no retries of tool execution, local writes/deletes, browser/search or approvals |
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
| Workflow metadata ledger | `workflow_ledger.py`, `durable_task_engine.py` | SQLite workflow and task tables | `IMPLEMENTED_AND_VERIFIED` | `test_workflow_ledger.py` | Link digest-only traces to durable graph/task IDs and worker state transitions |
| Encrypted workflow checkpoint | `workflow_checkpoints.py`, `durable_task_engine.py` | Fernet key, owner-scope binding and SQLite | `IMPLEMENTED_AND_VERIFIED` | `test_workflow_checkpoints.py`, encrypted task-payload tests | Reusable owner-bound encryption helpers now protect durable task payloads/results; key rotation and versioned migrations remain |
| Durable task queue | `durable_task_engine.py`, `task_worker.py` | SQLite, encrypted scoped payloads/results, leases | `PARTIALLY_IMPLEMENTED` | `test_durable_task_engine.py`, `test_task_worker.py` | Atomic claims, dependency gates, leases, bounded retries and cancellation exist; distributed queue, priorities and supervised background workers remain out of scope |
| Model telemetry | `model_observability.py`, `ai_executor.py` | SQLite, execution events | `IMPLEMENTED_AND_VERIFIED` | `test_model_observability.py` | Add token/cost and task-quality correlation where available |
| Cost intelligence | No integrated cost ledger identified | Provider usage metadata/pricing inputs | `PLANNED` | No cost evaluation tests found | Capture actual usage where providers expose it; label estimates |
| Local Mac tools | `local_tools.py` | macOS user account and OS permissions | `IMPLEMENTED_BUT_UNVERIFIED` | `test_local_tools.py` | Physical Mac execution and platform-permission validation |
| Mac policy engine | `mac_intelligence.py`, `execution_policy.py`, `local_tools.py` | Trusted-workspace allowlists, exact single-use grants, owner-scoped approval queue | `PARTIALLY_IMPLEMENTED` | `test_mac_intelligence.py`, `test_execution_policy.py`, `test_local_tools.py`, `test_agent_orchestrator.py` | Direct registered local-tool deletion is approval-gated; indirect side effects of arbitrary project scripts still require OS-level mediation |
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


## Phase 03b — Bounded self-correction

The oracle/phase-03-bounded-self-correction branch adds a shared text-only correction loop and connects it to agent planning and Deep Research synthesis.

- One retry by default; hard ceiling of two retries.
- Repeated output fingerprints, repeated validation issue signatures, provider failures and exhausted budgets stop further attempts.
- Planner JSON/tool-catalogue validation happens before any tool execution.
- Deep Research synthesis is checked for JSON shape, non-empty answer and allowed inline source citations.
- Search/page collection is not repeated for a synthesis repair.
- Local shell, browser, file, tool, approval and other side-effecting operations are outside the retry loop.

See docs/architecture/BOUNDED_SELF_CORRECTION.md. Deterministic output validation is not a general proof of semantic correctness or factual truth.


## Phase 04 — Durable DAG task engine

The `oracle/phase-04-durable-task-engine` branch introduces a persistent scheduler/state engine without adding automatic execution:

- Graph creation validates task keys, dependency references and cycles; an owner-scoped idempotency key prevents accidental duplicate graph creation.
- Task payloads and results are encrypted with the owner-scope-bound workflow checkpoint key.
- Workers explicitly claim a single ready task using a transaction-backed lease, then start, heartbeat and complete/fail it.
- Dependencies gate task readiness; failed dependencies block descendants.
- Retry is off by default. Only tasks explicitly declared `retry_safe` may be requeued, and the attempt count/backoff are bounded.
- Graph pause releases unstarted leases without consuming an execution attempt; already-running tasks remain cooperative. Cancellation changes queue state but does not forcibly undo external effects.
- The queue does not execute tools, start a worker, or install a background service.

This phase is **partially implemented** until typed worker handlers, Control Center visibility, recovery/integration tests, distributed deployment assumptions and versioned migrations are addressed. See `docs/architecture/DURABLE_TASK_ENGINE.md`.


## Phase 04b — Explicit typed task worker adapter

The `oracle/phase-04-task-worker-adapter` branch adds a synchronous one-task dispatcher and bounded sequential batches on top of the durable queue:

- Handlers are supplied explicitly by the caller in a task-type registry.
- The lease query filters to registered task types; unknown task types remain queued.
- A handler receives the decrypted task payload and a scope-bound context with heartbeat and cooperative cancellation checks.
- A dispatch processes one task; `dispatch_batch` processes at most 100 tasks and never polls/sleeps indefinitely.
- Handler exceptions are reduced to an exception class code. Retry additionally requires both a declared retryable exception class and `retry_safe=True` on the task.
- No built-in shell, browser, filesystem, app-launch or generic tool handler is registered. Tool integrations must delegate through existing Oracle execution/approval paths.

This remains partially implemented until a reviewed production handler registry, Control Center visibility, concurrency/process supervision and recovery integration are added. See `docs/architecture/TASK_WORKER_ADAPTER.md`.


## Phase 04b — Typed task worker adapter

The `oracle/phase-04-task-worker-adapter` branch adds a synchronous adapter over the durable DAG queue:

- The caller provides an explicit task-type → handler mapping; there are no built-in arbitrary command, file, browser or model handlers.
- The durable claim query can filter to registered task types. Unsupported types remain queued instead of being claimed and failed.
- A handler receives a scoped context with `heartbeat()` and `cancellation_requested()`; it never receives the lease token.
- A single dispatch processes one task. A batch processes a caller-bounded maximum of 100 tasks sequentially; it does not sleep or poll indefinitely.
- Handler retry classification is combined with the stored task's explicit retry-safe declaration and attempt limit.
- Handler exceptions are reduced to a short exception class code; free-form exception messages are not persisted.

The adapter is tested but remains `IMPLEMENTED_BUT_UNVERIFIED` until production handler wiring, a reviewed handler catalogue, Control Center operations and supervised worker lifecycle are completed. See `docs/architecture/TASK_WORKER_ADAPTER.md`.


## Phase 04c — Task Queue Control Center panel

The `oracle/phase-04-control-center-tasks` branch adds a metadata-only Task Queue section inside the existing Oracle Control Center:

- Lists graphs in the active owner scope and summarizes succeeded/failed/blocked/pending counts.
- Shows task keys/types/status, attempt counts, retry-safety flags, worker IDs and compact error codes.
- Exposes attempt history without payload/result contents.
- Allows Pause/Resume for eligible graphs and Cancel only after an explicit confirmation checkbox.
- Keeps UI projections in `task_control_center.py`, which returns explicit metadata allowlists and validates actions.

The panel does not create arbitrary tasks, invoke a worker, poll in the background, or execute tools. It is **not yet a complete operations console**; production worker supervision and handler registration remain future work. See `docs/architecture/TASK_CONTROL_CENTER.md`.


## Phase 04d — Explicit Deep Research task submission and dispatch

The `oracle/phase-04-explicit-task-dispatch` branch adds a single typed production handler for `oracle.deep_research`:

- The Control Center can create one encrypted, owner-scoped research task with bounded options and a caller-provided idempotency key.
- The task is non-retryable by default because provider calls may repeat cost or external requests.
- The handler validates an exact payload schema and calls the existing Deep Research execution path.
- The Control Center can explicitly dispatch at most one queued research task per button press; no daemon, polling loop, or persistent worker is started.
- A bounded, allowlisted result preview exposes answer/findings/citations/evidence summaries only to the matching owner scope; encrypted payloads and raw task objects remain private.

Status: `IMPLEMENTED_BUT_UNVERIFIED` pending branch CI and live-provider/deployed-UI validation. See `docs/architecture/EXPLICIT_TASK_EXECUTION.md`.


## Phase 07a — Local execution policy and deletion approval enforcement

The `oracle/phase-07-deletion-approval-enforcement` branch strengthens the Mac execution boundary:

- Read-only local operations remain approval-free.
- File writes, approved development commands and app launches can run without a separate approval only when explicitly configured by the Mac policy and scoped to trusted workspaces/allowlists.
- Moves can be automatic only when both paths are inside the same trusted workspace and the destination does not exist; overwriting an existing destination falls back to explicit approval.
- Git checkout/switch/pull commands that can replace working-tree files require explicit approval even when their argv prefixes are allowlisted.
- Deletion is always routed to the one-time owner approval path, even if a policy file lists `local.delete_path` as auto-allowed.
- `local_tools._execute` is now the shared policy boundary for direct registered local tool calls; the agent orchestrator passes an exact single-use grant bound to scope, tool ID and payload.
- The agent's encrypted checkpoint/resume approval flow is retained.

Status remains `PARTIALLY_IMPLEMENTED`: registered direct local-tool deletion is guarded and covered by deterministic tests, but the application cannot statically prove the side effects of arbitrary allowed third-party project scripts. A filesystem sandbox or equivalent OS-level mediation is still required before claiming that every indirect deletion path is blocked.

See `docs/architecture/LOCAL_EXECUTION_POLICY.md`.


## Phase 04d — Autonomous planner and specialist-agent DAG

The `oracle/phase-04-autonomous-task-planner-dag` branch connects the planner model to the durable task engine:

- The planner returns a strict JSON DAG with a bounded set of allowlisted specialist roles (`researcher`, `coder`, `writer`); unknown roles, tool identifiers, extra fields, invalid dependencies and malformed task keys are rejected.
- The application adds a mandatory `final_review` task that depends on every specialist task.
- The durable engine stores task payloads and results encrypted and owner-scope-bound; the worker executes only explicitly registered agent-step and final-review handlers.
- Dependency outputs are passed only to dependent tasks, after successful completion. A bounded dispatch batch follows the engine's dependency scheduler.
- The Control Center can create a plan, explicitly dispatch up to three ready tasks, inspect persisted specialist results, and see the final review decision.
- Pending and completed task state survives app restarts. Expired worker leases can be retried at most once for these model-only tasks; an interruption after a provider call but before persistence may repeat the provider call and incur duplicate cost.
- The final reviewer assesses request coverage and internal consistency, not factual truth. A graph marked completed is not considered accepted unless the final review decision is `accepted`.
- No shell, browser, filesystem, executor handler, daemon, LaunchAgent, or background worker is added or activated.

Status: `IMPLEMENTED_BUT_UNVERIFIED` pending current-branch CI, live provider validation, and deployed/physical-Mac UI validation. See `docs/architecture/AUTONOMOUS_AGENT_DAG.md`.


## Phase 04e — Bounded autonomous specialist revision loop

The `oracle/phase-04-bounded-agent-revision-loop` branch adds selective, lineage-aware correction after a rejected final review:

- The user explicitly requests a revision from a completed graph with `needs_revision` or `incomplete`; accepted or unfinished graphs cannot be revised.
- The revision planner maps every bounded review issue to one or more existing source task keys. Roles are derived from stored specialist results; the model cannot invent agents, task IDs, tools, or commands.
- Only selected specialists are rerun. Each receives its previous output, assigned review issues, parent dependency outputs, and any revised dependency outputs.
- New revision graphs are encrypted, owner-scoped, linked to their root and immediate parent, and have a mandatory review task over the merged effective results.
- Unchanged specialist results are inherited from the previous graph. The next review evaluates the complete merged set rather than only the changed steps.
- Deterministic root/cycle idempotency keys prevent duplicate child graphs. A stale parent cannot create a competing revision branch.
- Hard limits: two revision cycles per root graph, eight specialist tasks per cycle, and twelve review issues per cycle. Created cycles count toward the cap even if cancelled.
- The Control Center exposes revision creation separately from execution. No revision worker runs until the user explicitly dispatches a bounded batch.
- Revision agents remain content/reasoning specialists only; no shell, browser, filesystem, executor or Mac action handlers are registered.

Status: `IMPLEMENTED_AND_VERIFIED` by run `42469959196` (379 tests passed on Ubuntu and macOS). Live provider quality/cost, deployed Streamlit interaction, and physical-Mac restart validation remain outstanding. The final reviewer assesses completeness/internal consistency, not factual truth. See `docs/architecture/AUTONOMOUS_AGENT_DAG.md`.


## Phase 04f — Composed evidence-to-agent end-to-end workflow

| Increment | Owning modules | Status on this branch | Verified scope | Remaining work |
|---|---|---|---|---|
| Evidence research task composition | `task_execution.py`, `agent_task_execution.py` | `IMPLEMENTED_AND_VERIFIED` | A validated Deep Research task can be composed into the same encrypted specialist DAG; research is a prerequisite for every specialist and final review | CI run `42471524130`: 381 passed on Ubuntu/macOS; live search/provider validation |
| Evidence handoff to specialists | `agent_task_execution.py` | `IMPLEMENTED_AND_VERIFIED` | Only allowlisted bounded report fields are projected to dependent specialists; research evidence is inherited across revision lineage and excluded from revision-target candidates | Live-provider quality and cost validation remain outstanding; strict result-size limits are tested |
| Control Center evidence projection | `app.py`, `agent_task_execution.py` | `IMPLEMENTED_AND_VERIFIED` | UI can show the persisted evidence answer, evidence summary, limitations and validated HTTP(S) citations alongside specialist outputs | Live Streamlit browser validation remains outstanding |
| End-to-end regression | `test_oracle_e2e.py` | `IMPLEMENTED_AND_VERIFIED` | Offline test exercises memory context, encrypted graph creation, mocked research, specialist dependency handoff, reviewer rejection, selective revision, merged result projection and owner-scoped Control Center metadata | CI run `42471524130`: 381 passed per platform; live provider run remains a separate opt-in operation |

The composed path remains explicitly dispatched by the user. Research uses bounded query/source settings and a non-retryable task. The final reviewer assesses request coverage and internal consistency, not factual truth. See `docs/testing/ORACLE_END_TO_END.md`.
