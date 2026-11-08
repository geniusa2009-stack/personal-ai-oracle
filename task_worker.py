"""Explicit one-task worker adapter for the durable DAG queue.

A dispatcher runs only handlers supplied by its caller. It has no shell,
browser, filesystem, model-provider or generic tool-executor fallback.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

import durable_task_engine as task_engine


class TaskWorkerError(ValueError):
    """Invalid handler registry or worker invocation."""


TaskHandlerFunction = Callable[
    [Mapping[str, Any], "TaskExecutionContext"],
    Mapping[str, Any],
]


@dataclass(frozen=True)
class TaskHandler:
    """Explicit handler for one task type."""

    execute: TaskHandlerFunction
    retryable_exceptions: tuple[type[Exception], ...] = ()
    retry_delay_seconds: int = 2

    def __post_init__(self) -> None:
        if not callable(self.execute):
            raise TaskWorkerError("task handler execute must be callable")
        if not isinstance(self.retryable_exceptions, tuple):
            raise TaskWorkerError("retryable_exceptions must be a tuple")
        if any(
            not isinstance(item, type) or not issubclass(item, Exception)
            for item in self.retryable_exceptions
        ):
            raise TaskWorkerError("retryable_exceptions must contain Exception subclasses")
        if (
            isinstance(self.retry_delay_seconds, bool)
            or not isinstance(self.retry_delay_seconds, int)
            or not 0 <= self.retry_delay_seconds <= task_engine.MAX_RETRY_DELAY_SECONDS
        ):
            raise TaskWorkerError("retry_delay_seconds is outside the supported range")


@dataclass(frozen=True)
class TaskExecutionContext:
    scope: str
    graph_id: str
    task_id: str
    task_key: str
    task_type: str
    worker_id: str
    attempt_number: int
    _heartbeat_callback: Callable[[], bool] = field(repr=False, compare=False)

    def heartbeat(self) -> bool:
        """Extend the active lease without exposing its secret token to the handler."""
        return self._heartbeat_callback()

    def cancellation_requested(self) -> bool:
        """Poll durable state so handlers can stop cooperatively."""
        item = task_engine.get_task(self.scope, self.task_id)
        if item is None or item["status"] == "cancelled":
            return True
        graph = task_engine.get_graph(self.scope, self.graph_id)
        return graph is None or graph.status == "cancelled"


@dataclass(frozen=True)
class TaskDispatchResult:
    task_id: str
    task_key: str
    task_type: str
    status: str
    attempt_number: int
    error_code: str = ""


def _normalize_handlers(
    handlers: Mapping[str, TaskHandler],
) -> dict[str, TaskHandler]:
    if not isinstance(handlers, Mapping):
        raise TaskWorkerError("handlers must be an explicit mapping")
    normalized: dict[str, TaskHandler] = {}
    for raw_type, handler in handlers.items():
        if (
            not isinstance(raw_type, str)
            or not raw_type.strip()
            or len(raw_type.strip()) > 80
            or not re.fullmatch(r"[A-Za-z0-9_.-]+", raw_type.strip())
        ):
            raise TaskWorkerError("handler task type contains unsupported characters")
        task_type = raw_type.strip()
        if task_type in normalized:
            raise TaskWorkerError("duplicate normalized handler task type")
        if not isinstance(handler, TaskHandler):
            raise TaskWorkerError(f"handler for {task_type} must be a TaskHandler")
        normalized[task_type] = handler
    return normalized


def _error_code(exc: Exception) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]", "_", type(exc).__name__)[:80]
    return value or "WorkerError"


def dispatch_once(
    scope: str,
    worker_id: str,
    handlers: Mapping[str, TaskHandler],
    *,
    lease_seconds: int = 120,
) -> TaskDispatchResult | None:
    """Claim and process at most one task of an explicitly registered type.

    Unknown task types remain queued. The handler must return a JSON-safe
    mapping. Retry requires both a configured retryable exception class and
    the task's explicit retry_safe declaration.
    """
    registry = _normalize_handlers(handlers)
    if not registry:
        return None

    lease = task_engine.claim_next(
        scope,
        worker_id,
        lease_seconds=lease_seconds,
        task_types=tuple(registry),
    )
    if lease is None:
        return None

    def result(status: str, error_code: str = "") -> TaskDispatchResult:
        return TaskDispatchResult(
            task_id=lease.task_id,
            task_key=lease.task_key,
            task_type=lease.task_type,
            status=status,
            attempt_number=lease.attempt_number,
            error_code=error_code,
        )

    try:
        task_engine.start_task(scope, lease.task_id, worker_id, lease.lease_token)
    except task_engine.TaskEngineError:
        current = task_engine.get_task(scope, lease.task_id)
        status = current["status"] if current is not None else "lease_lost"
        return result(
            status if status in {"queued", "cancelled", "failed", "blocked"} else "lease_lost"
        )

    context = TaskExecutionContext(
        scope=scope,
        graph_id=lease.graph_id,
        task_id=lease.task_id,
        task_key=lease.task_key,
        task_type=lease.task_type,
        worker_id=worker_id,
        attempt_number=lease.attempt_number,
        _heartbeat_callback=lambda: task_engine.heartbeat(
            scope,
            lease.task_id,
            worker_id,
            lease.lease_token,
            lease_seconds=lease_seconds,
        ),
    )
    handler = registry[lease.task_type]
    try:
        output = handler.execute(lease.payload, context)
        if not isinstance(output, Mapping):
            raise TaskWorkerError("task handler must return a mapping")
        current = task_engine.get_task(scope, lease.task_id)
        if current is None or current["status"] == "cancelled":
            return result("cancelled")
        task_engine.complete_task(
            scope,
            lease.task_id,
            worker_id,
            lease.lease_token,
            dict(output),
        )
        return result("succeeded")
    except Exception as exc:
        code = _error_code(exc)
        retryable = bool(handler.retryable_exceptions) and isinstance(
            exc, handler.retryable_exceptions
        )
        try:
            updated = task_engine.fail_task(
                scope,
                lease.task_id,
                worker_id,
                lease.lease_token,
                error_code=code,
                retryable=retryable,
                retry_delay_seconds=handler.retry_delay_seconds,
            )
            return result(updated["status"], code)
        except task_engine.TaskEngineError:
            current = task_engine.get_task(scope, lease.task_id)
            status = current["status"] if current is not None else "lease_lost"
            if status in {"cancelled", "failed", "queued", "blocked"}:
                return result(status, code)
            return result("lease_lost", code)



def dispatch_batch(
    scope: str,
    worker_id: str,
    handlers: Mapping[str, TaskHandler],
    *,
    max_tasks: int = 10,
    lease_seconds: int = 120,
) -> list[TaskDispatchResult]:
    """Process at most max_tasks ready jobs; never sleeps or runs indefinitely."""
    if (
        isinstance(max_tasks, bool)
        or not isinstance(max_tasks, int)
        or not 1 <= max_tasks <= 100
    ):
        raise TaskWorkerError("max_tasks must be between 1 and 100")
    registry = _normalize_handlers(handlers)
    if not registry:
        return []
    results = []
    for _ in range(max_tasks):
        result = dispatch_once(
            scope,
            worker_id,
            registry,
            lease_seconds=lease_seconds,
        )
        if result is None:
            break
        results.append(result)
    return results
