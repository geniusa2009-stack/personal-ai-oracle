# G1/G2 continuation engineering report — 2026-11-17

## A. Repository state

Branch: `oracle/phase-04-g1-g2-local-ai`; base:
`oracle/phase-04-end-to-end-integration`. PR #23 remains open, draft and unmerged.
Initial local and remote head: `6d98dcd27629581d6055f376edab1c9f1253107c`.
PR #22 is also open/draft, head `31a2ef048a5064046a65f380d26257e742a69bd8`.
No new remote commits or PR comments were present at inspection. The original
workspace is unrelated (`saja`) and was left intact; Oracle was cloned separately.
The fresh Oracle checkout was clean. No repository AGENTS.md was found.
Final delivery SHA is recorded in Git history and the PR description rather than
embedding a self-referential commit hash in this file.

## B. Audit findings

Existing architecture: `features.py` registry → `ai_core.py` / model router and
executor; `hybrid_memory.py` combines lexical/vector/graph context; `deep_research.py`
collects bounded evidence and calls `semantic_verifier.py`; `agent_task_execution.py`
composes evidence, specialist DAG and bounded revisions; `task_control_center.py`
projects scoped metadata into `app.py`. `execution_policy.py` maintains exact-action,
owner-scoped, single-use approval grants and mandatory deletion approval.

G1 already supplied native Ollama, asymmetric prefixes, vector hashes, bounded
scoped indexing and lexical fallback. G2 already supplied lazy offline CPU ONNX,
thresholds, extracted-page-only decisive evidence, a 48-pair limit and no hosted
fallback. Found defects: local requests could follow redirects/use environment
proxies; dimensions could drift across batches/runs; invalid logits/label indices
were incompletely rejected; cached sessions persisted after runs; setup documentation
incorrectly named the embedding transport. These are addressed by this increment.

Initial local baseline command was BLOCKED by missing pytest. Existing remote CI
passed both platforms at the original head. Dependencies were installed only into
`.venv`; optional AI runtime and weights were not installed. No dedicated lint,
type-check or dependency-security workflow was found. This is a focused source review,
not an exhaustive security audit of every legacy module.

## C. Changes implemented

- `memory_embeddings.py`: disable redirects and proxies for native local requests;
  enforce one vector dimension per scope/model across batches and runs.
- `local_nli_verifier.py`: validate three finite logits and exact label positions;
  serialize runs and clear runtime cache on success/failure. Cold reload trades
  latency for less persistent residency; RSS release is allocator-dependent.
- `local_ai_status.py`, `app.py`: read-only configuration/file inventory; explicitly
  distinguish configuration from inference readiness and untracked history.
- `scripts/evaluate_local_nli.py`, `tests/fixtures/local_nli_eval.json`: explicit
  offline evaluation, expected/actual output, latency/CPU/peak process RSS.
- Local AI tests: transport, cache dimensions, malformed output, resource cleanup,
  bilingual missing/snippet evidence and truthful/redacted status projections.
- Architecture profile, capability matrix and delivery log: updated actual scope
  and limitations; historical records retained.

## D. G1 results

IMPLEMENTED: native `/api/embed`, required query/document prefixes, `keep_alive=0`,
explicit owner indexing with CLI defaults 100 records/batch 2, current-record hash
checks, scope isolation and lexical fallback. TESTED_LOCALLY with mocked adapters;
real Ollama inference/retrieval quality remains IMPLEMENTED_BUT_UNVERIFIED.
Service was unreachable at loopback; no private memory was indexed. Model installation
and operational availability detection remain unknown in the inventory.

## E. G2 results

IMPLEMENTED: lazy predownloaded tokenizer/quantized model, CPU sequential inference,
threshold default 0.80, no hosted fallback, all five evidence labels and fail-closed
pair cap. Tests preserve `factual_truth_verified=false` and verification lineage.
TESTED_LOCALLY via mocks; actual tokenizer/ONNX input-output compatibility, runtime
installation and classifier behavior remain IMPLEMENTED_BUT_UNVERIFIED.

## F. Arabic/English evaluation

18 transparent synthetic cases cover English, Arabic and mixed-language inputs.
Missing/snippet cases are TESTED_LOCALLY without a model. Real model evaluation is
BLOCKED by unavailable approved weights/runtime. No accuracy, false-positive,
false-negative or threshold-calibration results are claimed. The runner reports
per-case actual labels/errors and mismatches when explicitly invoked after setup.

