"""Safe metadata projections and graph controls for the Oracle Control Center.

No payloads/results are returned and no task/worker execution is started here.
"""

from __future__ import annotations

from typing import Any

import durable_task_engine as task_engine


class TaskControlCenterError(ValueError):
    """Invalid or unavailable task-graph control request."""


def _graph_summary(graph: task_engine.TaskGraph) -> dict[str, Any]:
    return {
        "graph_id": graph.graph_id,
        "idempotency_key": graph.idempotency_key,
        "status": graph.status,
        "task_count": graph.task_count,
        "succeeded_count": graph.succeeded_count,
        "failed_count": graph.failed_count,
        "blocked_count": graph.blocked_count,
        "pending_count": graph.pending_count,
        "created_at": graph.created_at,
        "updated_at": graph.updated_at,
        "finished_at": graph.finished_at,
    }


def _task_summary(task: dict[str, Any]) -> dict[str, Any]:
    """Project only UI-safe task metadata; never include payload or result data."""
    allowed = (
        "task_id",
        "task_key",
        "task_type",
        "status",
        "attempt_count",
        "max_attempts",
        "retry_safe",
        "available_at",
        "lease_owner",
        "lease_expires_at",
        "last_error_code",
        "created_at",
        "updated_at",
        "result_digest",
    )
    return {key: task.get(key) for key in allowed}


def list_graph_summaries(scope: str, *, limit: int = 50) -> list[dict[str, Any]]:
    return [_graph_summary(item) for item in task_engine.list_graphs(scope, limit=limit)]


def get_graph_detail(scope: str, graph_id: str) -> dict[str, Any] | None:
    graph = task_engine.get_graph(scope, graph_id)
    if graph is None:
        return None
    tasks = task_engine.list_tasks(
        scope,
        graph_id,
        limit=task_engine.MAX_GRAPH_TASKS,
        include_payload=False,
    )
    return {
        "graph": _graph_summary(graph),
        "tasks": [_task_summary(item) for item in tasks],
    }


def list_task_attempts(scope: str, task_id: str, *, limit: int = task_engine.MAX_ATTEMPTS) -> list[dict[str, Any]]:
    return task_engine.list_attempts(scope, task_id, limit=limit)


def transition_graph(scope: str, graph_id: str, action: str) -> dict[str, Any]:
    """Apply one explicit queue-control transition; never start a worker."""
    operations = {
        "pause": task_engine.pause_graph,
        "resume": task_engine.resume_graph,
        "cancel": task_engine.cancel_graph,
    }
    operation = operations.get(action)
    if operation is None:
        raise TaskControlCenterError("unsupported graph action")
    changed = operation(scope, graph_id)
    if not changed:
        raise TaskControlCenterError("graph is missing or no longer allows this action")
    updated = task_engine.get_graph(scope, graph_id)
    if updated is None:
        raise TaskControlCenterError("graph became unavailable after the action")
    return _graph_summary(updated)
