# GitHub Delivery Log — Personal AI Oracle

This file tracks completed, tested, committed, and published milestones. A milestone is not marked delivered until its branch and Pull Request exist on GitHub.

## Delivery rules

- Never push directly to `main`.
- Do not force-push or rewrite published history.
- Do not merge PRs automatically.
- Use explicit stacked-PR dependencies when the base depends on an unmerged PR.
- Record exact commit SHAs and CI status.
- Keep test results and limitations factual.
- Deletion requires explicit owner approval.

## Existing upstream dependency chain

| PR | Head branch | Base branch | Head SHA | Status at snapshot |
|---|---|---|---|---|
| #1 | `hardening/auth-webhook-vault-routing` | `main` | `06f7765731f0179b93ac8e70223ef2f892951a60` | Open, draft |
| #2 | `feature/oracle-answer-quality-foundation` | `hardening/auth-webhook-vault-routing` | `d4468b28de54e88c032d873c66ed08c532378c17` | Open, draft |
| #3 | `feature/oracle-answer-quality-benchmark` | `feature/oracle-answer-quality-foundation` | `0763f14e006554cb20af4a22526394a4d4ce0ade` | Open, draft |

## Milestones delivered by this branch

### Phase 00 — Architecture audit baseline

- **Branch:** `oracle/phase-00-architecture-audit`
- **Base:** `feature/oracle-answer-quality-benchmark`
- **Dependency:** Stacked on PR #3, which itself depends on PR #2 and PR #1.
- **Files:**
  - `docs/architecture/REPOSITORY_AUDIT.md`
  - `docs/architecture/CAPABILITY_MATRIX.md`
  - `docs/engineering/GITHUB_DELIVERY_LOG.md`
- **Commits:**
  - Repository audit: `3a7452769cda40800e0ed8cc3adf89ff112cf05b`
  - Capability matrix: `d5e4a9a635c861c38cd1dadfc073dd88be1656bf`
  - Delivery log: recorded in the PR head after file creation.