## G. Hardware and resource status

Local host reports Darwin arm64 and Python 3.13.5. Automated code tests on this Mac
are TESTED_LOCALLY; they do not establish VERIFIED_ON_TARGET_MAC for inference or
that this host has the requested 8 GB configuration. Ollama binary exists but its
service did not respond. Approximately 7.3 GiB disk was available before dependency
installation. No model weights, daemon or persistent worker were installed.
Resource planning estimates and a reproducible benchmark command are in the local
AI profile. Actual load time, inference latency, memory pressure behavior and
interprocess embedding/NLI coordination remain unverified. Session cleanup does
not provide an OS-level memory guarantee.

## H. CI and validation

Original head run: https://github.com/geniusa2009-stack/personal-ai-oracle/actions/runs/44087449979
Ubuntu and macOS compile/test jobs succeeded (TESTED_IN_CI). This audit confirmed
job status; it did not independently recount the original test logs.
Local targeted suite: 37 passed. Python compilation, `pip check` and `git diff --check`
passed. Final full-suite and new-head CI results are recorded in the PR description
and delivery log. One intermediate full run had a newly added fixture missing its
required source argument (399 passed/1 failed); the fixture was corrected. A prior
full run before that added test passed 399 tests. The existing Starlette/httpx
TestClient deprecation remains; no unrelated dependency migration was made.
No dedicated linter/type checker was configured. Secret-pattern review of changed
files is a limited check, not an exhaustive secret-scanning service.

## I. Security review

Preserved explicit local-mode routing, owner scopes, approval policies, evidence
allowlists and no-auto-download behavior. Regression tests demonstrate redirect
rejection before response-body use; explicit proxy bypass prevents proxy routing of
local memory requests. Retrieved evidence remains classifier input, never execution
instructions. No paid API, personal data ingestion or security-setting change was
performed. Remaining risks include upstream model-main revision mutability, missing
checksum pinning, unknown real-model calibration and broader legacy application
cloud paths. G1/G2 locality does not imply all planning/research uses local models.

## J. GitHub delivery

Authorized existing feature branch and Draft PR #23 are used; main and the PR stack
are preserved. No merge, force push or history rewrite. The PR description carries
confirmed delivery SHA and new-head CI status after push.

## K. Next recommended phase

1. Review model licenses/provenance; pin revisions/checksums before distribution.
2. Explicitly approve model preparation, then run bilingual evaluation on the actual
   8 GB Mac with the Python 3.11 reference environment and measure RSS/latency.
3. Calibrate thresholds from human-reviewed examples; inspect false support and
   missed contradictions before using outputs in autonomous decisions.
4. Add owner-scoped persistent indexing/verification/resource telemetry. This is
   NOT_IMPLEMENTED; current UI honestly labels it untracked.
5. Add interprocess resource coordination if measurements show contention, then
   validate the full live orchestration path with explicitly local planner models.

# Phase 04h continuation — 2026-11-17

Audit reconfirmed clean feature branch at `e05e34c`, open Draft PR #23 with unchanged
base and successful prior CI. Hardware inspection established Darwin arm64/macOS
26.5.1 with exactly 8 GiB RAM, approximately 7.3 GiB disk available and a 25% memory
availability snapshot. The earlier unreachable-Ollama observation was sandbox
network isolation: outside-sandbox `/api/tags` succeeded. The selected embedding
model is absent; no real G1 embeddings, retrieval quality or inference latency/RAM
results exist. Project NLI weights and optional packages are absent; real G2 tensor,
tokenizer and bilingual accuracy results remain BLOCKED. No alternative installed
model was substituted. No private memory was indexed.

Implemented: explicit cold/session evaluation modes, bounded advisory process/thread
coordination, OS pressure admission and post-cleanup snapshots; owner-scoped bounded
persistent metadata through the existing database; Control Center scoped event display;
pinned NLI upstream revision, sizes/hashes and explicit-download verification.
Default NLI disposal remains per assessment. Session reuse is an explicit evaluation
choice, not a new production default. Tests cover lifecycle, scope retention, metadata
redaction, integrity failures and evaluation outputs. An initial targeted run exposed
two legacy mocks receiving an unnecessary `scope=None` keyword; the call now adds
scope only when explicitly supplied, preserving the existing no-scope contract.

