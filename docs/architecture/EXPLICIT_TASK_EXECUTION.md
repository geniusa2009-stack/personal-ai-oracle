# Explicit Deep Research Task Submission and Dispatch

**Branch:** `oracle/phase-04-explicit-task-dispatch`  
**Base:** `oracle/phase-04-control-center-tasks` (PR #17)  
**Execution mode:** Explicit, caller-invoked, one task per dispatch.

## Purpose

This milestone connects the durable DAG queue to one real Oracle capability: Deep Research. It closes the gap between a queue that can only be inspected and a queue that can accept and execute a bounded, typed task.

## Submission contract

`task_execution.create_research_graph` accepts an owner scope, an idempotency key, a query, and bounded Deep Research options. It creates one task with type `oracle.deep_research`.

- Query length is limited by the existing Deep Research contract (500 characters).
- Query count and source count use the existing Deep Research bounds.
- Boolean options are type-checked.
- Freshness profiles are allowlisted and validated before the task is persisted.
- The task payload is encrypted by the existing durable task engine.
- Research tasks are explicitly non-retryable (`retry_safe=False`, one attempt) because a retry can repeat provider calls and cost.

The queue's existing idempotency key prevents accidental duplicate submission. Reusing a key for a different query/plan is rejected by the durable engine.

## Handler and dispatch contract

The only built-in handler in this milestone is `oracle.deep_research`.

- The handler accepts an exact, validated payload schema.
- It calls the existing `deep_research.run_research` implementation with the task's owner scope.
- It preserves a bounded answer, findings, limitations, citations, source excerpts, evidence summary, quality summary, semantic-verification summary, and freshness summary.
- It does not expose raw prompts, full page bodies, arbitrary tool execution, shell access, file operations, browser control, or model-provider selection.
- A no-source research result is recorded as a failed task.
- Provider or execution errors are reduced to exception-class codes by the existing worker adapter.
- The task is never automatically retried.

`dispatch_research_once` calls the existing worker adapter for at most one registered research task. It does not poll, sleep, spawn a process, or activate a persistent service.

## Control Center integration

The Oracle Control Center now allows the owner to:
1. Submit a bounded research query into the durable queue.
2. Explicitly run one queued research task.
3. Inspect the task status and attempt metadata.
4. View an allowlisted result preview for a succeeded research task.

The result preview is loaded only from the current owner scope. It does not return the encrypted payload, ciphertext, raw task object, or arbitrary result keys.

## Validation strategy

`test_task_execution.py` uses a temporary SQLite database, a test encryption key, and an injected deterministic research function. It covers:
- Encrypted owner-scoped graph creation and idempotency.
- Invalid query/options/profile rejection.
- One-task dispatch and integration with the existing durable queue.
- Bounded result projection and source URL validation.
- No-source failure without retry.
- Unknown payload-field rejection.
- No-op behavior when no research task is queued.
- Idempotency-key conflict handling.

CI runs the complete offline test suite and Python compilation on Ubuntu and macOS. No live provider call is part of CI.

## Limitations

- This is a manually invoked one-shot worker path, not a production daemon or scheduler.
- Only Deep Research is registered; other task types remain queued until an explicit handler is implemented.
- Live search/provider behavior, real-world latency/cost, and deployed Streamlit interaction are not validated by deterministic tests.
- No distributed worker, concurrency supervisor, automatic startup, recurring schedule, or background polling is added.
- Research results are stored encrypted; the UI exposes only the bounded allowlisted preview.
- Research task retry is disabled by design.
