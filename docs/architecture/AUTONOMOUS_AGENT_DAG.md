# Autonomous Planner and Specialist-Agent DAG

**Branch:** `oracle/phase-04-autonomous-task-planner-dag`  
**Dependency:** PR #19 → PR #18 → PR #17 and the earlier stacked Oracle work.

## End-to-end flow

1. The user submits a bounded request and a stable idempotency key.
2. The planner model returns a strict JSON plan containing 1–8 typed specialist steps.
3. Application validation rejects unknown roles, extra fields, malformed keys, missing dependencies, duplicate dependencies, and oversized instructions.
4. The application appends a `final_review` task that depends on every specialist task.
5. The durable task engine validates the DAG for cycles and persists each task payload encrypted and owner-scope-bound.
6. A user explicitly dispatches a bounded batch. The worker claims only the two registered agent task types; it has no shell, browser, filesystem, or generic tool fallback.
7. Ready tasks execute only after all declared dependencies have succeeded. Each specialist receives only its own instruction and the allowlisted outputs of its declared dependencies.
8. Every task result is persisted encrypted before the worker advances. The final reviewer cannot run until all specialist tasks have succeeded.
9. The result projection exposes bounded outputs and the final review decision only to the matching owner scope.

## Specialist roles

The planner may select only:
- `researcher`
- `coder`
- `writer`

The planner itself is used only to create the DAG. The final `reviewer` is appended by application code and cannot be removed by model output. The `executor` role is deliberately excluded from this task DAG because local actions require the separate deterministic execution-policy and approval path.

Specialist prompts explicitly prohibit claiming that a tool, browser, filesystem, or external action was performed. This milestone is agent reasoning and content production, not arbitrary tool execution.

## Dependency and persistence semantics

- The durable engine's existing dependency scheduler controls readiness.
- A handler reads only successful dependency results from the same owner scope and graph.
- Payloads and results use the existing scoped encryption layer.
- Repeated submission with the same idempotency key and same validated plan returns the existing graph; a different plan with the same key conflicts.
- Pending and succeeded tasks survive application restarts. The user can dispatch another bounded batch after reopening the app; already-succeeded tasks are not repeated.
- Agent tasks allow at most two attempts for an expired worker lease. This supports recovery when the process disappears while a task is leased. **A process interruption after a provider call but before result persistence can cause that call to be repeated and may incur duplicate provider cost.** Ordinary handler exceptions are not automatically retried.
- There is no daemon, polling loop, LaunchAgent, scheduler, or persistent worker activation in this milestone.

## Final review contract

The final review task evaluates request coverage, completeness of specialist outputs, and internal consistency. It returns one of:
- `accepted`
- `needs_revision`
- `incomplete`

A graph being `completed` means all scheduled tasks, including the reviewer task, ran successfully. It does **not** mean the reviewer accepted the deliverable. The UI/API must check `accepted` / `final_review.decision` before presenting the work as accepted.

The reviewer is not an independent factual verifier. Results explicitly expose `factual_truth_verified: false`; external facts and citations still require source-level verification.

## Limits and next work

- The first version does not automatically revise a `needs_revision` graph. A later increment can create a new revision graph from the review issues, with a bounded revision count and explicit user approval.
- Specialist tasks do not execute Mac tools. Connecting tool execution later requires a separate typed handler catalogue and must preserve the local approval/checkpoint boundary.
- Planning depends on the configured planner model. If planning or validation fails, no graph is created.
- Provider calls are mocked in deterministic tests; live provider behavior, real deployment, and restart behavior on a physical Mac remain operational validation items.
