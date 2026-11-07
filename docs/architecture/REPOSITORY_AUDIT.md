# Personal AI Oracle — Repository Architecture Audit

**Audit snapshot:** 2026-11-07 (UTC)  
**Audited ref:** `feature/oracle-answer-quality-benchmark`  
**Audited commit:** `0763f14e006554cb20af4a22526394a4d4ce0ade`  
**Audit delivery branch:** `oracle/phase-00-architecture-audit`  
**Audit type:** Repository inventory + source-level review of the core runtime and intelligence paths.

> This is an evidence-based baseline audit, not a claim that every Python module has received a line-by-line review or that the system has been tested on the owner's physical Mac or a live cloud deployment. The entire tracked file inventory and active PR graph were inspected; source-level inspection focused on the core execution, memory, research, policy, persistence, and runtime modules listed below. Remaining module-by-module verification is tracked as follow-up work.

## 1. Executive summary

The repository already contains a meaningful hybrid local/cloud agent foundation. It is not accurate to describe the project as a blank-slate chatbot. The audited branch contains:

- A multi-provider LLM layer and deterministic configuration-based router.
- Role profiles for assistant, planner, executor, researcher, coder, writer, and reviewer.
- A tool-using local agent orchestrator.
- Bounded deep research with source extraction and citation IDs.
- Conservative citation-integrity assessment and a deterministic synthetic benchmark.
- Explicit, scope-isolated memory and a SQLite knowledge graph.
- Workflow metadata ledger and encrypted checkpoints for approval-paused workflows.
- Model execution telemetry.
- Local Mac tools, local policy evaluation, cloud control/client/agent modules, and an isolated browser implementation.
- A Streamlit application and a feature registry for the existing Oracle capabilities.

However, several major goals in the proposed autonomous intelligence roadmap are not yet implemented end-to-end. In particular:

1. Claim-level semantic evidence verification is not implemented by the current answer-quality assessor.
2. Research contradiction and freshness detection are not yet a complete integrated evidence subsystem.
3. Memory is explicit and primarily lexical; episodic/procedural memory and vector retrieval are not evidenced as integrated capabilities.
4. The agent orchestrator is a bounded sequential tool loop, not a durable DAG-based task engine.
5. Encrypted checkpoints exist, but they are primarily associated with paused approval workflows; they do not by themselves establish general crash-resumable task execution.
6. The current router is configuration-driven, not performance-driven.
7. Multi-provider telemetry records operational metadata but does not yet tie measured quality/cost results into adaptive routing.
8. The currently observed local execution policy does not fully match the owner's requested rule that deletion alone requires manual approval.
9. Live physical-Mac, deployed-cloud, wake/sleep, and real provider end-to-end validation have not been established by this repository audit.

The highest-value next step is to complete the evidence-verification foundation while preserving the current PR dependency chain, then evolve memory, durable task execution, multi-agent orchestration, and model intelligence in dependency order.

## 2. GitHub state at audit time

The repository was observed as **Public**, with `main` at `5a99c9d6e6416ed3dfb879ea07cf1adfb04882e5`.

Open draft PRs:

| PR | Head branch | Base branch | Head SHA | Observed purpose |
|---|---|---|---|---|
| #1 | `hardening/auth-webhook-vault-routing` | `main` | `06f7765731f0179b93ac8e70223ef2f892951a60` | Hybrid cloud, local Mac agent, browser, runtime, execution governance |
| #2 | `feature/oracle-answer-quality-foundation` | `hardening/auth-webhook-vault-routing` | `d4468b28de54e88c032d873c66ed08c532378c17` | Conservative citation integrity assessment integrated into deep research |
| #3 | `feature/oracle-answer-quality-benchmark` | `feature/oracle-answer-quality-foundation` | `0763f14e006554cb20af4a22526394a4d4ce0ade` | Deterministic 10-case synthetic citation-classification benchmark |

Dependency chain:

`main → PR #1 → PR #2 → PR #3`

All three were observed open and draft. They must not be merged or retargeted automatically. Any new work based on the full current feature stack should declare its base branch and dependency explicitly.

### CI evidence observed

