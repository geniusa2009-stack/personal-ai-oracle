# Durable Task Engine

**Branch:** \`oracle/phase-04-durable-task-engine\`  
**Depends on:** PR #14 (bounded self-correction), then PR #13 → PR #12 → PR #11 → PR #10 and the earlier stack.

## Purpose and boundary

The existing workflow ledger records execution traces and the encrypted checkpoint store preserves approval-resume state. This increment adds a separate durable DAG queue: tasks can be persisted, dependencies can be evaluated, workers can claim leases, and attempts/results can be inspected after process restarts.

The queue is a scheduler and state store. **It does not execute tools, call models, run shell commands, or perform local/cloud side effects.** A worker must explicitly claim a task and then hand its payload to an independently configured executor. Existing agent orchestration, approval gates and execution policy remain authoritative.

No worker loop or recurring scheduler is started by importing this module. No LaunchAgent or background process is installed.

## Graph and task model

A graph contains 1–100 uniquely keyed tasks. Each task contains:
- A stable task key and task type.
- A JSON mapping payload, encrypted before persistence.
- Zero or more dependencies on other task keys in the same graph.
- A maximum attempt count from 1 to 5.
- An explicit \`retry_safe\` declaration, false by default.

Graph creation validates all dependency references and rejects cycles before writing. An idempotency key is unique within the owner's exact scope. Reusing the same key and same plan digest returns the existing graph. Reusing it for a different plan raises \`TaskIdempotencyConflict\`.

The graph plan digest includes each task key/type, payload digest and length, dependency set, retry limit and retry-safety declaration. Raw task payloads are not written to the graph metadata row.

## Persistence and privacy

New SQLite tables:
- \`oracle_task_graphs\`: graph identity, exact owner scope, idempotency key, plan digest, status and timestamps.
- \`oracle_durable_tasks\`: task status, encrypted payload/result, hashes, attempt limits, lease fields and bounded error code.
- \`oracle_task_dependencies\`: directed prerequisite edges.
- \`oracle_task_attempts\`: worker/attempt status, durations, result hash/length and compact error code.

Task payloads and results use the same Fernet encryption key and owner-scope binding as workflow checkpoints. The ciphertext is stored in SQLite; an embedded scope value is checked again after decryption. Losing the configured/generated checkpoint key means those encrypted values cannot be read.

Lease tokens are generated randomly and only their SHA-256 digest is stored. A live operation must present the exact owner scope, worker ID and lease token. Comparisons use constant-time digest comparison. Task/lease dataclass representations redact payloads and lease tokens.

The new tables are included in the explicit \`database.panic_wipe\` allowlist.

## Claim and execution protocol

A worker uses this sequence:

1. \`claim_next(scope, worker_id, lease_seconds=...)\` atomically leases one ready task.
2. The returned \`TaskLease\` includes the decrypted payload, task type, lease token, attempt number and expiry. The caller must not log the lease object or its payload.
3. \`start_task(...)\` moves the task from \`leased\` to \`running\` before the worker starts external work.
4. The worker periodically calls \`heartbeat(...)\` to extend the lease while the work is still active.
5. The worker calls \`complete_task(..., result)\` to persist an encrypted result, or \`fail_task(...)\` with a short error code.

A task is claimable only when:
- Its graph is active.
- Its task is queued and available.
- Its attempt budget is not exhausted.
- Every declared parent task is \`succeeded\`.

Claims use a SQLite immediate transaction and a conditional state update so two workers cannot successfully claim the same queued task. Lease operations fail when the lease is expired, has been replaced, or is owned by a different worker/token.

## State transitions

Task statuses:
- \`queued\` — waiting for availability and prerequisites.
- \`leased\` — claimed by one worker but not yet started.
- \`running\` — worker explicitly acknowledged the start.
- \`succeeded\` — result was durably stored.
- \`failed\` — terminal failure or exhausted retry budget.
- \`blocked\` — prerequisite failed, was blocked or was cancelled.
- \`cancelled\` — graph cancellation stopped further scheduling.

Graph statuses:
- \`active\`, \`paused\`, \`completed\`, \`failed\`, \`cancelled\`.

A graph completes only when every task succeeds. A graph fails when no tasks remain pending and at least one task is failed, blocked or cancelled.

## Retry and lease-expiry policy

Retry is deliberately conservative:
- \`retry_safe=False\` by default, and requires \`max_attempts=1\`.
- A task can be configured with more attempts only when the caller explicitly marks it \`retry_safe=True\`.
- A retry still requires the worker to report a retryable failure, and the attempt budget must remain.
- Retry delay uses bounded exponential backoff, capped at 300 seconds.
- Expired leases are reaped. Expired work is requeued only when it was explicitly declared retry-safe and has remaining attempts; all other expired work becomes failed.

The engine cannot prove that a task is truly idempotent. The caller is responsible for making that declaration only when repeating the task is safe. The queue does not infer retry-safety from the task type or error code.

A lease that was acquired but never moved to \`running\` can be released during graph pause without consuming an execution attempt. Already-running work is not automatically replayed.

## Pause and cancellation

- Pausing a graph stops new claims.
- Unstarted leases are returned to the queue and their unused attempt reservation is removed.
- Already-running tasks retain their live lease so the worker can finish or cooperatively stop. A paused graph cannot issue new leases.
- Resuming reactivates scheduling.
- Cancelling a graph cancels queued/leased/running task records and invalidates their leases.

Cancellation is a durable queue state change, not a forceful process kill. An external operation already in progress must cooperate with cancellation at its own execution boundary. The queue cannot undo a completed external side effect.

## Limits

- 100 tasks per graph.
- 5 attempts maximum per task.
- 5–3,600 seconds per lease.
- 300 seconds maximum retry backoff.
- 200 graph/task listing limit.
- Encrypted payload and result sizes use the existing 256 KiB checkpoint payload limit.

## APIs

- \`create_graph(scope, idempotency_key, tasks)\`
- \`get_graph(scope, graph_id)\`, \`list_graphs(scope)\`
- \`get_task(scope, task_id, include_payload=..., include_result=...)\`
- \`list_tasks(scope, graph_id, include_payload=...)\`
- \`claim_next(scope, worker_id, lease_seconds=...)\`
- \`start_task(scope, task_id, worker_id, lease_token)\`
- \`heartbeat(scope, task_id, worker_id, lease_token, lease_seconds=...)\`
- \`complete_task(scope, task_id, worker_id, lease_token, result)\`
- \`fail_task(scope, task_id, worker_id, lease_token, error_code, retryable=..., retry_delay_seconds=...)\`
- \`reap_expired_leases(scope)\`
- \`pause_graph(scope, graph_id)\`, \`resume_graph(scope, graph_id)\`, \`cancel_graph(scope, graph_id)\`
- \`list_attempts(scope, task_id)\`

Stored \`error_code\` values must be short identifiers. Free-form exception messages are rejected so paths, provider details or user content cannot be accidentally persisted as error telemetry.

## Validation

\`test_durable_task_engine.py\` verifies:
- DAG validation, cycle rejection, unknown dependency rejection and idempotent graph creation.
- Dependency ordering and encrypted payload/result round trips.
- Unique atomic claims and lease owner/token checks.
- Heartbeats and lease expiry.
- Default no-retry behavior and explicitly retry-safe bounded attempts.
- Failed dependency propagation to descendants.
- Pause/resume behavior for unstarted leases and cooperative cancellation state.
- Scope isolation, sensitive-table wipe coverage and secret redaction.
- Rejection of unsafe retry settings, invalid worker/lease values and free-form error details.

The full repository test suite is run on GitHub Actions for Ubuntu and macOS.

## Known limitations

- No production worker is wired to execute these tasks yet. The queue APIs are ready for a separate adapter, but task-type handlers and execution allowlists still need to be designed and tested.
- No recurring scheduler/cron or automatic startup worker is included.
- The Streamlit Control Center does not yet expose graph creation, dependency visualization, worker leases, retries, pause/resume or cancellation.
- Cancellation is cooperative for work that has already started outside the queue.
- Retry-safety is a caller assertion; the engine cannot prove external idempotency.
- SQLite table creation is additive but there is no general versioned migration framework yet.
- There is no distributed multi-host coordination guarantee beyond SQLite's transactional claim semantics on a shared database file.
- The engine does not replace the Workflow Ledger or approval-bound encrypted checkpoints; it complements them.
