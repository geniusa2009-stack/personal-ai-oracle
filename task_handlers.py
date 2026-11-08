"""Reviewed, local-only task handlers available to the Control Center.

Only the memory-consolidation discovery task is registered here. It creates
review proposals and never edits, merges, supersedes or deletes source memories.
"""

from __future__ import annotations

from typing import Any, Mapping

import durable_task_engine
import memory_consolidation
from task_worker import TaskExecutionContext, TaskHandler


MEMORY_SCAN_TASK_TYPE = "memory.consolidation.scan"
MEMORY_SCAN_TASK_KEY = "scan"
DEFAULT_CANDIDATE_LIMIT = 200
DEFAULT_MAX_PAIR_CHECKS = 20000
DEFAULT_MAX_PROPOSALS = 500


class MemoryScanHandlerError(ValueError):
    """Invalid payload for the local memory consolidation scan handler."""


def _bounded_int(value: Any, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise MemoryScanHandlerError(f"{field} must be between {minimum} and {maximum}")
    return value


def _scan_config(
    *,
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
    max_pair_checks: int = DEFAULT_MAX_PAIR_CHECKS,
    max_proposals: int = DEFAULT_MAX_PROPOSALS,
) -> dict[str, int]:
    return {
        "candidate_limit": _bounded_int(candidate_limit, "candidate_limit", 2, 500),
        "max_pair_checks": _bounded_int(max_pair_checks, "max_pair_checks", 1, 50000),
        "max_proposals": _bounded_int(max_proposals, "max_proposals", 1, 1000),
    }


def create_memory_consolidation_scan(
    scope: str,
    idempotency_key: str,
    *,
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
    max_pair_checks: int = DEFAULT_MAX_PAIR_CHECKS,
    max_proposals: int = DEFAULT_MAX_PROPOSALS,
) -> durable_task_engine.TaskGraph:
    """Queue one bounded, non-destructive memory scan in the supplied scope."""
    config = _scan_config(
        candidate_limit=candidate_limit,
        max_pair_checks=max_pair_checks,
        max_proposals=max_proposals,
    )
    return durable_task_engine.create_graph(
        scope,
        idempotency_key,
        [
            durable_task_engine.TaskSpec(
                task_key=MEMORY_SCAN_TASK_KEY,
                task_type=MEMORY_SCAN_TASK_TYPE,
                payload=config,
                max_attempts=1,
                retry_safe=False,
            )
        ],
    )


def _run_memory_scan(
    payload: Mapping[str, Any],
    context: TaskExecutionContext,
) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise MemoryScanHandlerError("scan payload must be a mapping")
    expected = {"candidate_limit", "max_pair_checks", "max_proposals"}
    if set(payload) != expected:
        raise MemoryScanHandlerError("scan payload has unsupported fields")
    config = _scan_config(
        candidate_limit=payload["candidate_limit"],
        max_pair_checks=payload["max_pair_checks"],
        max_proposals=payload["max_proposals"],
    )
    if context.cancellation_requested():
        return {"cancelled": True}

    run = memory_consolidation.scan_scope(context.scope, **config)

    if context.cancellation_requested():
        return {"cancelled": True}

    return {
        "task_kind": MEMORY_SCAN_TASK_TYPE,
        "run_id": run.run_id,
        "algorithm_version": run.algorithm_version,
        "status": run.status,
        "scanned_count": run.scanned_count,
        "comparison_count": run.comparison_count,
        "proposal_count": run.proposal_count,
        "truncated": run.truncated,
        "created_at": run.created_at,
        "finished_at": run.finished_at,
    }


def build_default_handlers() -> dict[str, TaskHandler]:
    """Return the deliberately small reviewed handler registry."""
    return {
        MEMORY_SCAN_TASK_TYPE: TaskHandler(
            execute=_run_memory_scan,
            retryable_exceptions=(),
            retry_delay_seconds=0,
        )
    }
