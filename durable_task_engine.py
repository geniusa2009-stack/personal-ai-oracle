"""Scope-isolated durable DAG queue; this module schedules but never runs tools."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from database import init_database
from db import get_conn
import workflow_checkpoints

MAX_GRAPH_TASKS = 100
MAX_ATTEMPTS = 5
MAX_LEASE_SECONDS = 3600
MIN_LEASE_SECONDS = 5
MAX_RETRY_DELAY_SECONDS = 300
MAX_LIST_LIMIT = 200
_ID = re.compile(r"^[a-f0-9]{32}$")
_KEY = re.compile(r"^[A-Za-z0-9_.:-]+$")
_TYPE = re.compile(r"^[A-Za-z0-9_.-]+$")
_WORKER = re.compile(r"^[A-Za-z0-9_.:@-]+$")


class TaskEngineError(ValueError):
    """Invalid task graph, owner scope, lease or state transition."""


class TaskIdempotencyConflict(TaskEngineError):
    """An idempotency key was reused for a different graph definition."""


@dataclass(frozen=True)
class TaskSpec:
    task_key: str
    task_type: str
    payload: Mapping[str, Any]
    depends_on: tuple[str, ...] = ()
    max_attempts: int = 1
    retry_safe: bool = False


@dataclass(frozen=True)
class TaskGraph:
    graph_id: str
    scope: str
    idempotency_key: str
    status: str
    task_count: int
    succeeded_count: int
    failed_count: int
    blocked_count: int
    pending_count: int
    created_at: str
    updated_at: str
    finished_at: str | None


@dataclass(frozen=True)
class TaskLease:
    task_id: str
    graph_id: str
    scope: str
    task_key: str
    task_type: str
    payload: dict[str, Any]
    worker_id: str
    lease_token: str
    attempt_number: int
    max_attempts: int
    retry_safe: bool
    lease_expires_at: float


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _scope(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 255:
        raise TaskEngineError("scope is required and must be at most 255 characters")
    return value.strip()


def _label(value: Any, field: str, maximum: int, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise TaskEngineError(f"{field} is required and must be at most {maximum} characters")
    result = value.strip()
    if not pattern.fullmatch(result):
        raise TaskEngineError(f"{field} contains unsupported characters")
    return result


def _id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise TaskEngineError(f"{field} is invalid")
    return value


def _int(value: Any, field: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise TaskEngineError(f"{field} must be between {low} and {high}")
    return value


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _digest(value: Any) -> tuple[str, int]:
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TaskEngineError("payload must be JSON serializable") from exc
    return hashlib.sha256(raw).hexdigest(), len(raw)


def _normalise_specs(tasks: Sequence[TaskSpec]) -> tuple[TaskSpec, ...]:
    if not isinstance(tasks, (list, tuple)) or not 1 <= len(tasks) <= MAX_GRAPH_TASKS:
        raise TaskEngineError(f"tasks must contain 1 to {MAX_GRAPH_TASKS} entries")
    result = []
    for item in tasks:
        if not isinstance(item, TaskSpec):
            raise TaskEngineError("every task must be a TaskSpec")
        key = _label(item.task_key, "task_key", 100, _KEY)
        task_type = _label(item.task_type, "task_type", 80, _TYPE)
        if not isinstance(item.payload, Mapping):
            raise TaskEngineError(f"payload for {key} must be a mapping")
        payload = dict(item.payload)
        _, size = _digest(payload)
        if size > workflow_checkpoints.MAX_CHECKPOINT_BYTES:
            raise TaskEngineError(f"payload for {key} exceeds the encrypted payload limit")
        attempts = _int(item.max_attempts, "max_attempts", 1, MAX_ATTEMPTS)
        if not isinstance(item.retry_safe, bool):
            raise TaskEngineError("retry_safe must be a boolean")
        if not item.retry_safe and attempts != 1:
            raise TaskEngineError(f"non-retry-safe task {key} must use max_attempts=1")
        if not isinstance(item.depends_on, (list, tuple)):
            raise TaskEngineError(f"depends_on for {key} must be a sequence")
        deps = tuple(_label(dep, "dependency key", 100, _KEY) for dep in item.depends_on)
        if len(set(deps)) != len(deps):
            raise TaskEngineError(f"task {key} contains duplicate dependencies")
        result.append(TaskSpec(key, task_type, payload, deps, attempts, item.retry_safe))
    keys = [item.task_key for item in result]
    if len(set(keys)) != len(keys):
        raise TaskEngineError("task_key values must be unique")
    known = set(keys)
    for item in result:
        for dep in item.depends_on:
            if dep not in known or dep == item.task_key:
                raise TaskEngineError(f"task {item.task_key} has an unknown or self dependency")
    adjacency = {item.task_key: item.depends_on for item in result}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(key: str) -> None:
        if key in visiting:
            raise TaskEngineError("task dependency graph contains a cycle")
        if key in visited:
            return
        visiting.add(key)
        for dep in adjacency[key]:
            visit(dep)
        visiting.remove(key)
        visited.add(key)

    for key in keys:
        visit(key)
    return tuple(result)


def _plan_digest(specs: Sequence[TaskSpec]) -> str:
    canonical = []
    for item in sorted(specs, key=lambda value: value.task_key):
        payload_digest, payload_size = _digest(dict(item.payload))
        canonical.append({
            "task_key": item.task_key, "task_type": item.task_type,
            "payload_digest": payload_digest, "payload_size": payload_size,
            "depends_on": sorted(item.depends_on), "max_attempts": item.max_attempts,
            "retry_safe": item.retry_safe,
        })
    return _digest(canonical)[0]


def _graph_info(conn: Any, row: Any) -> TaskGraph:
    counts = conn.execute(
        """SELECT
           SUM(CASE WHEN status='succeeded' THEN 1 ELSE 0 END) AS succeeded,
           SUM(CASE WHEN status IN ('failed','cancelled') THEN 1 ELSE 0 END) AS failed,
           SUM(CASE WHEN status='blocked' THEN 1 ELSE 0 END) AS blocked,
           SUM(CASE WHEN status IN ('queued','leased','running') THEN 1 ELSE 0 END) AS pending
           FROM oracle_durable_tasks WHERE graph_id=? AND scope=?""",
        (row["graph_id"], row["scope"]),
    ).fetchone()
    return TaskGraph(
        graph_id=row["graph_id"], scope=row["scope"], idempotency_key=row["idempotency_key"],
        status=row["status"], task_count=int(row["task_count"]),
        succeeded_count=int(counts["succeeded"] or 0),
        failed_count=int(counts["failed"] or 0),
        blocked_count=int(counts["blocked"] or 0),
        pending_count=int(counts["pending"] or 0),
        created_at=row["created_at"], updated_at=row["updated_at"], finished_at=row["finished_at"],
    )


def _propagate_blocked(conn: Any, scope: str, graph_id: str) -> int:
    total = 0
    while True:
        cur = conn.execute(
            """UPDATE oracle_durable_tasks AS child SET status='blocked',updated_at=?
               WHERE child.scope=? AND child.graph_id=? AND child.status='queued'
                 AND EXISTS (
                   SELECT 1 FROM oracle_task_dependencies AS dep
                   JOIN oracle_durable_tasks AS parent
                     ON parent.task_id=dep.depends_on_task_id AND parent.scope=dep.scope
                   WHERE dep.task_id=child.task_id AND dep.scope=child.scope
                     AND parent.status IN ('failed','blocked','cancelled')
                 )""",
            (_now_iso(), scope, graph_id),
        )
        total += cur.rowcount
        if cur.rowcount == 0:
            return total


def _refresh_graph(conn: Any, scope: str, graph_id: str) -> None:
    graph = conn.execute(
        "SELECT status,task_count FROM oracle_task_graphs WHERE graph_id=? AND scope=?",
        (graph_id, scope),
    ).fetchone()
    if graph is None or graph["status"] in {"paused", "cancelled", "failed", "completed"}:
        return
    counts = conn.execute(
        """SELECT COUNT(*) AS total,
           SUM(CASE WHEN status='succeeded' THEN 1 ELSE 0 END) AS succeeded,
           SUM(CASE WHEN status IN ('failed','blocked','cancelled') THEN 1 ELSE 0 END) AS failed,
           SUM(CASE WHEN status IN ('queued','leased','running') THEN 1 ELSE 0 END) AS pending
           FROM oracle_durable_tasks WHERE graph_id=? AND scope=?""",
        (graph_id, scope),
    ).fetchone()
    total = int(counts["total"] or 0)
    succeeded = int(counts["succeeded"] or 0)
    failed = int(counts["failed"] or 0)
    pending = int(counts["pending"] or 0)
    status = "completed" if total == graph["task_count"] and succeeded == graph["task_count"] else (
        "failed" if pending == 0 and failed else "active"
    )
    now = _now_iso()
    conn.execute(
        """UPDATE oracle_task_graphs SET status=?,updated_at=?,
           finished_at=CASE WHEN ? IN ('completed','failed') THEN ? ELSE NULL END
           WHERE graph_id=? AND scope=?""",
        (status, now, status, now, graph_id, scope),
    )


def create_graph(scope: str, idempotency_key: str, tasks: Sequence[TaskSpec]) -> TaskGraph:
    """Create an encrypted DAG. Matching idempotency requests return the same graph."""
    scope = _scope(scope)
    idem = _label(idempotency_key, "idempotency_key", 160, _KEY)
    specs = _normalise_specs(tasks)
    plan_hash = _plan_digest(specs)
    now = _now_iso()
    graph_id = uuid.uuid4().hex
    task_ids = {item.task_key: uuid.uuid4().hex for item in specs}
    encrypted = {
        item.task_key: workflow_checkpoints.encrypt_scoped_payload(scope, dict(item.payload))
        for item in specs
    }
    digests = {item.task_key: _digest(dict(item.payload))[0] for item in specs}
    init_database()
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        old = conn.execute(
            "SELECT * FROM oracle_task_graphs WHERE scope=? AND idempotency_key=?",
            (scope, idem),
        ).fetchone()
        if old is not None:
            if old["plan_digest"] != plan_hash:
                raise TaskIdempotencyConflict("idempotency key already belongs to a different graph")
            return _graph_info(conn, old)
        conn.execute(
            """INSERT INTO oracle_task_graphs
               (graph_id,scope,idempotency_key,plan_digest,status,task_count,created_at,updated_at)
               VALUES(?,?,?,?,'active',?,?,?)""",
            (graph_id, scope, idem, plan_hash, len(specs), now, now),
        )
        for item in specs:
            conn.execute(
                """INSERT INTO oracle_durable_tasks
                   (task_id,graph_id,scope,task_key,task_type,status,payload_ciphertext,
                    payload_digest,attempt_count,max_attempts,retry_safe,available_at,created_at,updated_at)
                   VALUES(?,?,?,?,?,'queued',?,?,0,?,?,0,?,?)""",
                (
                    task_ids[item.task_key], graph_id, scope, item.task_key, item.task_type,
                    encrypted[item.task_key], digests[item.task_key], item.max_attempts,
                    int(item.retry_safe), now, now,
                ),
            )
        for item in specs:
            for dep in item.depends_on:
                conn.execute(
                    """INSERT INTO oracle_task_dependencies
                       (graph_id,scope,task_id,depends_on_task_id) VALUES(?,?,?,?)""",
                    (graph_id, scope, task_ids[item.task_key], task_ids[dep]),
                )
        row = conn.execute(
            "SELECT * FROM oracle_task_graphs WHERE graph_id=? AND scope=?",
            (graph_id, scope),
        ).fetchone()
        conn.commit()
        return _graph_info(conn, row)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_graph(scope: str, graph_id: str) -> TaskGraph | None:
    scope = _scope(scope)
    graph_id = _id(graph_id, "graph_id")
    init_database()
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM oracle_task_graphs WHERE graph_id=? AND scope=?",
            (graph_id, scope),
        ).fetchone()
        return _graph_info(conn, row) if row is not None else None
    finally:
        conn.close()


def list_graphs(scope: str, *, limit: int = 50) -> list[TaskGraph]:
    scope = _scope(scope)
    limit = _int(limit, "limit", 1, MAX_LIST_LIMIT)
    init_database()
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM oracle_task_graphs WHERE scope=? ORDER BY created_at DESC LIMIT ?",
            (scope, limit),
        ).fetchall()
        return [_graph_info(conn, row) for row in rows]
    finally:
        conn.close()


def get_task(
    scope: str,
    task_id: str,
    *,
    include_payload: bool = False,
    include_result: bool = False,
) -> dict[str, Any] | None:
    scope = _scope(scope)
    task_id = _id(task_id, "task_id")
    if not isinstance(include_payload, bool) or not isinstance(include_result, bool):
        raise TaskEngineError("include_payload and include_result must be booleans")
    init_database()
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT task_id,graph_id,scope,task_key,task_type,status,payload_ciphertext,
                      payload_digest,result_ciphertext,result_digest,attempt_count,max_attempts,
                      retry_safe,available_at,lease_owner,lease_expires_at,last_error_code,
                      created_at,updated_at
               FROM oracle_durable_tasks WHERE task_id=? AND scope=?""",
            (task_id, scope),
        ).fetchone()
        if row is None:
            return None
        item = dict(row)
        payload_cipher = item.pop("payload_ciphertext")
        result_cipher = item.pop("result_ciphertext")
        item["retry_safe"] = bool(item["retry_safe"])
        if include_payload:
            item["payload"] = workflow_checkpoints.decrypt_scoped_payload(scope, payload_cipher)
        if include_result and result_cipher:
            item["result"] = workflow_checkpoints.decrypt_scoped_payload(scope, result_cipher)
        return item
    finally:
        conn.close()


def list_tasks(
    scope: str,
    graph_id: str,
    *,
    limit: int = MAX_GRAPH_TASKS,
    include_payload: bool = False,
) -> list[dict[str, Any]]:
    scope = _scope(scope)
    graph_id = _id(graph_id, "graph_id")
    limit = _int(limit, "limit", 1, MAX_GRAPH_TASKS)
    if not isinstance(include_payload, bool):
        raise TaskEngineError("include_payload must be a boolean")
    init_database()
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT task_id FROM oracle_durable_tasks WHERE graph_id=? AND scope=?
               ORDER BY created_at,task_key LIMIT ?""",
            (graph_id, scope, limit),
        ).fetchall()
    finally:
        conn.close()
    return [
        item for row in rows
        if (item := get_task(scope, row["task_id"], include_payload=include_payload)) is not None
    ]
