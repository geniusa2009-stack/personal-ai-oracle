# Personal AI Oracle — Capability Matrix

**Snapshot ref:** `feature/oracle-answer-quality-benchmark`  
**Snapshot SHA:** `0763f14e006554cb20af4a22526394a4d4ce0ade`  
**Last reviewed:** 2026-11-07 UTC

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
| Performance-based router | `model_router.py`, `model_observability.py` | Benchmarks, persisted metrics | `PLANNED` | No integrated quality-feedback routing test found | Persist benchmark outcomes and measured cost; add safe selection policy |
| Sequential agent tool loop | `agent_orchestrator.py` | AI Core, feature registry, local/browser/research tools | `IMPLEMENTED_AND_VERIFIED` | `test_agent_orchestrator.py` | Evolve without breaking existing bounded behavior |
| Persistent DAG task engine | Not present as a complete subsystem | DB, queue, checkpoint, tool registry | `PLANNED` | Ledger/checkpoint tests are not task-engine tests | Durable task/step state, dependency graph, retries, cancellation, resume |
| Specialist agent contracts | `agent_profiles.py`, `agent_orchestrator.py` | Provider layer | `PARTIALLY_IMPLEMENTED` | Role routing and orchestrator tests | Typed agent inputs/outputs and delegated lifecycle |
| Bounded supervisor/delegation | `agent_orchestrator.py` | Tool catalog, execution policy | `PARTIALLY_IMPLEMENTED` | `test_agent_orchestrator.py` | Multi-agent delegation, depth/concurrency limits, shared task state |
| Deep research | `deep_research.py`, `search.py` | Search providers, AI Core, page extraction | `IMPLEMENTED_BUT_UNVERIFIED` | `test_deep_research.py` | Live-source evaluation and research workflow e2e tests |
| Citation integrity assessment | `answer_quality.py`, `deep_research.py` | Source IDs, final answer claims | `IMPLEMENTED_AND_VERIFIED` | `test_answer_quality.py`, `test_deep_research.py` | Maintain explicit non-entailment limitation |
| Semantic claim verification | Not present as integrated verifier | Claim extraction, evidence store, entailment evaluator | `PLANNED` | Current assessment explicitly sets semantic support to not evaluated | Claim-level structured evidence and verification statuses |
| Evidence provenance store | Research source objects only; no complete normalized evidence subsystem verified | Source extraction, DB persistence | `PARTIALLY_IMPLEMENTED` | Deep-research tests | Normalize source metadata and claim/source edges; define persistence policy |
| Source contradiction detection | Not found as integrated engine | Claim normalization, temporal evidence | `PLANNED` | No dedicated contradiction test suite found | Distinguish true contradictions from temporal/definition differences |
| Temporal freshness engine | Not found as integrated engine | Published/updated/retrieved timestamps | `PLANNED` | No dedicated freshness tests found | Domain-specific freshness policies and stale labels |
| Citation benchmark | `answer_quality_benchmark.py`, `benchmarks/answer_quality_cases.json` | Deterministic fixtures | `IMPLEMENTED_AND_VERIFIED` | `test_answer_quality_benchmark.py`, latest PR #3 CI | Expand beyond 10 synthetic citation-classification cases |
| Representative research benchmark | Not present | Human-reviewed bilingual annotations | `PLANNED` | Synthetic baseline only | Arabic/English evidence and semantic support dataset |
| Explicit fact/preference/goal memory | `memory.py` | SQLite `memories` table | `IMPLEMENTED_AND_VERIFIED` | `test_memory.py`, `test_memory_retrieval.py` | More lifecycle metadata and memory categories |
| Episodic memory | No dedicated integrated implementation found | Task/event lifecycle | `PLANNED` | No dedicated episodic tests found | Durable event records with links to tasks and outcomes |
| Procedural memory | No dedicated integrated implementation found | Validated workflow outcomes | `PLANNED` | No dedicated procedural tests found | Store and retrieve validated reusable procedures |
| Hybrid/vector retrieval | `memory.py` currently lexical | Embedding provider, vector index, fallback | `PLANNED` | Lexical retrieval tests only | Optional vectors, hybrid ranking, deterministic offline fallback |
| Explicit knowledge graph | `knowledge_graph.py` | SQLite entity/relation tables | `IMPLEMENTED_AND_VERIFIED` | `test_knowledge_graph.py` | Temporal/versioned graph edges and evidence lifecycle |
| Automatic graph extraction | Not evidenced as integrated | Claim/entity extraction and provenance | `PLANNED` | Explicit graph write tests only | Evidence-backed entity resolution and relation extraction |
| Memory consolidation | No integrated lifecycle engine found | Memory versions, conflict and retention policy | `PLANNED` | No dedicated lifecycle tests found | Deduplication, supersession, conflict review and retention rules |
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

`ai_core memory_scope → memory.retrieve_memories + knowledge_graph.retrieve_context → bounded context injection`

### Local/cloud path

`cloud dashboard/control plane ↔ authenticated Mac polling agent → local runtime/tool execution`

These are code-level paths; live deployed behavior must be verified independently.

## Immediate engineering priorities

1. Complete claim extraction and evidence-backed semantic verification.
2. Introduce normalized evidence and claim/source relationships.
3. Add contradiction and temporal freshness logic.
4. Add episodic/procedural memory and hybrid retrieval.
5. Build durable task state and restart-safe execution.
6. Add typed specialist-agent delegation on top of the task engine.
7. Extend telemetry and benchmarks to quality, latency and cost.
8. Align Mac execution policy with the owner's explicit approval contract.
9. Expand integration/e2e/operational validation and Control Center visibility.

See `docs/architecture/REPOSITORY_AUDIT.md` for methodology, limitations, GitHub state, and rationale.