User explicitly requested no optional installation and no modification to `.venv`.
Only existing test tools were used. No new environment was created pending separate
approval. Python 3.11 was absent in standard installation locations; existing 3.13.5
is proposed for `.venv-local-ai`. A metadata-only candidate dependency resolution
found compatible arm64 wheels satisfying direct requirements; it is not an installer
or real-import verification. Detailed per-wheel sizes/hashes and exact model payloads
are in `LOCAL_AI_SETUP_PLAN.md` and its JSON manifests. Binary installation footprint
and actual model compatibility are not measured. Model sizes total 663,275,623 bytes;
27 candidate package wheels add 51,387,232 bytes. No weights or wheels downloaded.

TESTED_LOCALLY: full suite **408 passed, 1 existing warning**; compilation, pip
consistency and diff checks pass. TESTED_IN_CI results for this phase are recorded in
PR #23 after push; the report avoids a documentation-only CI loop. Model downloads,
real inference, real cold/warm timings, peak inference RSS, session memory recovery
and threshold calibration remain BLOCKED or IMPLEMENTED_BUT_UNVERIFIED. There is
no VERIFIED_ON_TARGET_MAC inference claim. The isolated setup approval is the next
required user action; system Python, global packages and the original venv stay intact.

# Approved isolated setup and real inference — 2026-11-17

User explicitly approved isolated dependencies, both downloads and sequential
synthetic validation. `.venv-local-ai` was created using existing Python 3.13.5;
27 binary packages installed without source builds, import checks and pip check
passed. Existing `.venv` and global packages were not modified. Actual installed
packages match the candidate version pins; pip selected alternate compatible wheels
for charset-normalizer/protobuf, recorded in the ignored installer report. Isolated
environment disk usage ~289 MiB. Model artifacts/cache/logs remain ignored.

Sources/licenses: official Ollama registry/Google EmbeddingGemma 2 Apache-2.0 card;
pinned MoritzLaurer model card MIT. Ollama chose a 378 MB MLX/nvfp4 variant rather
than the 304 MB GGUF manifest previously measured. All 425 referenced installed
blobs passed size/SHA-256 validation. NLI pinned revision and all seven sizes/three
LFS hashes matched. ONNX SHA-256: 27c39e884c14b03cf46cfc5485971b6db70ff330220d93dfe729c63fde43af0e.

VERIFIED_ON_TARGET_MAC for measured synthetic paths:
- G1: real finite 768d embeddings, correct top ranking 3/3 including Arabic,
  explicit temporary two-owner index isolation, stable dimensions and idempotent
  reindex. 6.432 s total wall; sampled Ollama process RSS peak 569,425,920 bytes;
  Python RSS peak 38,207,488; pressure availability 29%→30%; no model loaded afterward.
- G2: local tokenizer and quantized ONNX CPU inference succeed. Dynamic int64 input_ids
  and attention_mask; [batch,3] float logits; expected labels. Load 1.966 s,
  representative short pairs 11–31 ms. Peak contract-process RSS 1,068,859,392 bytes;
  RSS after disposal 552,927,232. No guarantee of immediate RSS return.
- Cold/session fixture: 18/18 expected results each (six per language group), no
  mismatches/errors. Six per mode are missing/snippet guards; 15 actual NLI pairs
  per mode. Cold: 14.110 s / 12.206 CPU s / peak 1,329,561,600 bytes. Session:
  3.937 s / 2.640 CPU s / peak 676,823,040 bytes. Pressure 29%→30% cold and 42%→36%
  session; different snapshots preclude a controlled memory-efficiency conclusion.

The first NLI contract attempt stopped before model load because sandbox policy
blocked `ps`; authorized outside-sandbox rerun succeeded. This was not a Python,
ONNX or tokenizer compatibility failure. Expected Transformers warning: generative
PyTorch/TensorFlow/Flax backends absent, while tokenizer/ONNX inference succeeded.
ORT import initially warned it could not persist a telemetry ID in sandbox; runtime
telemetry is now explicitly disabled at model initialization. No runtime inference
errors occurred. Baseline suite remains 408 passing with existing deprecation warning.

No private data was indexed. Full results with no private paths/content are in
LOCAL_AI_REAL_VALIDATION.json. Actual model measurements are local, not CI. Peak
RSS is not total hardware footprint and sampled G1 RSS can miss spikes. Models ran
sequentially. Production calibration, long-input/memory-pressure stress tests and
full end-to-end local planning remain IMPLEMENTED_BUT_UNVERIFIED. No new approval
is needed for the already authorized work; no unsafe compatibility workaround was used.