- PR #3 head SHA `0763f14e006554cb20af4a22526394a4d4ce0ade` had completed successful Oracle CI runs, including run IDs `42373584032` and `42373575270`.
- An earlier intermediate commit on the benchmark branch had a failed run; later commits on the current PR head were followed by successful runs.
- PR #2 also had completed successful CI runs on its observed head.
- The workflow `.github/workflows/ci.yml` runs Python 3.11 on Ubuntu and macOS, installs `requirements.txt` plus pytest, runs `compileall`, and then `pytest -q`.
- A previous user-reported local run showed 179 tests passing with one Starlette/httpx compatibility warning on the PR #2 branch. This is historical user-provided evidence, not a test executed during this audit.

CI success proves the configured test suite passed on GitHub-hosted runners. It does **not** prove production deployment, physical Mac behavior, live third-party API behavior, or full feature completeness.

## 3. Architecture as currently observed

### 3.1 Application and capability layer

- `app.py` is the Streamlit application entry point.
- `features.py` maintains the legacy capability registry, with declared states such as active, beta, integration, and scaffold.
- `feature_hub.py` and feature-specific modules supply existing productivity, content, opportunity, finance, learning, and other capability implementations.
- `agent_orchestrator.py` includes non-scaffold Oracle features, local Mac tools, browser tools, and deep research in its available-tool catalog.

The registry's self-declared status is useful metadata, but it is not independent proof that each capability is fully implemented, integrated, configured, and tested. Each feature needs its own execution-path verification.

### 3.2 AI request and provider pipeline

Observed core modules:

- `ai_request.py`: immutable request/context structures with validation and frozen request data.
- `llm_provider.py`: provider protocol and OpenAI-compatible adapters, including OpenRouter, OpenAI, Gemini, and local Ollama support.
- `agent_profiles.py`: role-specific provider/model/task/temperature configuration.
- `model_router.py`: deterministic routing by explicit provider/model, task category, or configured fast/balanced/deep tier.
- `ai_executor.py`: request-scoped provider/model execution.
- `ai_core.py`: shared entry point; attaches bounded relevant explicit memory and optional graph context before executing a request.

Current routing is configurable and explainable at the route-decision level. It is not yet an adaptive optimizer trained on measured task quality, benchmark outcomes, cost, and latency.

### 3.3 Agent orchestration

`agent_orchestrator.py` implements a model-planned, sequential tool-use loop:

- Builds a catalog from Oracle features, local tools, browser tools, and deep research.
- Requests one next tool step at a time.
- Validates that the selected tool exists in the allowlist.
- Bounds task and tool input/output/history sizes.
- Uses a default step limit of 12 with a hard upper bound of 30.
- Replans after observing each tool result.
- Includes executor-model preflight for selected local mutations.
- Uses deterministic execution policy as the actual approval boundary.

This is a useful bounded tool-using agent. It is not yet a multi-agent DAG scheduler with persistent task plans, dependency-aware parallel execution, generic crash recovery, and specialized agent lifecycle management.

### 3.4 Research and answer quality

`deep_research.py` implements bounded multi-query research, source deduplication, selected page extraction, and cited reporting. The inspected constants bound query count, source count, page fetches, extracted page text, context, and answer length.

`answer_quality.py` deliberately evaluates citation presence and source availability. It classifies claims as uncited, invalid-reference, or citation-present-but-semantically-unverified. It explicitly returns:

- `semantic_entailment_checked = false`
- `truth_verified = false`

The benchmark in `answer_quality_benchmark.py` evaluates citation classification using a small synthetic fixture set. It is a regression baseline, not a representative real-world research-quality benchmark.

Not evidenced as complete in this audit:

- Reliable claim extraction beyond sentence-like segmentation.
- Semantic entailment verification.
- Claim-to-evidence support scoring.
- Source authority ranking.
- Temporal contradiction resolution.
- Domain-specific freshness policies.
- A production-representative human-reviewed evaluation dataset.

### 3.5 Memory and knowledge graph

`memory.py` provides explicit, scope-isolated `fact`, `preference`, and `goal` records. It includes deterministic duplicate handling and token-overlap retrieval with recency as a tie-breaker.

`knowledge_graph.py` provides a scope-isolated SQLite graph with explicitly added entities and directed relationships, evidence fields, bounded traversal, and deterministic lexical entity search. `ai_core.py` retrieves a small amount of memory and graph context when a memory scope is supplied.

This is a foundation, not the complete hybrid memory architecture. The audited implementation does not establish integrated:

