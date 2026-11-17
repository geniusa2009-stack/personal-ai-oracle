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

Ollama's OpenAI-compatible embeddings endpoint is used by the existing `OpenAICompatibleEmbeddingClient`; no API key is required for the local loopback endpoint.

### 2. Configure G1

Set these values in your local, untracked environment file (never commit secrets or machine-specific paths):

```dotenv
ORACLE_MEMORY_EMBEDDINGS_ENABLED=1
ORACLE_EMBEDDING_PROVIDER=ollama
ORACLE_EMBEDDING_MODEL=embeddinggemma-2:270m
ORACLE_EMBEDDING_BASE_URL=http://127.0.0.1:11434/v1
ORACLE_MEMORY_EMBEDDINGS_AUTOINDEX=0
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
