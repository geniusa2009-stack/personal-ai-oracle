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

## Bounded autonomous revision loop

A rejected completed graph can be revised only after an explicit user action in the Control Center. Revision does not dispatch work automatically.

1. Oracle reads the persisted final-review issues (or the review summary when the issue list is empty).
2. A revision planner maps every issue to one or more existing specialist task keys. It may select only source tasks present in the effective result set; the specialist role is derived from the stored source result, never trusted from model output.
3. The planner returns a strict bounded schema. Unknown task keys, extra fields, duplicate selections, invalid issue indexes, uncovered issues, and invalid dependencies are rejected.
4. Oracle creates a new encrypted DAG linked to the root graph and its immediate parent graph. Each revision task receives its previous output, assigned review issues, prior dependency outputs, and any already-revised dependency output.
5. Only selected specialists are rerun. Unselected specialist outputs are inherited unchanged when the next final review builds the merged result set.
6. A new final-review task depends on all selected revision tasks and reviews the merged result set against the original request and previous review issues.
7. The user explicitly dispatches bounded batches from the Control Center. Pending revision work and completed outputs survive app restarts.

### Revision limits and lineage

- Maximum revision cycles per root graph: `MAX_REVISION_CYCLES = 2`.
- Maximum specialist tasks in one revision cycle: 8.
- Maximum review issues carried into one cycle: 12.
- Revision graph idempotency keys are deterministic per root graph and cycle. Repeated clicks return the same child graph instead of creating duplicate branches.
- A stale parent cannot create a parallel branch after a newer revision exists. The next cycle must continue from the latest graph.
- The hard cap counts created revision graphs, even if a user later cancels one; a cancelled cycle is not silently refunded.
- Each revision graph persists the root graph ID, immediate parent graph ID, and cycle number inside encrypted owner-scoped task payloads.
- The final reviewer is still a completeness/internal-consistency reviewer, not an independent fact verifier. It cannot certify factual truth.
- At the cap, the UI reports that no further automatic revision cycle can be created. The user can still inspect/export the current work or create a new independent task.

### Safety and cost boundaries

- The revision planner and specialists cannot emit or execute tools, shell commands, browser actions, filesystem operations, or Mac actions.
- Revision creation and execution are separate explicit user actions; there is no autonomous background loop.
- Provider failures are not automatically retried by the handler. Expired worker leases have the existing bounded retry behavior; a crash after a provider response but before encrypted result persistence can repeat a provider call and incur duplicate cost.
- A revision planner call can incur provider cost before a revision graph is persisted. A retry after a process interruption may call the planner again; deterministic graph idempotency prevents duplicate persisted cycles.

## Limits and next work

- Revision decisions are model assessments of request coverage and internal consistency; source-level fact verification remains separate.
- The first implementation uses deterministic mocked provider tests. Live provider behavior, deployed Streamlit interaction, and restart behavior on a physical Mac remain operational validation items.
- Specialist tasks still do not execute Mac tools. Connecting tool execution later requires a separate typed handler catalogue and must preserve the local approval/checkpoint boundary.