- Episodic event memory.
- Procedural workflow memory.
- Vector/embedding retrieval.
- Hybrid lexical + semantic + temporal + graph ranking.
- Automatic, evidence-backed entity/relationship extraction.
- Versioned conflict resolution and memory lifecycle orchestration.

### 3.6 Workflow persistence

- `workflow_ledger.py` stores scope-bound workflow and step metadata, including hashes/digests, statuses, lengths, and durations. It intentionally avoids storing raw task text, tool arguments, file contents, or outputs.
- `workflow_checkpoints.py` stores encrypted, bounded, TTL-limited payload checkpoints and supports scope-bound recovery. Its documented integration is focused on approval-paused workflows.

These components are valuable but are not equivalent to a general persistent job queue. A full task engine still needs durable task plans, step input/output state appropriate to the privacy model, idempotency keys, explicit state transitions, dependency tracking, restart recovery, cancellation, retry scheduling, and resource budgets.

The checkpoint loader currently removes an expired checkpoint while reporting it expired. This automatic cleanup behavior must be reviewed against the owner-defined deletion-approval requirement before it is treated as acceptable retention behavior.

### 3.7 Model observability

`model_observability.py` records bounded metadata including provider, model, route reason, latency, outcome, output character count, and timestamp. It intentionally does not store prompts or completions. It computes request counts, success rate, errors, and p50/p95 latency.

Not evidenced as integrated:

- Token-level usage.
- Actual/estimated cost.
- Quality benchmark outcome per model.
- Task-category quality measurements.
- Routing feedback loops.
- Confidence intervals or minimum-sample guards.
- Adaptive routing based on measured quality/cost/latency.

### 3.8 Local Mac and cloud runtime

The audited branch contains:

- `local_tools.py`: Mac-local file, command, application, and system-inspection tools.
- `mac_intelligence.py`: local policy configuration and trusted-workspace authorization.
- `execution_policy.py`: deterministic owner-scoped approval records and exact-payload one-time approvals.
- `local_runtime.py`, `manage_launch_agent.py`, and `install_local.py`: local runtime and LaunchAgent installation path.
- `cloud_control.py`, `cloud_client.py`, and `cloud_agent.py`: cloud control plane and Mac polling-agent components.
- `web_browser.py`: isolated browser tools.

PR #1 documents that the Mac agent initiates outbound HTTPS communication and that remote move/delete tools are not exposed. It also documents that screen capture and admin/root elevation are not implemented. The code review and CI do not prove that pairing, browser interaction, permissions, LaunchAgent behavior, sleep/wake recovery, or local execution have been tested on the owner's physical Mac.

Do not run the installer or activate a LaunchAgent as part of a source audit.

## 4. User-defined local operating policy — implementation gap

The owner has explicitly specified that ordinary reading, creation, editing, command execution, installation, moving, and renaming should not require redundant manual approval; deletion alone must require explicit owner approval.

The inspected code does not fully implement this requested policy:

- `execution_policy.py` places write, move, delete, run-command, and open-app tools in `APPROVAL_TOOLS`.
- `mac_intelligence.py` can auto-authorize only configured tools and configured command prefixes within configured trusted workspace roots.
- The currently described trusted-workspace policy only auto-allows selected configured operations; move and delete are not part of the remote mutation allowlist.
- `agent_orchestrator.py` performs an Executor preflight on selected local operations.
- Some internal deletion functions, such as graph entity removal and checkpoint expiration cleanup, need to be audited for enforcement through the same deletion-approval contract.

Required future behavior: remove redundant approvals for the owner's specified ordinary operations while enforcing explicit approval for every effective deletion path. The deletion control must be enforced by code, not solely by model instructions or UI behavior. This audit does not change execution policy.

## 5. Database and persistence observations

- The project uses SQLite through `db.py`, with a configurable `ORACLE_DB_PATH`, WAL journal mode, and shared connection helper.
- `database.py` reuses `db.py` and adds a large set of feature and Oracle tables.
- Multiple modules initialize tables through `init_db()` and `init_database()`.
- The inspected tree does not show a dedicated, versioned migration directory or migration framework.

Risks and follow-up work:

