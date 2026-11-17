# Personal AI Oracle — Zero-Cost Local G1/G2 Profile

**Target hardware:** Apple Silicon Mac with 8 GB unified memory.  
**Scope:** G1 hybrid memory embeddings and G2 semantic claim/evidence assessment.  
**Cloud/API requirement:** None for these two local inference paths. Model downloads require an internet connection once. The normal application dependencies and CI do not install or download model weights.

## Selected models

| Capability | Selected model | Footprint / reason |
|---|---|---|
| G1 multilingual embeddings | `embeddinggemma-2:270m` through Ollama | Text-only 270M parameter variant; Ollama registry lists approximately 304–378 MB. Supports multilingual retrieval and is the smallest text-only variant in this model family. |
| G2 multilingual NLI | `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli`, quantized ONNX | Use only `onnx/model_quantized.onnx` (listed at about 339 MB), plus tokenizer/config files. MIT-licensed model card; XNLI evaluation includes Arabic. |

The NLI model is a classifier, not a generative LLM. It scores premise/evidence versus hypothesis/claim pairs. The default threshold is deliberately conservative (0.80) and must be calibrated against Oracle's own reviewed Arabic/English benchmark before any automatic downstream action.

## Why this profile fits an 8 GB Mac

- Do not load a 7B/8B generative model as part of G1/G2.
- Embedding inference is delegated to the local Ollama service.
- NLI inference is CPU-only, sequential, and capped at 48 evidence/claim pairs per run.
- The NLI runtime loads lazily and requires a local model directory; it never downloads weights automatically.
- Keep vector indexing explicit and bounded. The index command defaults to 100 records and batches of two.
- Close memory-heavy applications before first-time NLI use. Model file size is not the same as peak runtime RAM; actual use must be measured on the target Mac.
- Do not run embedding indexing and a large generative model concurrently.

## Install and prepare

### 1. Install Ollama and fetch the small embedding model

Install Ollama for macOS from its official download page, open the app when you want to use local embeddings, then run:

```bash
ollama pull embeddinggemma-2:270m
```

The native `OllamaEmbeddingClient` uses `/api/embed`; no API key is required. Redirects and environment HTTP proxies are disabled for this local transport.

### 2. Configure G1

Set these values in your local, untracked environment file (never commit secrets or machine-specific paths):

```dotenv
ORACLE_MEMORY_EMBEDDINGS_ENABLED=1
ORACLE_EMBEDDING_PROVIDER=ollama
ORACLE_EMBEDDING_MODEL=embeddinggemma-2:270m
ORACLE_EMBEDDING_BASE_URL=http://127.0.0.1:11434
ORACLE_MEMORY_EMBEDDINGS_AUTOINDEX=0
ORACLE_OLLAMA_EMBED_KEEP_ALIVE=0
```

The existing SQLite vector cache and scope-aware retrieval remain in place. Auto-indexing stays off: the owner explicitly chooses which scope to index.

Build/update an index for one exact scope:

```bash
python -m scripts.index_memory_scope --scope "YOUR_EXACT_OWNER_SCOPE" --max-records 100 --batch-size 2
```

Run this separately for each authorized scope. Never substitute a different user's scope. Re-running the command is content-hash aware and skips unchanged records.

### 3. Install the optional local NLI runtime

The normal `requirements.txt` is unchanged. Install the extra dependencies only when enabling G2:

```bash
python -m pip install -r requirements-local-ai.txt
```

Download the quantized model explicitly (about 339 MB for the ONNX weights; tokenizer/config files are additional):

```bash
python -m scripts.download_local_nli_model --destination models/mdeberta-v3-base-mnli-xnli
```

Set:

```dotenv
ORACLE_SEMANTIC_VERIFIER=local_nli
ORACLE_NLI_MODEL_DIR=models/mdeberta-v3-base-mnli-xnli
ORACLE_NLI_THRESHOLD=0.80
```

With `ORACLE_SEMANTIC_VERIFIER=local_nli`, a missing model or runtime error leaves affected claims `UNVERIFIED`. There is intentionally no automatic fallback to a hosted reviewer/API. The previous hosted reviewer path remains available only when explicitly configured as `model` or `hosted`.

