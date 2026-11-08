# Local Mac Execution Policy and Deletion Approval

**Branch:** `oracle/phase-07-deletion-approval-enforcement`  
**Dependency:** PR #18 → PR #17 → earlier stacked Oracle work.

## Operating model

The local Mac agent runs as the currently logged-in macOS user. It does not elevate to root, bypass macOS TCC prompts, or change operating-system security settings.

### Read-only operations

Directory listing, file reading, search, system diagnostics, process inventory, and application inventory remain available without a manual approval request, subject to macOS permissions and protected-path restrictions.

### Normal local mutations

A mutation can run without a separate approval only when the local Mac policy explicitly permits it:

- File creation/writing: the tool is listed in `auto_allow_tools` and the resolved destination is inside a configured trusted workspace.
- File move/rename: `local.move_path` is explicitly listed; source and destination resolve inside the same trusted workspace; the destination does not already exist.
- Development command: the command passes the existing executable/subcommand allowlist, its argv prefix is explicitly listed in `auto_run_commands`, and its working directory is inside a trusted workspace.
- App launch: the application name is explicitly listed in `allowed_applications`.

Outside those boundaries, the operation falls back to the exact one-time owner approval flow. The policy does not grant arbitrary shell access.

### Deletion invariant

`local.delete_path` always requires explicit owner approval, even when the path is inside a trusted workspace and even if a policy file mistakenly lists the tool in `auto_allow_tools`.

The invariant is enforced in both:
- `execution_policy.authorize_action`, which skips workspace auto-authorization for deletion.
- `local_tools._execute`, the shared local execution boundary used by direct local tool callers and the agent orchestrator.

An approved action is tied to the exact owner scope, tool ID, and canonical payload. Authorization creates a short-lived, single-use in-process execution grant. The grant is consumed by the local tool boundary and cannot be reused for a different payload or a second execution.

The orchestrator retains its checkpoint/resume flow: it pauses before a pending operation, records an encrypted checkpoint, and resumes only after the exact approval has been granted.

### Remote execution

The paired-Mac remote policy continues to reject remote deletion and remote move operations. Remote write/command/app operations require the Mac's explicit local workspace policy. The Mac agent rechecks policy before local execution.

## Tests

The deterministic test coverage includes:
- Direct `local_tools.execute` deletion cannot bypass approval.
- A trusted workspace policy cannot auto-authorize deletion.
- An approved delete executes only after the exact one-time approval is consumed.
- Writes and moves can be auto-authorized only within the configured trusted workspace.
- Moving to an existing destination requires approval.
- Development commands require both the local command allowlist and trusted working directory.
- Execution grants are single-use and bound to owner scope, tool ID, and exact payload.
- The agent's pause/approve/resume checkpoint flow continues to work.

## Important limitations

This is application-level enforcement for Oracle's registered local tool paths. It is not an operating-system sandbox and cannot prove the filesystem side effects of every arbitrary third-party program or project script. Obvious destructive shell commands remain outside the local executable allowlist, but a permitted test/build script could itself perform file operations. Therefore the project must not claim that arbitrary subprocess behavior is fully deletion-proof until commands run under a filesystem sandbox or equivalent OS-level mediation.

No persistent worker, LaunchAgent, admin privilege, or security-setting change is activated by this milestone.