- Document table ownership and schema initialization order.
- Introduce a versioned migration strategy without losing existing local/cloud data.
- Test upgrades from representative prior database states.
- Test concurrent app/worker access, backup/restore, and crash recovery.
- Define deletion-aware retention/cleanup behavior.
- Review indexes and query performance as task, memory, and evidence tables grow.

## 6. Test and CI inventory

The current tree includes dedicated test modules for:

- Agent orchestration.
- AI provider/core routing.
- Answer quality and benchmark.
- Deep research.
- Execution policy.
- Hybrid runtime.
- Knowledge graph.
- Local tools and Mac Intelligence.
- Memory and memory retrieval.
- Model observability.
- Multi-provider integration.
- Panic-wipe and vault security.
- WhatsApp idempotency and webhook security.
- Workflow checkpoints and workflow ledger.

The configured CI matrix currently covers Ubuntu and macOS with Python 3.11, compileall, and pytest. It does not currently show dedicated lint/type-check/build/migration/security-analysis jobs in the inspected workflow.

Do not interpret the existence of test files as proof that every integration or operational scenario is covered.

## 7. Capability status summary

| Capability | Status | Evidence-based assessment |
|---|---|---|
| Multi-provider adapters | `IMPLEMENTED_AND_VERIFIED` | Adapters and tests exist; live provider credentials and production health are not verified |
| Deterministic model routing | `IMPLEMENTED_AND_VERIFIED` | Configuration-driven task/tier routing and tests exist |
| Performance-based model routing | `PLANNED` | Telemetry exists but quality/cost benchmark feedback is not integrated |
| Role profiles | `IMPLEMENTED_AND_VERIFIED` | Seven role profiles are defined and consumed by AI Core |
| Sequential tool-using agent | `IMPLEMENTED_AND_VERIFIED` | Bounded planner/replan loop and dedicated tests exist |
| Multi-agent orchestration | `PARTIALLY_IMPLEMENTED` | Role profiles and one orchestrator exist; no full delegated DAG lifecycle is evidenced |
| Deep research | `IMPLEMENTED_BUT_UNVERIFIED` | Bounded source research is implemented; live-source quality and operational runs not verified here |
| Citation integrity assessment | `IMPLEMENTED_AND_VERIFIED` | Conservative citation-presence/source-availability checks and tests |
| Semantic claim verification | `PLANNED` | Explicitly marked not evaluated by current assessment |
| Source contradiction detection | `PLANNED` | Not evidenced as integrated end-to-end |
| Freshness detection | `PLANNED` | Source dates are not used in a complete freshness policy |
| Synthetic citation benchmark | `IMPLEMENTED_AND_VERIFIED` | 10-case deterministic structural benchmark and CI |
| Representative research benchmark | `PLANNED` | Requires broader Arabic/English, reviewed claim/evidence cases |
| Explicit fact/preference/goal memory | `IMPLEMENTED_AND_VERIFIED` | Scope isolation, duplicate handling, lexical retrieval and tests |
| Hybrid semantic/vector memory | `PLANNED` | Not evidenced in the current memory retrieval path |
| SQLite knowledge graph | `IMPLEMENTED_AND_VERIFIED` | Explicit entities/relations, scope isolation, bounded traversal and tests |
| Automatic memory consolidation | `PLANNED` | Not evidenced as integrated |
| Workflow metadata ledger | `IMPLEMENTED_AND_VERIFIED` | Digest-only workflow/step history and tests |
| Encrypted approval checkpoint | `IMPLEMENTED_AND_VERIFIED` | TTL- and scope-bound encrypted checkpoint and tests |
| General persistent task engine | `PLANNED` | No complete durable DAG/job queue/resume lifecycle evidenced |
| Model telemetry | `IMPLEMENTED_AND_VERIFIED` | Provider/model/route/latency/outcome summary |
| Cost + quality telemetry | `PLANNED` | Not evidenced as integrated |
| Mac local tools and policy | `IMPLEMENTED_BUT_UNVERIFIED` | Source and tests exist; physical Mac behavior not verified, and user policy mismatch remains |
| Cloud control + Mac polling agent | `IMPLEMENTED_BUT_UNVERIFIED` | Code and documentation exist; live deployment/pairing not verified |
| Isolated browser | `IMPLEMENTED_BUT_UNVERIFIED` | Browser module exists; real device and browser workflows not verified |
| Streamlit Control Center | `PARTIALLY_IMPLEMENTED` | Existing UI exists; full task/memory/research/model/agent observability coverage needs verification |
| Existing Oracle feature registry | `PARTIALLY_IMPLEMENTED` | Registry and many modules exist; individual capability statuses require execution-path audit |
| Versioned DB migrations | `PLANNED` | No dedicated migration system found in inspected tree |
| Ubuntu/macOS CI | `IMPLEMENTED_AND_VERIFIED` | Workflow and successful latest PR #3 runs observed |