## G1/G2 contracts

### G1

- Embeddings are enabled only by explicit environment configuration.
- The selected model ID is part of the SQLite vector-cache key, so changing models does not silently reinterpret old vectors.
- Document indexing uses EmbeddingGemma 2's `title: none | text: ...` instruction; query retrieval uses `task: search result | query: ...`. This asymmetric prefix pair is required for the model's intended retrieval quality.
- Existing content hashes, stale-record rejection, scope filters, and lexical/graph fallback remain authoritative.
- The indexing script requires an explicit scope and has conservative record/batch defaults.
- The local endpoint is loopback-only by default; do not expose Ollama to a public network.

### G2

- Only cited source excerpts prepared by `semantic_verifier.py` are passed to NLI.
- Local NLI ignores snippet-only evidence for decisive labels.
- Only extracted-page evidence can be accepted by the existing verifier's decisive-evidence gate.
- `SUPPORTED`, `CONTRADICTED`, and `CONFLICTING_EVIDENCE` mean textual evidence assessment, not proof of factual truth.
- `factual_truth_verified` remains `false`.
- Pair count, claim count, source count, excerpt size, and sequence length are bounded.
- The NLI model does not follow or execute instructions in evidence text.

## Validation plan

CI must remain fully offline and deterministic:

1. Mock the Ollama embeddings response and validate URL, model, vector ordering, and vector shape.
2. Keep existing tests for scope isolation, stale-vector rejection, RRF fusion, and lexical fallback.
3. Mock local NLI scores to test support, contradiction, conflicting evidence, snippet rejection, and threshold behavior.
4. Verify that selecting local NLI never silently calls `ai_core.chat`.
5. Run the full repository test suite on Ubuntu and macOS.
6. On the owner's Mac, separately measure peak memory, latency, and retrieval quality using a small manually reviewed Arabic/English set before enabling it in routine use.

No live model download, real Ollama request, production data reindex, hosted API request, background worker, or automatic execution is part of CI.

## Model references

- Ollama model registry: https://ollama.com/library/embeddinggemma-2
- Google EmbeddingGemma 2 documentation and license: https://ai.google.dev/gemma/docs/embeddinggemma
- NLI model card, labels, languages, and license: https://huggingface.co/MoritzLaurer/mDeBERTa-v3-base-mnli-xnli
- Quantized ONNX file: https://huggingface.co/MoritzLaurer/mDeBERTa-v3-base-mnli-xnli/tree/main/onnx

## Continuation audit — 2026-11-17

The native Ollama transport rejects redirects and bypasses environment HTTP proxies.
This prevents a local endpoint response from redirecting private embedding inputs to
another host. The explicit hosted embedding adapter remains a separate opt-in path.
NLI runs are serialized within the process and release cached session/tokenizer
references in a `finally` block. This permits memory reclamation but does not prove
that an allocator immediately returns RSS to macOS. Separate processes can still
compete for memory; avoid concurrent indexing and verification.

NLI rejects non-finite logits, output lengths other than three, and invalid label
indices. Missing runtime or model files continue to fail closed through the existing
semantic-verifier contract. No approval, scope, or deletion policy was changed.

The Control Center now displays a read-only configuration/file inventory. It does
not probe a service, load weights, inspect private memories, or claim readiness.
Installed tokenizer/runtime, operational inference, index history, last verification,
and resource-failure history remain unverified or untracked. Persistent telemetry
for those fields is NOT_IMPLEMENTED.

### Reproducible bilingual evaluation

`tests/fixtures/local_nli_eval.json` contains 18 synthetic cases split equally among
English, Arabic, and cross-language evidence. Each group includes support,
contradiction, conflict, unrelated evidence, missing evidence, and snippet-only
input. Expected labels are author-specified and need human review before calibration.
After explicitly preparing model files and the optional runtime, run:

```bash
python -m scripts.evaluate_local_nli
```

The command never downloads weights. It prints actual/expected labels, errors,
per-case cold-load-plus-inference latency, CPU time, platform and process peak RSS.
A nonzero exit indicates errors or mismatches. Inspect per-case false support,
missed support, and UNVERIFIED cases; do not treat a small synthetic set as a
production benchmark. Actual accuracy, threshold calibration, warm inference,
memory-pressure recovery and browser interaction remain IMPLEMENTED_BUT_UNVERIFIED.

