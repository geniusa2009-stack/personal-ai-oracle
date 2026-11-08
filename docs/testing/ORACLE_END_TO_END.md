# Oracle End-to-End Workflow

## Purpose

This milestone composes the existing memory, Deep Research, specialist-agent DAG, bounded revision, encrypted task persistence and Control Center projections into one explicit workflow.

It is an integration path, not a claim that all external facts are proven or that live provider quality has been calibrated.

## Workflow

```text
User request
  -> AI Core planner (scope-local memory retrieval)
  -> encrypted task DAG
       evidence_research (optional, enabled in Control Center by default)
         -> researcher/writer/coder specialist steps
              -> dependency-aware handoff of bounded research evidence
                   -> final completion review
                        -> accepted result
                        OR
                        -> bounded selective revision graph
                             -> merged inherited + revised results
                                  -> final revision review
  -> owner-scoped Control Center projection
```

When evidence research is enabled, one `oracle.deep_research` task is added to the same DAG. It is a prerequisite for all specialist tasks and the first final review. Each specialist receives only a bounded JSON projection of the sanitized research report. The projection includes available findings, limitations, citations, source excerpts, evidence summary, semantic summary and freshness summary.

The graph is encrypted and owner-scoped through the existing durable task engine. The research task is non-retryable. Specialist and reviewer tasks retain their existing bounded retry/lease behavior.

## Memory

Planner and specialist calls continue to use `ai_core.chat(..., memory_scope=scope)`. AI Core retrieves the relevant scope-local hybrid memory context, with lexical fallback if optional vector/graph retrieval is unavailable. Memory records remain contextual data, never instructions or authorization.

## Revision behavior

If the reviewer returns `needs_revision` or `incomplete`, the existing bounded revision flow can create a child graph. The original evidence research output is inherited in the effective result set and remains visible to the revision reviewer. It is deliberately excluded from the revision planner's selectable targets: corrections rerun specialist outputs, not the source-discovery task. Existing limits remain in force (at most two revision cycles, eight revision tasks per cycle and twelve review issues per cycle).

## Control Center

The Autonomous Task Planner form exposes:
- Evidence research enable/disable.
- Maximum query count (1–4).
- Maximum source count (1–8).
- Page extraction toggle.
- Claim/evidence review toggle.

Creating a graph does not dispatch it. The user must explicitly run a bounded batch for the selected graph. Evidence output is displayed with its summary, limitations and HTTP(S) citations. The selected graph ID is passed to dispatch to prevent cross-graph work from being claimed.

## Deterministic end-to-end test

Run the repository's normal offline test suite:

```bash
python -m pytest -q
```

`test_oracle_e2e.py` uses a temporary SQLite database, a generated test encryption key, mocked research output and a deterministic model boundary. It exercises:
- Scope-local memory context assembly.
- Planner and DAG creation.
- Research task persistence and dispatch.
- Evidence handoff to specialist inputs.
- First review rejection.
- Selective correction of only the affected specialist.
- Evidence inheritance into the revision review.
- Accepted merged result projection.
- Control Center owner-scope isolation.

No real search or model provider is called by this test.

## Live-provider validation boundary

Live validation is intentionally not run by CI and has not been performed by this milestone. It requires the operator to configure the existing provider/search credentials privately and explicitly initiate a run from the Control Center. Start with one query and one source, disable page extraction and semantic review for the first smoke test, and inspect provider telemetry before increasing limits.

The current repository does not yet expose a verified monetary/token budget across all providers. Query/source limits and task batch limits are not equivalent to a guaranteed dollar cap. Do not describe a live run as cost-capped until actual provider usage and billing metadata are integrated and tested.

## What this does not prove

- It does not prove factual truth; semantic review remains model-assisted.
- It does not validate a deployed Streamlit instance or physical Mac.
- It does not validate live provider quality, latency or cost.
- It does not activate a daemon, scheduler, persistent worker or local Mac executor.
- It does not establish production readiness.
