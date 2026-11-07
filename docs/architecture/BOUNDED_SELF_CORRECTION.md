# Bounded Self-Correction and Loop Prevention

**Branch:** \`oracle/phase-03-bounded-self-correction\`  
**Depends on:** PR #13 (measured model benchmarking), then PR #12 → PR #11 → PR #10 and the earlier stacked phases.

## Goal and scope

Add a small, auditable correction loop for two text-generation boundaries:

1. **Agent planning:** repair malformed planner JSON or a plan that contains no usable catalogued tool step *before any tool is executed*.
2. **Deep Research synthesis:** repair malformed response JSON, an empty answer, missing inline citations, or citation IDs that are not present in the current research evidence set.

This is not an autonomous action retry engine. Tool execution and research collection remain outside the correction loop.

## Shared correction engine

\`bounded_correction.run_bounded_correction(generate, repair, validate, ...)\` is a callback-based, text-only loop.

- Default: one correction retry (two text-generation attempts total).
- Hard ceiling: two retries (three generation attempts total).
- Each output is checked by a caller-supplied deterministic validator.
- A configured non-retryable issue ends the loop immediately.
- A repeated output fingerprint ends the loop.
- A repeated validation-issue signature ends the loop.
- Exhausting the retry budget ends the loop.
- Generation/repair exceptions are reduced to the exception class name for control metadata.
- The result contains only attempt numbers, SHA-256 output fingerprints, issue codes, pass/fail flags and a stop reason. It does not return the raw output in its metadata dictionary.

The retry cap is validated before execution. Outputs are bounded to a maximum size. The module exposes no tool-execution callback or local-action API.

## Agent planner integration

\`agent_orchestrator._build_next_step\` now uses the correction engine before returning a planned tool step.

Deterministic validation checks:
- The planner response is JSON and an object.
- The \`steps\` field is a list.
- A proposed step maps to a currently available tool ID (or a known legacy feature ID).
- The input is a supported string/object, non-empty and within the existing tool-input limit.
- The exact tool/input signature has not already been used in this task.

A valid empty step list or a clarifying question is a valid planner decision. When several suggestions are present, the existing behavior is preserved: the first valid, unused step is selected; the agent replans after observing that step's result.

When the plan is malformed or contains no usable step, the planner may receive one repair-only prompt. The repair is another \`ai_core.chat\` call; it cannot invoke a tool.

### Explicit non-retry boundary

Once \`_build_next_step\` returns a valid step, the existing execution path runs it once. This phase does not automatically repeat:
- Local shell commands.
- File writes, moves or deletes.
- Application launches.
- Browser navigation or page fetching.
- Web searches.
- Any other tool execution or side effect.

If a tool fails, the agent may observe the result and make a new plan within its existing step budget, but it does not replay the same tool call automatically. Existing approvals, checkpoints, scope restrictions and executor policy remain authoritative.

## Deep Research synthesis integration

\`deep_research._synthesize\` validates the model-generated JSON before using the response:

- Response must be valid JSON with an object shape.
- The answer must be a non-empty string.
- Declared citation IDs must be well-formed list entries.
- Every cited/declared source ID must belong to the current evidence set.
- The answer must contain at least one valid inline citation when evidence sources were supplied.

The default is one correction retry. Callers can set \`max_correction_retries\` from 0 to 2. The repair prompt contains the previous response as untrusted data and the deterministic issue codes. It tells the model to use only the original evidence and allowed source identifiers.

If the provider returns a recognized execution-error response, correction is not retried. The final research report includes a compact \`self_correction\` summary:
- Status, attempt count and retry count.
- Whether the answer was corrected.
- Stop reason.
- Remaining deterministic issue codes.
- Per-attempt hashes and validation issue codes.

The same report metadata is preserved in \`compact_report_json\`. Raw previous outputs are not placed in the correction summary.

## Stop reasons

The shared engine reports bounded outcomes such as:
- \`validated_first_attempt\`
- \`validated_after_retry\`
- \`non_retryable_issue\`
- \`repeated_output\`
- \`repeated_validation_issues\`
- \`retry_limit_reached\`
- \`generation_error\`
- \`repair_error\`

A failed correction is not represented as a successful answer. Deep Research continues to report unresolved citation issues in its normal citation validation and limitations.

## Validation

Tests cover:
- Valid first attempt without another model call.
- One correction producing a valid result.
- Repeated output and repeated-issue loop termination.
- Provider errors that must not be retried.
- Retry/input size hard caps.
- Metadata reports that do not contain the generated answer text.
- Agent planner correction for invalid JSON/unknown tool IDs before execution.
- Planner loop termination when the same malformed output repeats.
- No tool executor call during planner correction.
- Deep Research correction of invalid citations without re-running search.
- Repeated invalid citation output stopping within the retry budget.
- Provider errors and zero-retry configuration.

GitHub Actions validation runs on Ubuntu and macOS.

## Limitations

- The validators check output structure, tool catalogue membership, input bounds and citation integrity. They do not prove factual correctness or semantic entailment.
- No independent second model is used as a general judge in this phase.
- The Deep Research repair only regenerates the synthesis; it does not re-run search, fetch pages or semantic evidence assessment.
- A repaired answer can still be wrong despite passing deterministic validation. Existing semantic verification and source-evidence limitations continue to apply.
- The default single repair attempt can increase model latency and provider usage only when deterministic validation fails. Provider pricing and token usage are not inferred.
- This phase does not add automatic retries for tool failures, network errors, local operations or approval denials.
