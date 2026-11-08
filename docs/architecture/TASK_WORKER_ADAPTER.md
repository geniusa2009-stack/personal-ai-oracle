# Durable Task Worker Adapter

**Branch:** \`oracle/phase-04-task-worker-adapter\`  
**Depends on:** PR #15 (durable DAG task engine), then PR #14 → PR #13 → the earlier stack.

## Purpose

The durable task engine stores and schedules work, but intentionally does not execute task payloads. This adapter adds a caller-supplied registry of typed handlers and a bounded dispatch entry point.

A handler is invoked only when its task type is explicitly present in the mapping passed to \`dispatch_once\` or \`dispatch_batch\`. Unknown task types are filtered out of the lease query and remain queued. There is no fallback that interprets a task payload as a shell command, file path, browser instruction, model prompt or arbitrary tool call.

No handlers are registered at module import, no worker starts on application startup, and no background service is installed.

## Handler contract

A \`TaskHandler\` contains:
- \`execute(payload, context)\` — a callable that returns a JSON-serializable mapping.
- \`retryable_exceptions\` — optional tuple of exception classes that the handler considers transient.
- \`retry_delay_seconds\` — bounded retry delay used when a retryable exception occurs.

The handler mapping is keyed by an explicit task type such as \`text.transform\`. The registry is validated on each dispatch call. Handler types are not inferred from untrusted payload content.

## Execution context

Each handler receives a \`TaskExecutionContext\` containing the owner scope, graph/task IDs and keys, task type, worker ID and attempt number.

The context exposes:
- \`heartbeat()\` — extends the active lease without returning the secret lease token to handler code.
- \`cancellation_requested()\` — checks durable task/graph state so long-running handlers can stop cooperatively.

The context's representation does not contain the lease token or task payload.

## Dispatch APIs

- \`dispatch_once(scope, worker_id, handlers, lease_seconds=...)\` claims and processes at most one task of a registered type.
- \`dispatch_batch(scope, worker_id, handlers, max_tasks=..., lease_seconds=...)\` processes a bounded sequential batch of at most 100 tasks. It does not sleep, poll indefinitely, or create a scheduler.
- If no registered type is ready, the API returns no work and leaves unsupported task types queued.

The adapter uses the durable engine's state protocol:
1. Claim a filtered task lease.
2. Mark the task running.
3. Invoke the registered handler with the decrypted payload and execution context.
4. Store a successful JSON mapping through the encrypted result path, or record a compact exception class name.
5. Return metadata about the dispatch outcome; raw handler results and exception messages are not copied to the dispatch report.

## Retry policy

A handler's retryable exception list is only one part of the decision. The stored task must also have been explicitly created with \`retry_safe=True\`, and its attempt budget must remain. The queue still controls the maximum attempt count and retry backoff.

Handler exceptions are stored by class name only. Exception messages, tracebacks, prompts, payloads and file contents are not stored by this adapter.

A handler that performs external side effects must not declare a task retry-safe unless it has its own idempotency protection. This adapter cannot prove that assertion.

## Side-effect and approval boundary

This module contains no built-in shell, filesystem, browser, app-launch, model-provider or generic tool handler. A caller may register a handler for a domain operation, but it must invoke the existing Oracle execution and approval paths rather than bypassing them.

The adapter itself does not:
- Execute a tool from a task payload.
- Re-run a failed external operation unless both the handler and task explicitly permit a retry.
- Force-kill a running handler when a graph is cancelled.
- Install a worker process or launch agent.
- Start any task without an explicit caller invocation.

Cancellation is cooperative. A long-running handler should periodically call \`context.cancellation_requested()\` and \`context.heartbeat()\`. If the graph is cancelled, the dispatcher will not persist a successful result for the cancelled task.

## Limits and validation

- At most 100 tasks per dispatch batch.
- Lease durations remain bounded by the durable task engine.
- Only explicitly registered task types can be leased by this adapter.
- Returned handler results must be JSON-serializable mappings.
- Invalid handler registries and retry exception declarations fail before work is claimed.

\`test_task_worker.py\` verifies:
- A bounded batch can complete a newly unblocked dependency in the same invocation.
- Unknown task types remain queued and do not invoke any handler.
- Handler context can heartbeat the lease and inspect cancellation.
- Retry only occurs when both the handler and stored task classify the work as retry-safe.
- Cancellation during a handler does not persist a successful task result.
- Error messages are not written to attempt history.
- Invalid handler registries and batch limits are rejected.

## Known limitations

- No built-in production handler registry is provided. The application still needs to decide which typed operations are appropriate and register them explicitly.
- The Streamlit Control Center does not yet expose worker registration, dispatch, queue state, lease health or cancellation controls.
- This adapter is synchronous and sequential. Parallel/concurrent worker orchestration, process supervision, health monitoring and recurring scheduling remain separate work.
- No durable worker daemon is started automatically.
- A running handler must cooperate with cancellation; already-completed external side effects cannot be undone by the queue.