### 8 GB planning envelope (estimates, not measurements)

Reserve roughly 3–4 GB for macOS, 0.5–1 GB for Python/Streamlit, 0.1–0.3 GB for
SQLite/cache, 0.5–1 GB for Ollama embedding inference, and 1–2 GB for quantized NLI
including tokenizer and temporary tensors. A browser can consume another 0.5–1.5 GB.
These uncertain ranges can exceed 8 GB; execute embedding and NLI work sequentially,
keep `keep_alive=0`, and close unrelated browser tabs. Session release is process-local;
it is not an interprocess memory scheduler. Stop on memory pressure rather than
increasing pair/batch limits. Only about 7.3 GiB disk was available during this audit;
no model weights were downloaded. The Ollama loopback service was unreachable.

The existing optional dependency ranges were not changed. Python 3.11 remains the
CI reference. Optional ONNX/Transformers compatibility on this Python 3.13 Mac,
actual ONNX tensor metadata, tokenizer loading, and peak model RAM still require
installation and live inference. Model provenance currently follows upstream main;
a pinned revision/checksum policy remains a follow-up, not an implemented guarantee.

The upstream NLI card declares MIT; EmbeddingGemma has Google model-specific terms,
which should be reviewed before distribution. Model selection is unchanged. Upstream
metadata and model cards are evidence of availability, not proof of local usability.

## Phase 04h — explicit evaluation sessions and scoped telemetry

`python -m scripts.evaluate_local_nli --mode cold` retains the per-case disposal
behavior. `--mode session` reuses one lazily loaded model for a bounded evaluation
batch (at most 48 cases and 48 supplied evidence pairs), then clears references.
Both modes report predictions/mismatches, per-case latency/CPU time, process peak
RSS, pressure snapshots, file hashes and upstream revision where provenance exists.
No mode downloads weights or invokes hosted fallback. Missing provenance is unknown,
not evidence of a revision. Resource pressure can block the whole batch.

`local_model_lifecycle.py` provides a cooperating-process advisory `flock`, a bounded
10-second lock wait, and before/after pressure snapshots. Kernel locks release on
process exit/crash; stale PID-file deletion is unnecessary and could split lock
ownership. A thread lock also bounds same-process waiting. Unknown pressure or less
than 15% available according to the OS query refuses work. This conservative threshold
is a policy starting point, not empirically calibrated model headroom. NLI session
references clear before cleanup/pressure resampling. Native Ollama calls use the same
coordination path; its default `keep_alive=0` requests unloading. Neither Python GC
nor an Ollama response guarantees immediate OS memory recovery. Noncooperating
applications and separately configured persistent Ollama residency remain outside
this advisory lock. No daemon is created.

`local_ai_telemetry.py` uses the existing Oracle SQLite connection and one metadata
table, `oracle_local_ai_events`. Indexing records explicit-scope start/end and aggregate
indexed/skipped/failed counts; semantic verification accepts optional explicit scope
and research passes its owner scope when available. Stored metadata includes bounded
model ID, timestamp, duration and allowlisted error category/result counts, never
raw claims, excerpts, embeddings, exception strings or memory content. Retention is
200 events per owner scope. Telemetry is best effort and cannot change task results;
storage failures may leave gaps. The table is included in existing panic-wipe coverage.
The Control Center queries only its current owner's events and makes no readiness
claim from configuration, file presence or event existence. Installed, loaded,
operational and real-model-tested state remain unverified when not observed.

The explicit NLI downloader pins revision
`8adb042d524ecd5c26d3e3ba0e3fbcf7e2d0864c`, verifies expected file sizes and known
upstream LFS SHA-256 values, and writes actual file hashes plus provenance only on
success. This mechanism is TESTED_LOCALLY using synthetic files; downloaded real
artifact integrity remains BLOCKED pending approval.

