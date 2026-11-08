# Task Queue in Oracle Control Center

**Branch:** \`oracle/phase-04-control-center-tasks\`  
**Depends on:** PR #16 (typed worker adapter), PR #15 (durable DAG engine), then PR #14 and the earlier stack.

## What the UI exposes

The existing Oracle Control Center now has a Durable Task Queue panel showing:
- Owner-scope-local graph summaries and graph status.
- Task counts: total, succeeded, failed, blocked and pending/leased/running.
- Per-task key/type/status, attempt count, retry-safety flag, worker ID and compact error code.
- Attempt history: attempt number, worker, status, compact error code, duration, result digest and timestamps.

The display is intentionally metadata-only. It does not render task payloads, task results, encrypted ciphertext, prompts, or full exception messages.

## Graph controls

For an active graph, the UI exposes Pause and Cancel. For a paused graph, it exposes Resume and Cancel. Cancel requires a separate confirmation checkbox.

Pause stops new claims and releases leases that were acquired but not started. Work already in the running state may finish; the UI does not force-kill workers or undo external side effects.

Cancel changes the durable queue state and invalidates leases. A worker performing an external operation must cooperate with cancellation at its execution boundary.

Completed, failed or already-cancelled graphs do not expose further controls.

## No implicit worker execution

The panel does not:
- Create task graphs or arbitrary task payloads.
- Start \`dispatch_once\` or \`dispatch_batch\`.
- Start a background worker or recurring scheduler.
- Execute tools, shell commands, filesystem operations, browser actions or model calls.

The adapter still requires the application to supply explicitly registered task handlers. Until a production handler catalogue and supervised worker are added, this panel is for queue visibility and graph-state control only.

## Data layer

\`task_control_center.py\` owns the UI-facing projection:
- \`list_graph_summaries(scope)\` returns only graph metadata.
- \`get_graph_detail(scope, graph_id)\` returns an explicit allowlist of task metadata.
- \`list_task_attempts(scope, task_id)\` returns the engine's compact attempt audit.
- \`transition_graph(scope, graph_id, action)\` restricts actions to pause, resume and cancel.

The projection never returns task payloads or result content, even though the durable engine has separate owner-scoped APIs for retrieving them in worker code.

## Validation

\`test_task_control_center.py\` covers:
- Scope isolation.
- Payload/result/ciphertext exclusion.
- Attempt metadata without exception text.
- Pause/resume/cancel state transitions and invalid action rejection.
- Missing and out-of-scope graph handling.

The full CI run compiles the Streamlit application and runs the repository test suite on Ubuntu and macOS.

## Known limitations

- No live worker/handler health or process supervision is displayed.
- No queue auto-refresh/polling is enabled; the Streamlit page reruns on user interaction.
- No graph creation/editing or dependency-graph visualization is included.
- Running external side effects remain cooperative on cancellation.