- **Code changes:** None. This milestone is documentation/audit only.
- **Tests:** No code tests were run for the documentation-only files. GitHub Actions should still be observed after the PR is opened; no CI result is claimed in advance.
- **Known limitations:** This is a baseline inventory and source-level audit of core paths, not a line-by-line audit of every feature module or a live physical-Mac/cloud validation.
- **Pull Request:** [PR #4 — Add architecture audit and evidence-based capability matrix](https://github.com/geniusa2009-stack/personal-ai-oracle/pull/4)
- **PR status:** Open, draft; base is `feature/oracle-answer-quality-benchmark` (stacked on PR #3).
- **CI:** Pending at the time of this log update; run `42395904281` was queued and run `42395886119` was in progress.
- **Current branch head before this log update:** `6749d030851576491a0306d0e140f13875b3f472`.

## Next planned milestones (not delivered)

| Milestone | Intended branch family | Current status | Dependency |
|---|---|---|---|
| Claim extraction + evidence verification + contradiction/freshness baseline | `oracle/phase-01-evidence-verification` | Not started | Phase 00 audit and PR #3 stack |
| Hybrid memory evolution | `oracle/phase-02-hybrid-memory` | Not started | Evidence/provenance contracts |
| Persistent task engine | `oracle/phase-03-autonomous-task-engine` | Not started | Database and workflow contracts |
| Multi-agent orchestration | `oracle/phase-04-multi-agent-orchestration` | Not started | Persistent task engine |
| Model intelligence and benchmark-driven routing | `oracle/phase-05-model-intelligence` | Not started | Evaluation datasets and telemetry |
| Bounded self-correction | `oracle/phase-06-self-correction` | Not started | Task state and evaluation contracts |
| Mac policy alignment and integration | `oracle/phase-07-mac-intelligence` | Not started | Owner's deletion-only approval requirement |
| Control Center and observability integration | `oracle/phase-08-observability-and-control-center` | Not started | Task, memory, research, agent and model APIs |

Do not mark a planned milestone complete until its implementation, tests, documentation, commit, push, and PR have all been verified.


### Phase 01 — Evidence foundation (implementation in progress)

- **Branch:** `oracle/phase-01-evidence-foundation`
- **Base:** `oracle/phase-00-architecture-audit`
- **Dependency:** Stacked on PR #4 → PR #3 → PR #2 → PR #1.
- **Files added:**
  - `evidence_verification.py`
  - `test_evidence_verification.py`
  - `docs/architecture/EVIDENCE_VERIFICATION.md`
- **Files integrated/updated:**
  - `deep_research.py`
  - `test_deep_research.py`
  - `docs/architecture/CAPABILITY_MATRIX.md`
- **Implemented scope:** Bounded source-provenance normalization, distinct publication/update/retrieval/extraction timestamps, evidence-level classification, sentence-level claim candidates kept explicitly UNVERIFIED, an explicit-policy freshness assessment primitive, and a structured potential-conflict candidate detector for supplied subject/predicate/object data.
- **Important limitations:** No semantic entailment verifier, no free-text subject/predicate/object extraction, no domain-specific freshness defaults, no persistent evidence database, and no claim of factual truth. Potential conflicts require review.
- **Commits:** Initial feature `d1205839a986f5a30755b643c8f4ad6da0f88679`; follow-up integration/tests and documentation commits are on this branch. Confirm the final branch head before recording final delivery.
- **Tests:** New unit and integration assertions have been added. They have not yet been executed in this environment. Await the branch's GitHub Actions run before claiming a passing result.
- **Pull Request:** [PR #5 — Add structured evidence provenance and claim candidate foundation](https://github.com/geniusa2009-stack/personal-ai-oracle/pull/5)
- **PR status:** Open, draft; base is `oracle/phase-00-architecture-audit` (PR #4).
- **Head before this delivery-log update:** `8f279aa29be2a04dceec7875fbbd603c1f2dbebe`.
- **CI:** Ubuntu test job passed on the current head. macOS job was still running at the time of this update; final PR CI remains pending.


### Phase 01b — Semantic verifier integration (implementation in progress)

- **Branch:** `oracle/phase-01-semantic-verifier`
- **Base:** `oracle/phase-01-evidence-foundation`
- **Dependency:** Stacked on PR #5 → PR #4 → PR #3 → PR #2 → PR #1.
- **Files added:**
  - `semantic_verifier.py`
  - `test_semantic_verifier.py`
  - `docs/architecture/SEMANTIC_VERIFICATION.md`
- **Files integrated/updated:**
  - `deep_research.py`
  - `test_deep_research.py`
  - `docs/architecture/CAPABILITY_MATRIX.md`
- **Implemented scope:** Bounded reviewer-model assessments for sentence-level candidates; strict status/source-ID validation; snippet-only, unavailable and empty-page evidence cannot yield decisive support/contradiction classifications; model errors leave claims unverified; deep-research reports include a separate semantic-verification object.
- **Important limitations:** This remains model-assisted evidence assessment, not proof of factual truth. Sentence-level claims are not guaranteed atomic. No representative human-reviewed production benchmark, automatic temporal conflict resolution, domain freshness registry, or persisted evidence store is included.
- **Tests:** GitHub Actions run `42396961333` completed successfully on commit `2592d1818e4753a350f1d223bfb356b2b2736bb8`: Ubuntu **213 passed, 1 warning**; macOS **213 passed, 1 warning**. The warning is the existing Starlette/httpx TestClient deprecation warning. No local execution is claimed.
- **Pull Request:** [PR #6 — Integrate bounded semantic claim verification into deep research](https://github.com/geniusa2009-stack/personal-ai-oracle/pull/6)
- **PR status:** Open, draft; base is `oracle/phase-01-evidence-foundation` (PR #5).
- **Verified code head:** `2592d1818e4753a350f1d223bfb356b2b2736bb8`.
- **CI:** Successful on Ubuntu and macOS for the verified code head. Subsequent documentation-only commits, if any, require their own CI verification.


### Phase 01c — Domain-aware research freshness

- **Branch:** `oracle/phase-01-temporal-evidence`
- **Base:** `oracle/phase-01-semantic-verifier`
- **Dependency:** Stacked on PR #6 → PR #5 → PR #4 → PR #3 → PR #2 → PR #1.
- **Files added:**
  - `freshness_policy.py`
  - `test_freshness_policy.py`
  - `docs/architecture/FRESHNESS_POLICY.md`
- **Files integrated/updated:**
  - `deep_research.py`
  - `test_deep_research.py`
  - `docs/architecture/CAPABILITY_MATRIX.md`
- **Implemented scope:** Domain-specific starting freshness profiles, conservative bilingual query-hint selection, explicit profile override, no universal general-purpose expiry, per-source/citation freshness fields in Deep Research, compact report support, and stale/unknown/future-date limitations.
- **Important limitations:** Thresholds are starting heuristics requiring calibration. Publication/update date hints are not authoritative proof. This does not detect source supersession or resolve cross-source contradictions.
- **Pull Request:** [PR #7 — Integrate domain-aware source freshness into deep research](https://github.com/geniusa2009-stack/personal-ai-oracle/pull/7)
- **PR status:** Open, draft; base is `oracle/phase-01-semantic-verifier`.
- **Verified code head:** `c9dbdce524a4af4547957144cf41638440343a5c`.
- **CI run:** `42397400916`; Ubuntu **228 passed, 1 warning**; macOS **228 passed, 1 warning**. Both compile and test steps passed. The warning is the existing Starlette/httpx TestClient deprecation warning.
- **Validation scope:** This verifies the configured offline test suite for this commit. It does not validate live search-provider date accuracy, live reviewer-model behavior, physical Mac execution, or production deployment.


### Phase 02a — Episodic and procedural memory (implementation in progress)

- **Branch:** `oracle/phase-02-memory-evolution`
- **Base:** `oracle/phase-01-temporal-evidence`
- **Dependency:** Stacked on PR #7 → PR #6 → PR #5 → PR #4 → PR #3 → PR #2 → PR #1.
- **Files added:**
  - `memory_layers.py`
  - `test_memory_layers.py`
  - `docs/architecture/MEMORY_ARCHITECTURE.md`
- **Files integrated/updated:**
  - `database.py` — additive `memory_events` and `memory_procedures` tables.
  - `ai_core.py` — bounded episodic and validated procedural memory context.
  - `docs/architecture/CAPABILITY_MATRIX.md`
- **Implemented scope:** Explicit scope-bound event storage/retrieval, separate event occurrence and record timestamps, source metadata, candidate/validated/retired procedures, success/failure counters, explicit procedure validation, validated-only procedure retrieval, additive database initialization, and AI Core context integration.
- **Important limitations:** Retrieval is lexical only; no embeddings/vector search, automatic memory extraction, consolidation, revision history, or automatic Knowledge Graph links. The phase does not add any memory deletion API.
- **Tests:** Initial CI reported 237 passed, 1 failed, 1 warning; the single failure was an incorrect test expectation about the deliberately populated second scope. The assertion was corrected to verify per-scope isolation. CI run `42397781790` passed on corrected code head `733ca24e6daf9ef5d1587c9e80cfbd63f30f2886`: Ubuntu **238 passed, 1 warning**; macOS **238 passed, 1 warning**. The warning is the existing Starlette/httpx TestClient deprecation warning. No local test execution is claimed.
- **Pull Request:** [PR #8 — Add episodic and validated procedural memory layers](https://github.com/geniusa2009-stack/personal-ai-oracle/pull/8)
- **PR status:** Open, draft; base is `oracle/phase-01-temporal-evidence` (PR #7).
- **Verified code head:** `733ca24e6daf9ef5d1587c9e80cfbd63f30f2886`.
- **CI after the subsequent delivery-log-only update:** Pending for the new branch head.


### Phase 02b — Hybrid lexical/vector memory retrieval

- **Branch:** `oracle/phase-02-hybrid-retrieval`
- **Base:** `oracle/phase-02-memory-evolution`
- **Dependency:** Stacked on PR #8 → PR #7 → PR #6 → PR #5 → PR #4 → PR #3 → PR #2 → PR #1.
- **Files added:**
  - `memory_embeddings.py` — provider-independent embeddings protocol, OpenAI-compatible client, hash-aware SQLite vector cache, cosine retrieval.
  - `hybrid_memory.py` — lexical/vector Reciprocal Rank Fusion and deterministic fallback.
  - `test_hybrid_memory.py` — deterministic fake embeddings, provider contract, idempotent indexing, stale-vector rejection, scope isolation, hybrid/fallback and AI Core integration tests.
  - `docs/architecture/HYBRID_MEMORY_RETRIEVAL.md`
- **Files integrated/updated:**
  - `database.py` — adds `memory_embeddings` cache table.
  - `ai_core.py` — connects hybrid retrieval while preserving lexical fallback and existing graph/event/procedure context.
  - `docs/architecture/MEMORY_ARCHITECTURE.md`
  - `docs/architecture/CAPABILITY_MATRIX.md`
- **Implemented scope:** Explicit opt-in embeddings, local Ollama default profile, hosted OpenAI-compatible option only when configured, scope/model-specific vector records, SHA-256 content checks, bounded indexing, weak-similarity filtering, RRF, and fail-soft lexical fallback.
- **Safety/privacy constraints:** No hosted provider is selected by default. Embedding calls are disabled unless explicitly enabled with a model. Auto-indexing is off by default. Raw memory text is not duplicated in the vector table.
- **Important limitations:** No real embedding endpoint was exercised by offline CI; tests use deterministic fake vectors. No benchmark-derived similarity threshold. Metadata/temporal/Knowledge Graph fusion and memory consolidation remain unfinished.
- **Validation:** GitHub Actions run `42399859389` passed on code head `24f0717ab6cf4dd7d52a0c0c7c334cc7c570c2e6`. Ubuntu: **251 passed, 1 warning**. macOS: **251 passed, 1 warning**. Both `compileall` and `pytest -q` passed. The warning is the existing Starlette/httpx TestClient deprecation warning. No local test execution is claimed.
- **Pull Request:** Pending creation; this milestone will be published as a draft stacked PR on PR #8.
- **PR status / CI:** CI successful on the verified code head.


### Phase 02c — Memory lifecycle metadata and append-only revisions

- **Branch:** `oracle/phase-02-memory-lifecycle`
- **Base:** `oracle/phase-02-hybrid-retrieval` (PR #9).
- **Dependency:** Stacked on PR #9 → PR #8 → PR #7 → PR #6 → PR #5 → PR #4 → PR #3 → PR #2 → PR #1.
- **Files added:**
  - `memory_lifecycle.py` — scope-bound metadata, validity, confidence/importance, access tracking, append-only revision snapshots, content revision/supersession APIs.
  - `test_memory_lifecycle.py` — default metadata, history, scope isolation, validation, expiry, future-validity filtering, score weighting, non-destructive revision, supersession, and access statistics.
  - `docs/architecture/MEMORY_LIFECYCLE.md`.
- **Files integrated/updated:**
  - `database.py` — additive `memory_metadata` and `memory_revision_history` tables; one-time backfill of legacy rows with neutral defaults and `legacy_baseline` history; panic-wipe allowlist includes all memory lifecycle/vector tables.
  - `memory.py` — registers created memories, excludes superseded records from normal listing/retrieval, applies validity/importance/confidence weights, updates access counters, and cleans linked metadata/history/vector rows on explicit deletion.
  - `memory_lifecycle.py` — creates a new memory record for a content revision; it never overwrites the old memory's content.
  - `test_memory.py` and `test_memory_layers.py` — explicit-delete cleanup and backward-compatible migration coverage.
  - `docs/architecture/MEMORY_ARCHITECTURE.md` and `docs/architecture/CAPABILITY_MATRIX.md`.
- **Implemented scope:** Confidence and importance metadata (0–1, default 0.5); valid-from/valid-until bounds; scope-safe access counts and last-accessed time; active/superseded states; append-only metadata snapshots with hash/reason/actor/timestamp; non-destructive content revision; history retrieval; legacy DB backfill; validity-aware retrieval and metadata-weighted lexical ranking.
- **Compatibility:** The legacy `MemoryRecord` dataclass and its original fields remain unchanged. Existing memory rows and IDs are preserved during additive schema initialization.
- **Deletion/data lifecycle:** Explicit memory deletion removes its associated metadata, revision history and vector-cache rows within one transaction. The database panic-wipe allowlist includes these linked tables. The caller must enforce explicit deletion approval.
- **Limitations:** Metadata is currently manual, not automatically inferred. Confidence/importance are explicit signals, not truth probabilities. Access frequency is recorded but not yet used in ranking. The current score multiplier is a heuristic, not benchmark-calibrated. Existing naive timestamps cannot recover their original timezone with certainty. Episodic/procedural layers do not yet share this metadata schema. UI for memory metadata/history, entity resolution, contradiction review, automatic consolidation, and graph-aware reranking remain unfinished.
- **Validation:** GitHub Actions run `42404347810` passed on code/documentation head `240fe73cd9acaea23610ba163b325efeef256ae9`.
  - Ubuntu: **259 passed, 1 warning**.
  - macOS: **259 passed, 1 warning**.
  - Both `python -m compileall -q .` and `python -m pytest -q` passed.
  - The warning is the existing Starlette/httpx TestClient deprecation warning.
- **Pull Request:** [PR #10 — Add memory lifecycle metadata and non-destructive revision history](https://github.com/geniusa2009-stack/personal-ai-oracle/pull/10)
- **PR status:** Open, draft; base `oracle/phase-02-hybrid-retrieval` (PR #9). Head at initial publication: `240fe73cd9acaea23610ba163b325efeef256ae9`. No PR is merged automatically.


### Phase 02d — Graph-aware hybrid memory retrieval

- **Branch:** `oracle/phase-02-graph-aware-retrieval`
- **Base:** `oracle/phase-02-memory-lifecycle` (PR #10).
- **Dependency:** Stacked on PR #10 → PR #9 → PR #8 → PR #7 → PR #6 → PR #5 → PR #4 → PR #3 → PR #2 → PR #1.
- **Files added:** `docs/architecture/GRAPH_AWARE_MEMORY_RETRIEVAL.md`.
- **Files updated:**
  - `knowledge_graph.py` — typed `GraphRetrieval` contract, bounded seed and neighbor lookup, relation direction/evidence, expansion terms, prompt-boundary escaping.
  - `hybrid_memory.py` — original lexical, optional vector and graph-expanded lexical result lists fused with weighted RRF; graph/vector failures leave remaining channels active.
  - `ai_core.py` — uses the graph context returned by hybrid retrieval, avoiding a second graph query; preserves a fail-soft compatibility fallback.
  - `test_knowledge_graph.py` — graph expansion bounds, scope isolation, stored evidence and markup escaping.
  - `test_hybrid_memory.py` — graph recall for facts, episodic events and validated procedures; graph disable/failure fallback; channel-weight ordering; AI Core integration.
  - `docs/architecture/CAPABILITY_MATRIX.md`, `docs/architecture/MEMORY_ARCHITECTURE.md`.
- **Ranking design:** Weighted RRF; vector 1.00, original lexical 0.70, graph-expanded lexical 0.45. Graph expansion adds only explicitly stored seed/neighbor entity names, not relation evidence. Limits are bounded (default five seed entities, twelve relations, twenty expansion terms).
- **Prompt/data handling:** Relation evidence is shown as stored provenance, not asserted as truth. Graph-owned entity names/evidence have markup delimiters escaped before inclusion in the system context. All graph queries remain exact-scope isolated.
- **Fallback behavior:** Graph failures do not disable lexical/vector retrieval. Embedding provider failures do not disable lexical/graph retrieval. Graph lookup itself makes no external API request.
- **Validation:** GitHub Actions run `42405405994` passed on implementation head `c5b7a7b695c30bf8d4e3ce8aeef58ceece0f0f6b`.
  - Ubuntu: **267 passed, 1 warning**.
  - macOS: **267 passed, 1 warning**.
  - Both compile and full pytest steps passed.
  - The warning remains the existing Starlette/httpx TestClient deprecation warning.
- **Limitations:** Graph extraction/entity resolution is still explicit-only. Query expansion is one-hop and lexical; graph vector embeddings, temporal edge validity, graph contradiction review, automatic consolidation, and benchmark-calibrated RRF weights are not implemented. The weights remain heuristics.
- **Pull Request:** Pending final documentation CI validation; planned as draft PR #11 based on PR #10.
- **PR status:** Not yet created. No prior PR was merged or retargeted.


### Phase 02d — Graph-aware hybrid memory retrieval

- **Branch:** `oracle/phase-02-graph-aware-retrieval`
- **Base:** `oracle/phase-02-memory-lifecycle` (PR #10).
- **Dependency:** Stacked on PR #10 → PR #9 → PR #8 → PR #7 → PR #6 → PR #5 → PR #4 → PR #3 → PR #2 → PR #1.
- **Files updated:**
  - `knowledge_graph.py` — typed `GraphRetrieval`, bounded seeds/neighbors, relation direction/evidence, name expansion terms, and prompt-boundary escaping for graph-owned names/evidence.
  - `hybrid_memory.py` — original lexical, optional vector and graph-expanded lexical channels fused through weighted RRF; graph and provider failures are independent fail-soft paths.
  - `ai_core.py` — consumes the graph context from hybrid retrieval rather than issuing a duplicate graph query; retains a compatibility fallback.
  - `test_knowledge_graph.py` — graph bounds, scope isolation, provenance and markup-escaping coverage.
  - `test_hybrid_memory.py` — graph recall for facts, episodic events and validated procedures; scope isolation, opt-out, failure fallback, channel-weight ordering and AI Core integration.
  - `docs/architecture/GRAPH_AWARE_MEMORY_RETRIEVAL.md`, `docs/architecture/MEMORY_ARCHITECTURE.md`, `docs/architecture/CAPABILITY_MATRIX.md`.
- **Ranking design:** Weighted RRF: vector 1.00, original lexical 0.70, graph-expanded lexical 0.45. Graph expansions contain explicit seed/neighbor entity names only; relation evidence remains provenance and is not used as query expansion.
- **Scope/privacy:** All graph queries stay within the provided scope. Graph text is escaped before being placed inside the system-context boundary. No external graph provider call is made.
- **Fallback behavior:** Graph errors preserve lexical/vector retrieval. Embedding errors preserve lexical/graph retrieval. Graph can be disabled explicitly for baseline evaluation.
- **Validation:** GitHub Actions run `42405656759` passed on implementation/documentation head `3dd48c579cae5e7f2153c7e136e57c996576b5bf`.
  - Ubuntu: **267 passed, 1 warning**.
  - macOS: **267 passed, 1 warning**.
  - Compile and full pytest steps both passed.
  - Warning: existing Starlette/httpx TestClient deprecation.
- **Limitations:** Graph edge extraction/entity resolution remains explicit-only; expansion is one-hop lexical; no temporal edge validity, graph contradiction handling, automatic memory consolidation, graph embeddings or benchmark-calibrated RRF weights.
- **Pull Request:** [PR #11 — Integrate Knowledge Graph into hybrid memory retrieval](https://github.com/geniusa2009-stack/personal-ai-oracle/pull/11)
- **PR status:** Open, draft; base `oracle/phase-02-memory-lifecycle` (PR #10). Initial published head: `ee03ba9292f19f9b2327ff9a862d0c33f8f3dd2f`. No earlier PR was merged or retargeted.


### Phase 02e — Review-only memory consolidation discovery

- **Branch:** `oracle/phase-02-memory-consolidation`
- **Base:** `oracle/phase-02-graph-aware-retrieval` (PR #11).
- **Dependency:** PR #12 → PR #11 → PR #10 → PR #9 → PR #8 → PR #7 → PR #6 → PR #5 → PR #4 → PR #3 → PR #2 → PR #1.
- **Files added:**
  - `memory_consolidation.py` — deterministic scope-local duplicate/related/possible-contradiction candidate discovery, proposal review and run-history APIs.
  - `test_memory_consolidation.py` — scan classification, source immutability, scope isolation, repeat observations, accept/dismiss, stale-source checks, validity expiry, bounded scans and explicit deletion cleanup.
  - `docs/architecture/MEMORY_CONSOLIDATION.md`.
- **Files updated:**
  - `database.py` — run/proposal/member/observation tables and sensitive-table wipe allowlist.
  - `memory.py` — explicit memory deletion clears proposals and observations that depend on the deleted source.
  - `docs/architecture/MEMORY_ARCHITECTURE.md`, `docs/architecture/CAPABILITY_MATRIX.md`.
- **Implemented scope:** bounded comparisons within one memory type and one exact scope; lexical duplicate/related classification; possible contradiction signals from negation-presence and numeric-value differences; source IDs and SHA-256 hashes; proposal observations; run counters and partial status; human accept/dismiss reviews; stale detection before review.
- **Safety contract:** scanning and reviewing do not edit source memories. No automatic merge, overwrite, supersession or deletion exists. Expired, revised, deleted or superseded sources prevent a proposal from being accepted/dismissed as if it were current.
- **Limitations:** deterministic token heuristics are not semantic contradiction verification. Units, date semantics, Arabic morphology, conditional claims and paraphrase reasoning are not fully handled. UI, automatic scheduling, duplicate clusters, entity resolution, retention and conflict resolution remain unfinished.
- **Validation:** GitHub Actions run `42412196590` passed on code/documentation head `d007ca12166bf62da423203faaff31b950fee607`.
  - Ubuntu: **276 passed, 1 warning**.
  - macOS: **276 passed, 1 warning**.
  - Python compile and full pytest steps passed on both platforms.
  - Warning: existing Starlette/httpx TestClient deprecation warning.
- **Pull Request:** [PR #12 — Add review-only memory consolidation and conflict candidate discovery](https://github.com/geniusa2009-stack/personal-ai-oracle/pull/12)
- **PR status:** Open, draft; base `oracle/phase-02-graph-aware-retrieval` (PR #11). Published head: `9833720dccd553ceca25c8d232f2e7d8c3ab7fee`. No earlier PR was merged or retargeted.


### Phase 03a — Measured model benchmarking

- **Branch:** `oracle/phase-03-model-benchmarking`
- **Base:** `oracle/phase-02-memory-consolidation` (PR #12).
- **Dependency:** PR #13 → PR #12 → PR #11 → PR #10 → PR #9 → PR #8 → PR #7 → PR #6 → PR #5 → PR #4 → PR #3 → PR #2 → PR #1.
- **Files added:**
  - `model_benchmark.py` — explicit candidate/case benchmark API, provider-call gate, privacy-safe result persistence, optional evaluator, scorecards and measured ranking.
  - `benchmarks/model_benchmark_cases.json` — six synthetic objective smoke checks.
  - `test_model_benchmark.py` — runner, remote gate, error handling, privacy, scorecard thresholds, evaluator/suite separation, runtime-health floor, bounded matrix and panic-wipe tests.
  - `docs/architecture/MODEL_BENCHMARKING.md`.
- **Files updated:**
  - `database.py` — benchmark run/result tables and sensitive-table wipe allowlist.
  - `ai_executor.py` — request context owner scope overrides environment fallback for model telemetry.
  - `test_multi_provider.py` — request-scoped telemetry regression test.
  - `docs/architecture/CAPABILITY_MATRIX.md`.
- **Measurements recorded:** End-to-end latency, success/error outcome, output character count, optional rubric score and evaluator ID. Prompt and completion content are never stored.
- **Quality policy:** Built-in `phrase_rubric_v1` is a deterministic phrase smoke-check, not semantic correctness or factual verification. Custom evaluators must provide a stable ID and return a finite score from 0 to 1. Scorecards are separated by suite version and evaluator ID.
- **Scorecard policy:** Default ranking weights are quality 0.65, success 0.20 and latency 0.15. Minimum evidence defaults to three benchmark requests and three quality-scored cases. Runtime telemetry contributes a conservative floor using the lower success rate and higher p95 latency when sufficient runtime observations exist.
- **Provider/cost safety:** No benchmark runs on startup or import. The default only permits a loopback Ollama endpoint. Hosted/non-loopback candidates require explicit `allow_remote=True`. No provider cost or token usage is guessed; existing provider adapters do not yet expose verified usage metadata.
- **Routing boundary:** Scorecards are advisory only. `ModelRouter` continues using explicit/category/tier configuration; no automatic model switching is introduced by this phase.
- **Validation:** GitHub Actions run `42418984170` passed on implementation head `245cf74f4327b51bcf930d67fc746d7e50f4a76c`.
  - Ubuntu: **290 passed, 1 warning**.
  - macOS: **290 passed, 1 warning**.
  - Compile and full pytest passed on both platforms.
  - Warning: existing Starlette/httpx TestClient deprecation warning.
- **Limitations:** The bundled suite is a small synthetic smoke set. No live provider benchmark was executed in CI. Cost, token throughput, energy and hardware-normalized performance remain unmeasured. The RRF/benchmark ranking weights are policy defaults, not statistically calibrated.
- **Pull Request:** [PR #13 — Add explicit measured model benchmarking and evidence-gated scorecards](https://github.com/geniusa2009-stack/personal-ai-oracle/pull/13)
- **PR status:** Open, draft; base `oracle/phase-02-memory-consolidation` (PR #12). Initial published head: `3b396abecc0b07261414e0b5f36afb45fe5f9446`. No earlier PR was merged or retargeted.


### Phase 03b — Bounded self-correction and loop prevention

- **Branch:** `oracle/phase-03-bounded-self-correction`
- **Base:** `oracle/phase-03-model-benchmarking` (planned PR #14 stacked on PR #13).
- **Dependency:** PR #14 → PR #13 → PR #12 → PR #11 → PR #10 → PR #9 → preceding stack.
- **Files added:**
  - `bounded_correction.py` — shared text-only correction runner, output fingerprints, repeated-issue detection, non-retryable issue policy and hard retry cap.
  - `test_bounded_correction.py` — first-pass success, correction success, repeated output, repeated validation signature, provider-error stop, policy caps and metadata-only reports.
  - `docs/architecture/BOUNDED_SELF_CORRECTION.md`.
- **Files updated:**
  - `agent_orchestrator.py` — validates planner JSON/tool IDs/input before returning a step; one bounded repair is permitted before tool execution.
  - `deep_research.py` — validates synthesis JSON/answer/inline citation IDs; one bounded repair is permitted by default, configurable from zero to the hard cap of two; exposes correction summary in full and compact reports.
  - `test_agent_orchestrator.py` — malformed JSON/unknown tool repair, repeated planner output, provider-error non-retry, duplicate-step prevention and no executor call during repair.
  - `test_deep_research.py` — repair of invalid citation IDs without repeating search, repeated invalid output stop, provider-error stop and zero-retry setting.
  - `docs/architecture/CAPABILITY_MATRIX.md`.
- **Retry policy:** One retry by default; absolute limit two. Identical output fingerprint, repeated issue signature, provider errors or exhausted budget stop further attempts.
- **Side-effect boundary:** All correction callbacks invoke text generation only. Local commands, file writes/moves/deletes, application launches, browser navigation, web search, page extraction, approval checks and other tool execution are not automatically retried.
- **Research semantics:** Correction validates response JSON, a non-empty answer and inline citations restricted to the sources collected in the current run. It does not prove semantic entailment or factual truth; semantic verification remains a separate evidence-assessment step.
- **Privacy:** Correction metadata contains attempt numbers, hashes and deterministic issue codes; raw previous answer text is not copied into the metadata report.
- **Validation:** GitHub Actions run `42420552279` passed on implementation/test head `66879d5b4e384bd1c5cbdecfc252e7fdb0e6a56f`.
  - Ubuntu: **313 passed, 1 warning**.
  - macOS: **313 passed, 1 warning**.
  - Compile and full pytest passed on both platforms.
  - Warning: existing Starlette/httpx TestClient deprecation warning.
- **Limitations:** This corrects structure/citation integrity and planner catalogue compliance, not general reasoning quality. No model is allowed to retry a tool call through this correction loop. A repaired answer may still be factually wrong and is subject to existing verification limitations.
- **Pull Request:** [PR #14 — Add bounded self-correction and loop prevention](https://github.com/geniusa2009-stack/personal-ai-oracle/pull/14)
- **PR status:** Open, draft; base `oracle/phase-03-model-benchmarking` (PR #13). Published head: `7ada00ce00f94900ec2a2fbb9c44e11b798fad97`. No earlier PR was merged or retargeted.


### Phase 04 — Durable DAG task engine

- **Branch:** `oracle/phase-04-durable-task-engine`
- **Base:** `oracle/phase-03-bounded-self-correction` (PR #14).
- **Dependency:** Planned PR #15 → PR #14 → PR #13 → PR #12 → PR #11 → PR #10 → PR #9 → PR #8 → PR #7 → PR #6 → PR #5 → PR #4 → PR #3 → PR #2 → PR #1.
- **Files added:**
  - `durable_task_engine.py` — scope-bound DAG creation, dependency validation, idempotency, encrypted task/result storage, atomic worker leases, heartbeats, completion/failure, bounded retry, lease reaping, pause/resume/cancel and attempt history.
  - `test_durable_task_engine.py` — DAG and cycle validation, duplicate graph idempotency, dependency ordering, atomic claims, scope/token validation, encryption, retry safety, lease expiry, failed-dependency propagation, pause/resume/cancel, panic wipe and log redaction.
  - `docs/architecture/DURABLE_TASK_ENGINE.md`.
- **Files updated:**
  - `database.py` — graph/task/dependency/attempt tables and sensitive-table wipe allowlist.
  - `workflow_checkpoints.py` — owner-scope-bound Fernet encrypt/decrypt helpers reused for task payloads and results.
  - `test_workflow_checkpoints.py` — wrong-scope, tamper and size-limit tests for encrypted payload helpers.
  - `docs/architecture/CAPABILITY_MATRIX.md`.
- **State and scheduling:** Graphs are DAG-validated and scope-local. A task becomes claimable only when all dependencies succeeded. Failed/blocked/cancelled prerequisites propagate a blocked state to descendants.
- **Lease protocol:** Workers explicitly claim, start, heartbeat and complete/fail tasks. Lease tokens are random, hashed at rest and bound to the worker ID and owner scope. Claims use a transactional conditional update.
- **Retry policy:** No retries by default. A task must explicitly declare `retry_safe=True` before it can have multiple attempts or be requeued after retryable failure/lease expiry. Attempts are capped at five and exponential backoff at 300 seconds. A task paused before entering `running` releases its unstarted lease without consuming an execution attempt.
- **Cancellation boundary:** Queue cancellation stops further scheduling and invalidates leases; it does not forcibly terminate or undo a side effect already running outside the engine. Worker/executor integration must poll and cooperate with cancellation.
- **Privacy:** Task payload and result values are encrypted at rest with owner-scope binding. Lease tokens are hashed at rest and redacted from object representations. Free-form error messages are rejected; only compact error codes are accepted. New tables are included in the panic-wipe allowlist.
- **Validation:** GitHub Actions run `42430710654` passed on code/test head `cd001f0a9f168c251b40de9b7f69d3b43fb85303`.
  - Ubuntu: **328 passed, 1 warning**.
  - macOS: **328 passed, 1 warning**.
  - Compile and full pytest passed on both platforms.
  - Warning: existing Starlette/httpx TestClient deprecation warning.
- **Limitations:** This is a queue/state engine, not a production worker. No task handlers, Control Center UI, recurring scheduler, distributed multi-host queue, key rotation, or general versioned migration framework is included. Retry safety remains an explicit caller assertion.
- **Pull Request:** Pending final documentation CI; planned as draft PR #15 stacked on PR #14.
- **PR status:** Not yet created; no earlier PR was merged, closed or retargeted.