The actual Mac has 8 GiB physical RAM. Ollama responds outside the sandbox, but the
selected embedding model is absent. No project NLI model or optional packages exist.
No real inference was run. See `docs/engineering/LOCAL_AI_SETUP_PLAN.md` for Python
inventory, metadata-only dependency compatibility, exact payload sizes and the
separate approval-gated isolated setup. Existing `.venv` and system packages are
unchanged. `.venv-local-ai/` and `models/` are gitignored; neither was populated.

## Approved real inference validation — 2026-11-17

VERIFIED_ON_TARGET_MAC, limited to the synthetic tests below: both selected models
completed inference on Darwin arm64/macOS 26.5.1, 8 GiB RAM, Python 3.13.5. Approved
binary packages were installed only in `.venv-local-ai`; the existing `.venv` and
global Python packages were not changed. Optional import checks and `pip check`
passed before inference. No PyTorch or TensorFlow is required for the tested path.
ORT telemetry is explicitly disabled when initializing the offline NLI model.

Licenses verified from upstream: EmbeddingGemma 2 is **Apache-2.0** (Google model
card: https://ai.google.dev/gemma/docs/embeddinggemma/model_card_2), and the pinned
mDeBERTa card declares **MIT**. This supersedes the earlier generic Gemma-terms
caution for this specific EmbeddingGemma 2 release.

Ollama selected the MLX/nvfp4 artifact, not the previously measured GGUF registry
variant. Reported model size: 378,346,995 bytes. All 425 installed manifest-referenced
blobs matched their SHA-256 and size; total referenced bytes 378,453,128. Upstream
artifact digest: `3963be2b16735897054a438b91f1bc64bf454df624967280be2a2d41874131aa`.
NLI downloaded at the pinned revision; all seven sizes and three upstream LFS
SHA-256 values matched, including the ONNX checksum recorded in the setup manifest.
Small non-LFS file hashes were recorded locally; they were not independently
compared with upstream SHA-256 values.

G1 real results: finite 768-dimensional vectors; three out of three English/Arabic
queries ranked the intended synthetic document first. Temporary SQLite indexed
three records in synthetic:one and one in synthetic:two; reindex skipped all three
unchanged records and retrieval excluded the other scope. Latest run: 6.432 s wall,
0.209 s Python CPU; sampled aggregate Ollama-related RSS peak 569,425,920 bytes,
Python peak RSS 38,207,488 bytes. Pressure availability 29% before / 30% after.
`/api/ps` returned no loaded models after keep_alive=0. Sampling is not a bound on
Metal allocations or instantaneous peak physical memory. Reproduce with the
explicit synthetic-only command `python -m scripts.validate_local_g1`.

G2 real contract: CPUExecutionProvider, int64 input_ids and attention_mask shaped
[batch_size, sequence_length], float logits shaped [batch_size, 3]; labels
entailment=0, neutral=1, contradiction=2. Load 1.966 s; representative short pair
latencies 11–31 ms. Contract-probe RSS: loaded 1,012,170,752 bytes, peak
1,068,859,392 bytes, after reference disposal 552,927,232 bytes. Reference cleanup
therefore did not immediately return all resident memory.

At threshold 0.80, cold and session modes each matched all 18 author-specified
fixture labels: six English, six Arabic, six mixed. Each mode executes 15 real
NLI pairs; six missing/snippet cases are evidence guards, not model predictions.
No mismatches, false decisive positives or runtime errors appeared in this tiny
fixture. This is not population accuracy or threshold calibration.

Cold evaluation: 14.110 s wall, 12.206 s CPU, peak process RSS 1,329,561,600 bytes;
pressure 29%→30%. Session: 3.937 s wall, 2.640 s CPU, peak RSS 676,823,040 bytes;
pressure 42%→36%. These are single runs in distinct processes with different OS
conditions, not controlled evidence that session mode always uses less memory.
G1 completed/unloaded before G2. No concurrent model inference was performed.

The isolated environment occupies about 289 MiB; project NLI files about 343 MiB.
Disk free after setup was about 5.2 GiB. Generated logs, pip reports, weights and
caches remain ignored. The committed `docs/engineering/LOCAL_AI_REAL_VALIDATION.json`
contains only sanitized synthetic measurements. No private memories were indexed.
Long documents, memory-pressure failure injection, repeated production workloads,
real-world bilingual accuracy and full local orchestration remain unverified.
