"""Privacy-preserving durable execution traces for Personal AI Oracle.

Only task/input/output digests and bounded execution metadata are persisted.
The actual task text, tool arguments, file contents, and tool outputs are never
stored by this module.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from database import init_database
from db import get_conn


MAX_SCOPE_LENGTH = 255
MAX_TOOL_ID_LENGTH = 128
MAX_RUNS_LIMIT = 100
MAX_STEPS_PER_RUN = 30
RUN_STATUSES = frozenset({"running", "completed", "partial", "failed", "cancelled"})
_STEP_STATUSES = frozenset({
    "running", "success", "active", "completed", "failed", "error",
    "blocked_by_executor", "skipped", "unknown",
})
_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")


class WorkflowLedgerError(ValueError):
    """Raised when trace metadata is invalid or scope ownership does not match."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _scope(value: str) -> str:
    if not isinstance(value, str) or not (value := value.strip()):
        raise WorkflowLedgerError("scope is required")
    if len(value) > MAX_SCOPE_LENGTH:
        raise WorkflowLedgerError("scope is too long")
    return value


def _workflow_id(value: str) -> str:
    if not isinstance(value, str) or not _ID_PATTERN.fullmatch(value):
        raise WorkflowLedgerError("workflow_id is invalid")
    return value


def _digest(value: Any) -> tuple[str, int]:
    try:
        serialized = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    except Exception as exc:
        raise WorkflowLedgerError("trace payload could not be normalized") from exc
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest(), len(serialized)


