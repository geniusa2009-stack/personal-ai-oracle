"""Scope-isolated durable DAG queue; this module schedules but never runs tools."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
import uuid
from dataclasses import dataclass, field
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
    payload: Mapping[str, Any] = field(repr=False)
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
    payload: dict[str, Any] = field(repr=False)
    worker_id: str
    lease_token: str = field(repr=False)
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



def _worker_id(value: Any) -> str:
    return _label(value, "worker_id", 100, _WORKER)


def _lease_seconds(value: Any) -> int:
    return _int(value, "lease_seconds", MIN_LEASE_SECONDS, MAX_LEASE_SECONDS)


def _valid_lease(conn: Any, scope: str, task_id: str, worker_id: str, token: str) -> Any:
    worker_id = _worker_id(worker_id)
    if not isinstance(token, str) or not 32 <= len(token) <= 256:
        raise TaskEngineError("lease_token is invalid")
    row = conn.execute(
        """SELECT task_id,graph_id,status,lease_expires_at,lease_token_digest,
                  lease_owner,attempt_count,retry_safe,max_attempts
           FROM oracle_durable_tasks WHERE task_id=? AND scope=?""",
        (task_id, scope),
    ).fetchone()
    if row is None:
        raise TaskEngineError("task was not found in this scope")
    if (
        row["status"] not in {"leased", "running"}
        or row["lease_owner"] != worker_id
        or not row["lease_token_digest"]
        or not secrets.compare_digest(row["lease_token_digest"], _token_hash(token))
        or row["lease_expires_at"] is None
        or float(row["lease_expires_at"]) <= time.time()
    ):
        raise TaskEngineError("task lease is invalid, expired or no longer owned by this worker")
    graph = conn.execute(
        "SELECT status FROM oracle_task_graphs WHERE graph_id=? AND scope=?",
        (row["graph_id"], scope),
    ).fetchone()
    if graph is None or graph["status"] == "cancelled":
        raise TaskEngineError("task graph is no longer active")
    return row


def _reap_graph_expired(conn: Any, scope: str, graph_id: str) -> int:
    now = time.time()
    rows = conn.execute(
        """SELECT task_id,attempt_count,max_attempts,retry_safe
           FROM oracle_durable_tasks
           WHERE scope=? AND graph_id=? AND status IN ('leased','running')
             AND lease_expires_at IS NOT NULL AND lease_expires_at<=?""",
        (scope, graph_id, now),
    ).fetchall()
    count = 0
    for row in rows:
        task_id = row["task_id"]
        attempt = int(row["attempt_count"])
        conn.execute(
            """UPDATE oracle_task_attempts SET status='lease_expired',finished_at=?
               WHERE task_id=? AND scope=? AND attempt_number=?
                 AND status IN ('leased','running')""",
            (_now_iso(), task_id, scope, attempt),
        )
        retry = bool(row["retry_safe"]) and attempt < int(row["max_attempts"])
        conn.execute(
            """UPDATE oracle_durable_tasks SET status=?,available_at=?,last_error_code=?,
               lease_owner='',lease_token_digest='',lease_expires_at=NULL,updated_at=?
               WHERE task_id=? AND scope=?""",
            (
                "queued" if retry else "failed", now, "lease_expired",
                _now_iso(), task_id, scope,
            ),
        )
        count += 1
    _propagate_blocked(conn, scope, graph_id)
    _refresh_graph(conn, scope, graph_id)
    return count


def claim_next(
    scope: str,
    worker_id: str,
    *,
    lease_seconds: int = 120,
) -> TaskLease | None:
    """Atomically lease one ready task. The queue never executes the task itself."""
    scope = _scope(scope)
    worker_id = _worker_id(worker_id)
    lease_seconds = _lease_seconds(lease_seconds)
    now = time.time()
    init_database()
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        graphs = conn.execute(
            """SELECT graph_id FROM oracle_task_graphs
               WHERE scope=? AND status IN ('active','paused')""",
            (scope,),
        ).fetchall()
        for graph in graphs:
            _reap_graph_expired(conn, scope, graph["graph_id"])
        task = conn.execute(
            """SELECT task.* FROM oracle_durable_tasks AS task
               JOIN oracle_task_graphs AS graph
                 ON graph.graph_id=task.graph_id AND graph.scope=task.scope
               WHERE task.scope=? AND task.status='queued' AND task.available_at<=?
                 AND task.attempt_count<task.max_attempts AND graph.status='active'
                 AND NOT EXISTS (
                   SELECT 1 FROM oracle_task_dependencies AS dep
                   JOIN oracle_durable_tasks AS parent
                     ON parent.task_id=dep.depends_on_task_id AND parent.scope=dep.scope
                   WHERE dep.task_id=task.task_id AND dep.scope=task.scope
                     AND parent.status<>'succeeded'
                 )
               ORDER BY task.created_at,task.task_key LIMIT 1""",
            (scope, now),
        ).fetchone()
        if task is None:
            for graph in graphs:
                _refresh_graph(conn, scope, graph["graph_id"])
            conn.commit()
            return None
        token = secrets.token_urlsafe(32)
        attempt = int(task["attempt_count"]) + 1
        expires = now + lease_seconds
        now_iso = _now_iso()
        cur = conn.execute(
            """UPDATE oracle_durable_tasks SET status='leased',attempt_count=?,
               lease_owner=?,lease_token_digest=?,lease_expires_at=?,updated_at=?
               WHERE task_id=? AND scope=? AND status='queued'""",
            (attempt, worker_id, _token_hash(token), expires, now_iso, task["task_id"], scope),
        )
        if cur.rowcount != 1:
            raise TaskEngineError("task lease could not be acquired")
        conn.execute(
            """INSERT INTO oracle_task_attempts
               (task_id,scope,attempt_number,worker_id,status,started_at)
               VALUES(?,?,?,?,'leased',?)""",
            (task["task_id"], scope, attempt, worker_id, now_iso),
        )
        payload = workflow_checkpoints.decrypt_scoped_payload(
            scope, task["payload_ciphertext"]
        )
        if not isinstance(payload, dict):
            raise TaskEngineError("stored task payload is not an object")
        conn.execute(
            "UPDATE oracle_task_graphs SET updated_at=? WHERE graph_id=? AND scope=?",
            (now_iso, task["graph_id"], scope),
        )
        conn.commit()
        return TaskLease(
            task_id=task["task_id"], graph_id=task["graph_id"], scope=scope,
            task_key=task["task_key"], task_type=task["task_type"], payload=payload,
            worker_id=worker_id, lease_token=token, attempt_number=attempt,
            max_attempts=int(task["max_attempts"]), retry_safe=bool(task["retry_safe"]),
            lease_expires_at=expires,
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def start_task(scope: str, task_id: str, worker_id: str, lease_token: str) -> bool:
    """Mark a claimed task running before the worker begins its external work."""
    scope = _scope(scope)
    task_id = _id(task_id, "task_id")
    init_database()
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = _valid_lease(conn, scope, task_id, worker_id, lease_token)
        if row["status"] != "leased":
            raise TaskEngineError("only a leased task can transition to running")
        now = _now_iso()
        cur = conn.execute(
            """UPDATE oracle_durable_tasks SET status='running',updated_at=?
               WHERE task_id=? AND scope=? AND status='leased'""",
            (now, task_id, scope),
        )
        if cur.rowcount != 1:
            raise TaskEngineError("task could not transition to running")
        conn.execute(
            """UPDATE oracle_task_attempts SET status='running'
               WHERE task_id=? AND scope=? AND attempt_number=? AND status='leased'""",
            (task_id, scope, row["attempt_count"]),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def heartbeat(
    scope: str,
    task_id: str,
    worker_id: str,
    lease_token: str,
    *,
    lease_seconds: int = 120,
) -> bool:
    """Extend a live lease only for its current owner and secret token."""
    scope = _scope(scope)
    task_id = _id(task_id, "task_id")
    lease_seconds = _lease_seconds(lease_seconds)
    init_database()
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        _valid_lease(conn, scope, task_id, worker_id, lease_token)
        now = time.time()
        cur = conn.execute(
            """UPDATE oracle_durable_tasks SET lease_expires_at=?,updated_at=?
               WHERE task_id=? AND scope=? AND lease_owner=? AND lease_token_digest=?
                 AND status IN ('leased','running') AND lease_expires_at>?""",
            (
                now + lease_seconds, _now_iso(), task_id, scope, worker_id,
                _token_hash(lease_token), now,
            ),
        )
        conn.commit()
        return cur.rowcount == 1
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def complete_task(
    scope: str,
    task_id: str,
    worker_id: str,
    lease_token: str,
    result: Mapping[str, Any],
) -> bool:
    """Persist an encrypted task result and finish its current attempt."""
    scope = _scope(scope)
    task_id = _id(task_id, "task_id")
    if not isinstance(result, Mapping):
        raise TaskEngineError("result must be a mapping")
    value = dict(result)
    digest, length = _digest(value)
    if length > workflow_checkpoints.MAX_CHECKPOINT_BYTES:
        raise TaskEngineError("task result exceeds the encrypted payload limit")
    encrypted = workflow_checkpoints.encrypt_scoped_payload(scope, value)
    init_database()
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = _valid_lease(conn, scope, task_id, worker_id, lease_token)
        if row["status"] != "running":
            raise TaskEngineError("only a running task can be completed")
        now = _now_iso()
        cur = conn.execute(
            """UPDATE oracle_durable_tasks SET status='succeeded',result_ciphertext=?,
               result_digest=?,lease_owner='',lease_token_digest='',lease_expires_at=NULL,
               updated_at=? WHERE task_id=? AND scope=? AND status='running'""",
            (encrypted, digest, now, task_id, scope),
        )
        if cur.rowcount != 1:
            raise TaskEngineError("task could not transition to succeeded")
        conn.execute(
            """UPDATE oracle_task_attempts SET status='succeeded',result_digest=?,
               result_length=?,finished_at=?,
               duration_ms=MAX(0,CAST((julianday(?) - julianday(started_at))*86400000 AS INTEGER))
               WHERE task_id=? AND scope=? AND attempt_number=? AND status='running'""",
            (digest, length, now, now, task_id, scope, row["attempt_count"]),
        )
        _propagate_blocked(conn, scope, row["graph_id"])
        _refresh_graph(conn, scope, row["graph_id"])
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def fail_task(
    scope: str,
    task_id: str,
    worker_id: str,
    lease_token: str,
    *,
    error_code: str,
    retryable: bool = False,
    retry_delay_seconds: int = 2,
) -> dict[str, Any]:
    """Record failure; retry is permitted only for explicitly retry-safe tasks."""
    scope = _scope(scope)
    task_id = _id(task_id, "task_id")
    if not isinstance(retryable, bool):
        raise TaskEngineError("retryable must be a boolean")
    retry_delay_seconds = _int(
        retry_delay_seconds, "retry_delay_seconds", 0, MAX_RETRY_DELAY_SECONDS
    )
    safe_error = _label(error_code, "error_code", 80, _TYPE)
    init_database()
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = _valid_lease(conn, scope, task_id, worker_id, lease_token)
        attempt = int(row["attempt_count"])
        can_retry = retryable and bool(row["retry_safe"]) and attempt < int(row["max_attempts"])
        status = "queued" if can_retry else "failed"
        delay = min(retry_delay_seconds * (2 ** max(0, attempt - 1)), MAX_RETRY_DELAY_SECONDS)
        now = _now_iso()
        conn.execute(
            """UPDATE oracle_task_attempts SET status=?,error_code=?,finished_at=?,
               duration_ms=MAX(0,CAST((julianday(?) - julianday(started_at))*86400000 AS INTEGER))
               WHERE task_id=? AND scope=? AND attempt_number=?
                 AND status IN ('leased','running')""",
            (
                "retryable_failure" if can_retry else "permanent_failure",
                safe_error, now, now, task_id, scope, attempt,
            ),
        )
        conn.execute(
            """UPDATE oracle_durable_tasks SET status=?,available_at=?,last_error_code=?,
               lease_owner='',lease_token_digest='',lease_expires_at=NULL,updated_at=?
               WHERE task_id=? AND scope=?""",
            (status, time.time() + (delay if can_retry else 0), safe_error, now, task_id, scope),
        )
        _propagate_blocked(conn, scope, row["graph_id"])
        _refresh_graph(conn, scope, row["graph_id"])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    task = get_task(scope, task_id)
    if task is None:
        raise TaskEngineError("task was not found after failure transition")
    return task


def reap_expired_leases(scope: str) -> int:
    """Requeue only retry-safe expired work; all other expired work fails closed."""
    scope = _scope(scope)
    init_database()
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        graphs = conn.execute(
            """SELECT graph_id FROM oracle_task_graphs WHERE scope=?
               AND status IN ('active','paused')""",
            (scope,),
        ).fetchall()
        count = 0
        for graph in graphs:
            count += _reap_graph_expired(conn, scope, graph["graph_id"])
        conn.commit()
        return count
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def pause_graph(scope: str, graph_id: str) -> bool:
    scope = _scope(scope)
    graph_id = _id(graph_id, "graph_id")
    init_database()
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        now = _now_iso()
        cur = conn.execute(
            """UPDATE oracle_task_graphs SET status='paused',updated_at=?
               WHERE graph_id=? AND scope=? AND status='active'""",
            (now, graph_id, scope),
        )
        if cur.rowcount:
            # A lease not yet started is safe to release; already-running work
            # remains leased so its worker can finish/heartbeat cooperatively.
            leased = conn.execute(
                """SELECT task_id,attempt_count FROM oracle_durable_tasks
                   WHERE graph_id=? AND scope=? AND status='leased'""",
                (graph_id, scope),
            ).fetchall()
            for item in leased:
                conn.execute(
                    """UPDATE oracle_task_attempts SET status='cancelled',finished_at=?
                       WHERE task_id=? AND scope=? AND attempt_number=? AND status='leased'""",
                    (now, item["task_id"], scope, item["attempt_count"]),
                )
            conn.execute(
                """UPDATE oracle_durable_tasks SET status='queued',lease_owner='',
                   lease_token_digest='',lease_expires_at=NULL,updated_at=?
                   WHERE graph_id=? AND scope=? AND status='leased'""",
                (now, graph_id, scope),
            )
        conn.commit()
        return cur.rowcount == 1
    finally:
        conn.close()


def resume_graph(scope: str, graph_id: str) -> bool:
    scope = _scope(scope)
    graph_id = _id(graph_id, "graph_id")
    init_database()
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            """UPDATE oracle_task_graphs SET status='active',updated_at=?
               WHERE graph_id=? AND scope=? AND status='paused'""",
            (_now_iso(), graph_id, scope),
        )
        if cur.rowcount:
            _propagate_blocked(conn, scope, graph_id)
            _refresh_graph(conn, scope, graph_id)
        conn.commit()
        return cur.rowcount == 1
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def cancel_graph(scope: str, graph_id: str) -> bool:
    """Cancel queued and leased tasks; running external effects stop cooperatively."""
    scope = _scope(scope)
    graph_id = _id(graph_id, "graph_id")
    init_database()
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        graph = conn.execute(
            "SELECT status FROM oracle_task_graphs WHERE graph_id=? AND scope=?",
            (graph_id, scope),
        ).fetchone()
        if graph is None or graph["status"] not in {"active", "paused"}:
            conn.rollback()
            return False
        now = _now_iso()
        conn.execute(
            """UPDATE oracle_durable_tasks SET status='cancelled',lease_owner='',
               lease_token_digest='',lease_expires_at=NULL,updated_at=?
               WHERE graph_id=? AND scope=?
                 AND status IN ('queued','leased','running','blocked')""",
            (now, graph_id, scope),
        )
        conn.execute(
            """UPDATE oracle_task_attempts SET status='cancelled',finished_at=?
               WHERE scope=? AND task_id IN (
                 SELECT task_id FROM oracle_durable_tasks WHERE graph_id=? AND scope=?
               ) AND status IN ('leased','running')""",
            (now, scope, graph_id, scope),
        )
        cur = conn.execute(
            """UPDATE oracle_task_graphs SET status='cancelled',updated_at=?,finished_at=?
               WHERE graph_id=? AND scope=? AND status IN ('active','paused')""",
            (now, now, graph_id, scope),
        )
        conn.commit()
        return cur.rowcount == 1
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_attempts(scope: str, task_id: str, *, limit: int = MAX_ATTEMPTS) -> list[dict[str, Any]]:
    scope = _scope(scope)
    task_id = _id(task_id, "task_id")
    limit = _int(limit, "limit", 1, MAX_ATTEMPTS)
    init_database()
    conn = get_conn()
    try:
        owned = conn.execute(
            "SELECT 1 FROM oracle_durable_tasks WHERE task_id=? AND scope=?",
            (task_id, scope),
        ).fetchone()
        if owned is None:
            return []
        rows = conn.execute(
            """SELECT attempt_number,worker_id,status,error_code,result_digest,
                      result_length,started_at,finished_at,duration_ms
               FROM oracle_task_attempts WHERE task_id=? AND scope=?
               ORDER BY attempt_number DESC LIMIT ?""",
            (task_id, scope, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
