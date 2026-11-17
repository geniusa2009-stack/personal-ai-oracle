# Phase 04h isolated setup plan — approval required

No optional dependencies or weights have been installed/downloaded. The existing
`.venv` has only been used to run repository tests and metadata inspection; its
packages were not changed in Phase 04h. No new environment has been created pending
separate approval, as requested. `.venv-local-ai/` and `models/` are now gitignored.

## Verified machine and Python inventory

Read-only outside-sandbox checks: Darwin arm64, macOS 26.5.1, physical RAM
8,589,934,592 bytes (8 GiB). `memory_pressure -Q` reported 25% free at the audit
snapshot, not a guarantee of future headroom. Disk free approximately 7.3 GiB.
Ollama responds to `/api/tags`; installed models do not include
`embeddinggemma-2:270m`. No inference was attempted with other models.

No Python 3.11 executable was found on PATH, Homebrew's standard bin/opt paths or
the Python framework installation. Available: framework Python 3.13.5, Homebrew
3.15, Apple `/usr/bin/python3` 3.9.6. `uv`/`pyenv` were not found on PATH. This is
an inventory of standard installation locations, not a search of unrelated files.
Use existing framework Python 3.13.5 for the proposed isolated environment. Do not
install system Python; Python 3.11 remains the CI reference. If strict 3.11 parity
is preferred, a separately approved project-local interpreter is another step.

## Compatibility evidence and exact proposed artifacts

`local-ai-package-plan.json` records a candidate dependency graph resolved from
PyPI JSON metadata only, compatible with this host's Python 3.13.5/macOS arm64
wheel tags. `requirements-local-ai-plan.txt` pins that candidate. No distributions
were downloaded or imported; no pip installer resolution or binary smoke test is
claimed. The graph includes a conservative dependency superset from resolution;
installed/downloaded size may be smaller after authoritative pip resolution.

Direct packages satisfy `requirements-local-ai.txt`:

- onnxruntime 1.32.0: Python >=3.11, native cp313 macOS 14+ arm64 wheel,
  22,518,865 bytes; MIT upstream package license.
- transformers 4.57.6: Python >=3.9, universal wheel, 11,993,498 bytes;
  Apache-2.0 upstream package license. Its hub constraint is `<1.0,>=0.34.0`.
- sentencepiece 0.2.3: Python >=3.10, native cp313 macOS 11+ arm64 wheel,
  1,426,935 bytes; Apache-2.0 upstream package license.
- huggingface-hub 0.36.2: universal wheel, 566,395 bytes; compatible with the
  Transformers constraint and the repository's broader >=0.25,<2 range.

All 27 candidate wheel payloads total **51,387,232 bytes**. Exact filenames,
SHA-256 values, package Python constraints and available license metadata are in
the JSON plan. This is metadata compatibility, not VERIFIED_ON_TARGET_MAC inference.
PyTorch/TensorFlow extras are not requested. Expanded site-packages size cannot be
measured without installation; conservatively reserve 0.5–1 GiB for environment,
caches and transient installation files. No global packages or existing venv files
are to be changed.

Metadata sources: https://pypi.org/pypi/onnxruntime/json,
https://pypi.org/pypi/transformers/4.57.6/json,
https://pypi.org/pypi/sentencepiece/json,
https://pypi.org/pypi/huggingface-hub/0.36.2/json.

## Exact model payloads and provenance

Ollama registry manifest for `embeddinggemma-2:270m`:
303,957,280-byte GGUF layer plus 158-byte config = **303,957,438 bytes**.
Layer SHA-256: `111e84992a0406bacb70d11dddd8874001c783cc56b82c462ec82a2f5b8d08b1`.
Source: https://registry.ollama.ai/v2/library/embeddinggemma-2/manifests/270m.
Tag is mutable; confirm manifest/digest immediately before any approved pull.
EmbeddingGemma distribution terms must be reviewed at the upstream model card.

NLI upstream: `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli`, MIT model-card license,
revision `8adb042d524ecd5c26d3e3ba0e3fbcf7e2d0864c`.
Selected seven files total **359,318,185 bytes**; ONNX alone **338,679,133 bytes**.
ONNX SHA-256: `27c39e884c14b03cf46cfc5485971b6db70ff330220d93dfe729c63fde43af0e`.
The checked-in upstream manifest records sizes and upstream LFS hashes. The explicit
downloader now pins this revision, validates sizes and known hashes, and writes
actual hashes/provenance only after successful validation. Actual download integrity
and ONNX/tokenizer input-output contracts remain unverified until approved setup.
Source: https://huggingface.co/api/models/MoritzLaurer/mDeBERTa-v3-base-mnli-xnli?blobs=true.

Model payloads plus the conservative wheel set total **714,662,855 bytes**
(about 681.6 MiB), excluding metadata, pip bootstrap and transfer overhead.
Reserve roughly 1.5–2 GiB disk for expanded packages, models and transient/cache
copies; that is a planning allowance, not a measured install footprint.

## Proposed separate approved action

1. Create `.venv-local-ai` with the existing framework Python 3.13.5. Bootstrap pip
   only inside it; never use sudo/global pip or activate/modify `.venv`.
2. Resolve pinned candidate requirements with pip inside the new environment, save
   its report and verify artifact sizes/hashes before installation. Stop for a new
   decision if resolution differs materially or requires a source build.
3. Install only the approved binary packages. Verify imports/version/license metadata.
4. Recheck pressure and disk, then pull the approved small Ollama model; verify its
   manifest digest. Run synthetic G1 inputs with keep_alive=0, not private indexing.
5. Explicitly download the pinned NLI artifact using the isolated interpreter;
   verify hashes, tokenizer, ONNX names/shapes and label mapping.
6. Run `python -m scripts.evaluate_local_nli --mode cold` and `--mode session`
   sequentially, save actual results and measure pressure before/after. Test G1
   synthetic retrieval in a temporary database with two synthetic owner scopes.
7. Stop on resource-pressure failure. Do not infer memory recovery from deleting
   references. Record actual latency/RSS; do not declare compatibility from files.

Approval covers creating the isolated environment, installing its packages and
these specific model downloads/tests only. It does not cover private indexing,
system software, daemons, cloud inference or unrelated file access.

## Approved/executed status — 2026-11-17

The user subsequently approved this isolated setup. `.venv-local-ai` now exists with
27 installed binary packages and successful imports/pip check on Python 3.13.5.
Both models were downloaded with integrity verification; real sequential synthetic
G1/G2 inference succeeded on the actual 8 GiB Mac. Ollama selected its ~378 MB MLX
variant rather than the ~304 MB GGUF metadata variant; see the real validation
report for actual identity and measurements. Existing `.venv` and global packages
remain unchanged. The initial approval-pending paragraphs above are historical.