def start_run(scope: str, task: str, max_steps: int) -> str:
    """Create a run record without storing its task text."""
    scope = _scope(scope)
    if not isinstance(task, str) or not task.strip() or len(task) > 12000:
        raise WorkflowLedgerError("task must be non-empty text up to 12000 characters")
    if isinstance(max_steps, bool) or not isinstance(max_steps, int) or not 1 <= max_steps <= MAX_STEPS_PER_RUN:
        raise WorkflowLedgerError("max_steps must be an integer from 1 to 30")
    task_digest, _ = _digest(task)
    workflow_id = uuid.uuid4().hex
    now = _now()

    init_database()
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO oracle_workflow_runs
               (workflow_id, scope, task_digest, status, max_steps, created_at, updated_at)
               VALUES(?, ?, ?, 'running', ?, ?, ?)""",
            (workflow_id, scope, task_digest, max_steps, now, now),
        )
        conn.commit()
        return workflow_id
    finally:
        conn.close()


def begin_step(
    scope: str,
    workflow_id: str,
    step_index: int,
    tool_id: str,
    tool_input: Any,
) -> None:
    """Persist a step-start checkpoint containing only a digest and tool metadata."""
    scope = _scope(scope)
    workflow_id = _workflow_id(workflow_id)
    if isinstance(step_index, bool) or not isinstance(step_index, int) or not 0 <= step_index < MAX_STEPS_PER_RUN:
        raise WorkflowLedgerError("step_index is outside the supported range")
    if (
        not isinstance(tool_id, str)
        or len(tool_id) > MAX_TOOL_ID_LENGTH
        or not re.fullmatch(
            r"(?:local|web)\.[a-z][a-z0-9_]*|feature:[1-9][0-9]*",
            tool_id.strip(),
        )
    ):
        raise WorkflowLedgerError("tool_id is invalid")
    input_digest, input_length = _digest(tool_input)
    now = _now()

    init_database()
    conn = get_conn()
    try:
        owned = conn.execute(
            """SELECT 1 FROM oracle_workflow_runs
               WHERE workflow_id = ? AND scope = ? AND status = 'running'""",
            (workflow_id, scope),
        ).fetchone()
        if not owned:
            raise WorkflowLedgerError("workflow is not active in this scope")
        conn.execute(
            """INSERT INTO oracle_workflow_steps
               (workflow_id, scope, step_index, tool_id, status, input_digest,
                input_length, created_at, updated_at)
               VALUES(?, ?, ?, ?, 'running', ?, ?, ?, ?)""",
            (workflow_id, scope, step_index, tool_id.strip(), input_digest, input_length, now, now),
        )
        conn.execute(
            "UPDATE oracle_workflow_runs SET updated_at = ? WHERE workflow_id = ? AND scope = ?",
            (now, workflow_id, scope),
        )
        conn.commit()
    finally:
        conn.close()


def complete_step(
    scope: str,
    workflow_id: str,
    step_index: int,
    result: MappingLike,
    *,
    duration_ms: int,
) -> None:
    """Complete a started step using status and result digests only."""
    scope = _scope(scope)
    workflow_id = _workflow_id(workflow_id)
    if isinstance(step_index, bool) or not isinstance(step_index, int) or not 0 <= step_index < MAX_STEPS_PER_RUN:
        raise WorkflowLedgerError("step_index is outside the supported range")
    if not isinstance(result, dict):
        raise WorkflowLedgerError("step result must be a mapping")
    if isinstance(duration_ms, bool) or not isinstance(duration_ms, int) or duration_ms < 0:
        raise WorkflowLedgerError("duration_ms must be a non-negative integer")
    status = str(result.get("status") or "unknown").strip().lower()
    status = re.sub(r"[^a-z0-9_-]", "_", status)[:40] or "unknown"
    if status not in _STEP_STATUSES:
        status = "unknown"
    output_digest, output_length = _digest(result)
    now = _now()

    init_database()
    conn = get_conn()
    try:
        cur = conn.execute(
            """UPDATE oracle_workflow_steps
               SET status = ?, output_digest = ?, output_length = ?,
                   duration_ms = ?, updated_at = ?
               WHERE workflow_id = ? AND scope = ? AND step_index = ? AND status = 'running'""",
            (
                status, output_digest, output_length, duration_ms,
                now, workflow_id, scope, step_index,
            ),
        )
        if cur.rowcount != 1:
            raise WorkflowLedgerError("no matching running step exists in this scope")
        conn.execute(
            "UPDATE oracle_workflow_runs SET updated_at = ? WHERE workflow_id = ? AND scope = ?",
            (now, workflow_id, scope),
        )
        conn.commit()
    finally:
        conn.close()


def finish_run(
    scope: str,
    workflow_id: str,
    status: str,
    *,
    error_code: str = "",
) -> bool:
    """Finish a run using a status and exception class, never an exception message."""
    scope = _scope(scope)
    workflow_id = _workflow_id(workflow_id)
    if status not in RUN_STATUSES - {"running"}:
        raise WorkflowLedgerError("invalid terminal workflow status")
    if not isinstance(error_code, str):
        raise WorkflowLedgerError("error_code must be text")
    error_code = re.sub(r"[^A-Za-z0-9_.-]", "_", error_code)[:80]
    now = _now()

    init_database()
    conn = get_conn()
    try:
        cur = conn.execute(
            """UPDATE oracle_workflow_runs
               SET status = ?, error_code = ?, updated_at = ?, finished_at = ?
               WHERE workflow_id = ? AND scope = ? AND status = 'running'""",
            (status, error_code, now, now, workflow_id, scope),
        )
        conn.commit()
        return cur.rowcount == 1
    finally:
        conn.close()


def list_runs(scope: str, *, limit: int = 30) -> list[dict[str, Any]]:
    """List bounded trace metadata for one owner scope."""
    scope = _scope(scope)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_RUNS_LIMIT:
        raise WorkflowLedgerError("limit must be an integer from 1 to 100")
    init_database()
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT workflow_id, scope, task_digest, status, max_steps,
                      created_at, updated_at, finished_at, error_code
               FROM oracle_workflow_runs WHERE scope = ?
               ORDER BY created_at DESC LIMIT ?""",
            (scope, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def list_steps(scope: str, workflow_id: str) -> list[dict[str, Any]]:
    """List a run's bounded step metadata only when the scope owns the run."""
    scope = _scope(scope)
    workflow_id = _workflow_id(workflow_id)
    init_database()
    conn = get_conn()
    try:
        owned = conn.execute(
            "SELECT 1 FROM oracle_workflow_runs WHERE workflow_id = ? AND scope = ?",
            (workflow_id, scope),
        ).fetchone()
        if not owned:
            return []
        rows = conn.execute(
            """SELECT step_index, tool_id, status, input_digest, output_digest,
                      input_length, output_length, duration_ms, created_at, updated_at
               FROM oracle_workflow_steps
               WHERE workflow_id = ? AND scope = ? ORDER BY step_index""",
            (workflow_id, scope),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


# A local alias avoids importing a type at runtime solely for annotations.
MappingLike = dict