## 8. Architecture risks and technical debt

1. **Flat module layout:** the repository has many top-level modules; ownership boundaries and dependency direction need to be documented before broad refactoring.
2. **Database initialization:** schema creation is spread across `db.py` and `database.py`; a versioned migration lifecycle is needed.
3. **Capability truthfulness:** legacy registry status values should be reconciled with real integration and tests.
4. **Synchronous agent loop:** the current tool-using loop is bounded but not a persistent general task scheduler.
5. **Memory limitations:** lexical retrieval is useful but insufficient for complex semantic/temporal retrieval.
6. **Evidence gap:** citation presence is not semantic support or factual truth.
7. **Model adaptation gap:** telemetry does not yet close the loop with quality benchmarks and cost.
8. **Policy mismatch:** current approvals and trusted-workspace restrictions do not fully reflect the owner's requested normal-operation policy.
9. **Physical integration gap:** cloud deployment, device pairing, browser operation, LaunchAgent lifecycle, permissions, and sleep/wake behavior require explicit operational validation.
10. **Repository hygiene:** the observed `main` tree contained tracked Python bytecode files; the audited PR #3 tree did not. Keep generated bytecode out of future commits and verify ignore rules.

## 9. Recommended dependency-aware roadmap

1. **Evidence foundation:** claim extraction, evidence provenance, semantic verification interface, contradiction and freshness models, broader benchmark.
2. **Memory evolution:** event/procedural records, hybrid retrieval with lexical fallback, provenance-backed graph integration, versioning and consolidation.
3. **Persistent task engine:** durable plans, DAG state, queue, idempotency, checkpoints, recovery, cancellation and budgets.
4. **Agent orchestration:** typed specialist contracts, supervisor, bounded delegation, task integration and reviewer.
5. **Model intelligence:** expanded benchmark, cost/quality/latency telemetry, measured routing policy, privacy-aware fallback.
6. **Bounded self-correction:** issue-specific retry, repeated-action detection, no-progress detection and verifiable stop conditions.
7. **Mac policy alignment and integration:** implement the user's approval contract, deletion gate coverage, local/cloud job lifecycle, and physical-device test plan.
8. **Control Center and capability integration:** expose real task/memory/research/model/agent state; connect existing feature modules through typed capabilities.
9. **Reliability and operations:** migrations, backup/recovery, structured CI, integration/e2e tests, deployment and operational runbooks.

Phases may overlap only when their contracts and dependencies are explicit. Avoid creating a new subsystem if a current module can be safely extended.

## 10. Source-level inspection performed

Primary files inspected on the audited ref:

- `README.md`
- `.github/workflows/ci.yml`
- `ai_request.py`
- `ai_core.py`
- `llm_provider.py`
- `ai_executor.py`
- `model_router.py`
- `agent_profiles.py`
- `agent_orchestrator.py`
- `features.py`
- `deep_research.py`
- `answer_quality.py`
- `answer_quality_benchmark.py`
- `memory.py`
- `knowledge_graph.py`
- `model_observability.py`
- `workflow_ledger.py`
- `workflow_checkpoints.py`
- `db.py`
- `database.py`
- `local_tools.py`
- `mac_intelligence.py`
- `execution_policy.py`
- `worker.py`

The full tracked file inventory and existing test-module inventory were also inspected. Feature-specific modules not listed above remain to be reviewed individually before their statuses can be considered final.

## 11. Audit conclusion

Personal AI Oracle already has valuable building blocks. Its next leap does not require a blind rewrite. It requires converting these building blocks into complete, persistent, measurable workflows with verified integration.

The most important architectural transition is:

**From a bounded tool-using assistant with memory and research utilities → to a persistent, evidence-grounded, task-oriented intelligence system with measured model selection and reliable recovery.**

This document is a baseline audit at the recorded commit. Update it whenever implementation changes materially alter the architecture.
