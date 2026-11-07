# Measured Model Benchmarking

**Branch:** \`oracle/phase-03-model-benchmarking\`  
**Depends on:** PR #12 (memory consolidation), then PR #11 → PR #10 and preceding stacked work.

## Objective

Provide repeatable, privacy-conscious measurements for configured model candidates before using performance data to influence routing.

The benchmark compares an explicit list of \`provider/model\` pairs against the same bounded evaluation suite. It records:

- Request outcome (success/error).
- End-to-end latency in milliseconds.
- Output length in characters.
- Optional numeric rubric score from 0 to 1.
- Evaluator ID, so scores from different evaluators are never mixed.
- Error class name only; no exception text.

Normal runtime observations from \`model_observability\` are also included in scorecards as a conservative health signal.

## Explicit execution and cost control

No benchmark is started automatically by the application.

\`run_benchmark(...)\` requires an explicit candidate list and an explicit call. The default configuration permits only an Ollama endpoint bound to loopback (\`localhost\`, \`127.0.0.1\`, or \`::1\`). Hosted providers and non-loopback Ollama endpoints require \`allow_remote=True\`.

That flag acknowledges that a provider may charge for requests and will receive the benchmark messages. The implementation does not make provider calls during import, app startup, or CI tests. CI uses injected fake runners.

A benchmark is bounded to:
- 20 model candidates.
- 50 cases in a suite.
- 250 total candidate-case requests per run.
- 5,000 benchmark result rows per scorecard analysis.

## Evaluation suite and rubric

The bundled \`benchmarks/model_benchmark_cases.json\` contains six synthetic smoke checks: simple arithmetic, positive/negative classification, a short Arabic instruction-following task, and a simple geography lookup.

The built-in \`phrase_rubric_v1\` checks whether required phrases appear and forbidden phrases do not appear. It is deterministic and reproducible, but it is not semantic evaluation, factual verification, or a broad measure of model intelligence.

A caller may provide a custom \`quality_evaluator(case, answer)\` and a stable \`quality_evaluator_id\`. A custom evaluator must return a finite score between 0 and 1. Evaluator failures are recorded as an error class and do not discard the latency/outcome measurement.

Cases within a default phrase-rubric suite must use consistent rubric coverage. This prevents the denominator from silently mixing scored and unscored cases.

## Privacy contract

Benchmark prompts and completions exist in process memory only. They are not written to the benchmark database or ordinary model telemetry.

Persisted benchmark results include only:
- Scope, provider, model, suite/run ID and case ID.
- Task type, latency, outcome and output character count.
- Optional quality score and evaluator ID.
- Exception class names, never exception messages.

The model event table continues to omit prompts, completions, messages, and tool inputs. Benchmark tables are added to the explicit sensitive-table wipe allowlist.

The executor now honors \`request.context.metadata["owner_scope"]\` for telemetry. This keeps benchmark observations within the same owner scope as the benchmark run, even when a different ambient environment scope is configured.

## Scorecards and ranking

\`scorecards(scope)\` produces per-model, per-evaluator scorecards. It does not combine different evaluator IDs into a single quality score.

Default evidence thresholds:
- At least 3 benchmark samples.
- At least 3 scored samples.

The default score is:

\`0.65 × average_quality + 0.20 × effective_success_rate + 0.15 × latency_score\`

Where:
- \`effective_success_rate\` is the lower of benchmark success and runtime success, when enough runtime observations exist; otherwise it is benchmark success.
- \`effective_p95_latency\` is the higher of benchmark p95 and runtime p95.
- \`latency_score = min(1, target_latency_ms / effective_p95_latency_ms)\`.

A model below the minimum evidence thresholds receives no ranking score and is marked ineligible. Scorecards include the sample and coverage counts, measured p50/p95 latency, runtime request count, and an explicit eligibility reason.

These weights and thresholds are initial policy defaults, not statistically calibrated constants. The ranking is an evidence-based comparison aid, not an automatic route change.

## APIs

- \`model_benchmark.load_suite()\` — load the bundled synthetic smoke suite.
- \`model_benchmark.run_benchmark(scope, suite, candidates, ...)\` — run the explicit candidate/case matrix.
- \`model_benchmark.get_run(scope, run_id)\` — inspect run counters and status.
- \`model_benchmark.list_results(scope, run_id=...)\` — read privacy-safe per-case results.
- \`model_benchmark.scorecards(scope, ...)\` — calculate evidence-gated scorecards.

Example:

\`\`\`python
from model_benchmark import ModelCandidate, load_suite, run_benchmark, scorecards

suite = load_suite()
run = run_benchmark(
    scope="owner:local",
    suite=suite,
    candidates=[
        ModelCandidate("ollama", "qwen2.5:7b"),
        ModelCandidate("ollama", "llama3.1:8b"),
    ],
)
print(run)
for card in scorecards("owner:local"):
    print(card)
\`\`\`

For hosted candidates, the caller must explicitly pass \`allow_remote=True\`.

## Current limitations

- The default suite is intentionally small and synthetic.
- Phrase matching does not detect semantic paraphrases, fabricated reasoning, or unsupported factual claims.
- No real provider benchmark was executed by CI; CI verifies the runner and persistence using fake providers.
- Provider adapters currently discard token-usage metadata, and cost is not measured or inferred.
- Quality scores are only comparable when they use the same suite ID, evaluator ID and compatible rubric semantics.
- ModelRouter continues to follow explicit/category/tier configuration. Scorecards do not automatically change the router.
- No token throughput, memory usage, energy use, or hardware-normalized metrics are recorded.
- A future router integration must keep manual provider/model overrides, privacy boundaries, and cost controls authoritative.
