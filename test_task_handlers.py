from dataclasses import dataclass
from types import SimpleNamespace

from cryptography.fernet import Fernet
import pytest

import db
import durable_task_engine
import memory
import memory_consolidation
import task_control_center
import task_handlers
import task_worker


def _use_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "memory-scan-worker.db"))
    monkeypatch.setenv(
        "ORACLE_CHECKPOINT_ENCRYPTION_KEY",
        Fernet.generate_key().decode("ascii"),
    )


def test_create_memory_scan_graph_has_bounded_payload_and_no_retry(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)

    graph = task_handlers.create_memory_consolidation_scan(
        "owner:one",
        "scan-once",
        candidate_limit=42,
        max_pair_checks=321,
        max_proposals=17,
    )

    tasks = durable_task_engine.list_tasks("owner:one", graph.graph_id, include_payload=True)
    assert len(tasks) == 1
    assert tasks[0]["task_type"] == task_handlers.MEMORY_SCAN_TASK_TYPE
    assert tasks[0]["payload"] == {
        "candidate_limit": 42,
        "max_pair_checks": 321,
        "max_proposals": 17,
    }
    assert tasks[0]["retry_safe"] is False
    assert tasks[0]["max_attempts"] == 1

    repeated = task_handlers.create_memory_consolidation_scan(
        "owner:one",
        "scan-once",
        candidate_limit=42,
        max_pair_checks=321,
        max_proposals=17,
    )
    assert repeated.graph_id == graph.graph_id


@pytest.mark.parametrize(
    "kwargs",
    [
        {"candidate_limit": True},
        {"candidate_limit": 1},
        {"candidate_limit": 501},
        {"max_pair_checks": 50001},
        {"max_proposals": 0},
    ],
)
def test_scan_config_rejects_bool_and_out_of_range_values(kwargs):
    with pytest.raises(task_handlers.MemoryScanHandlerError):
        task_handlers.create_memory_consolidation_scan(
            "owner:one",
            "invalid-config",
            **kwargs,
        )


def test_memory_scan_handler_uses_context_scope_and_fixed_payload(monkeypatch):
    calls = []
    fake_run = SimpleNamespace(
        run_id="a" * 32,
        algorithm_version="lexical-review-v1",
        status="partial",
        scanned_count=10,
        comparison_count=20,
        proposal_count=2,
        truncated=True,
        created_at="2026-11-08T00:00:00+00:00",
        finished_at="2026-11-08T00:00:01+00:00",
    )

    def fake_scan(scope, **kwargs):
        calls.append((scope, kwargs))
        return fake_run

    monkeypatch.setattr(memory_consolidation, "scan_scope", fake_scan)
    context = SimpleNamespace(scope="owner:trusted", cancellation_requested=lambda: False)
    handler = task_handlers.build_default_handlers()[task_handlers.MEMORY_SCAN_TASK_TYPE]

    result = handler.execute(
        {
            "candidate_limit": 40,
            "max_pair_checks": 400,
            "max_proposals": 8,
        },
        context,
    )

    assert calls == [(
        "owner:trusted",
        {"candidate_limit": 40, "max_pair_checks": 400, "max_proposals": 8},
    )]
    assert result["run_id"] == "a" * 32
    assert result["proposal_count"] == 2
    assert result["truncated"] is True
    assert "scope" not in result


def test_memory_scan_handler_rejects_unrecognized_payload_fields(monkeypatch):
    handler = task_handlers.build_default_handlers()[task_handlers.MEMORY_SCAN_TASK_TYPE]
    context = SimpleNamespace(scope="owner:one", cancellation_requested=lambda: False)

    with pytest.raises(task_handlers.MemoryScanHandlerError, match="unsupported fields"):
        handler.execute(
            {
                "candidate_limit": 10,
                "max_pair_checks": 10,
                "max_proposals": 10,
                "delete_after_scan": True,
            },
            context,
        )


def test_cancelled_context_does_not_start_memory_scan(monkeypatch):
    calls = []
    monkeypatch.setattr(
        memory_consolidation,
        "scan_scope",
        lambda *args, **kwargs: calls.append(True),
    )
    handler = task_handlers.build_default_handlers()[task_handlers.MEMORY_SCAN_TASK_TYPE]
    context = SimpleNamespace(scope="owner:one", cancellation_requested=lambda: True)

    result = handler.execute(
        {
            "candidate_limit": 10,
            "max_pair_checks": 10,
            "max_proposals": 10,
        },
        context,
    )

    assert result == {"cancelled": True}
    assert calls == []


def test_default_handler_dispatch_runs_real_non_destructive_memory_scan(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    memory.write_memory(
        "Oracle memory uses SQLite for durable project context",
        "fact",
        "owner:one",
        "manual",
    )
    memory.write_memory(
        "Oracle memory stores durable project context in SQLite",
        "fact",
        "owner:one",
        "manual",
    )
    original_records = memory.list_memories("owner:one")

    graph = task_handlers.create_memory_consolidation_scan(
        "owner:one",
        "integration-scan",
        candidate_limit=50,
        max_pair_checks=500,
        max_proposals=20,
    )
    dispatch = task_worker.dispatch_once(
        "owner:one",
        "control-center-manual-worker",
        task_handlers.build_default_handlers(),
        lease_seconds=300,
    )

    assert dispatch is not None
    assert dispatch.status == "succeeded"
    assert dispatch.task_type == task_handlers.MEMORY_SCAN_TASK_TYPE
    task = durable_task_engine.get_task(
        "owner:one", dispatch.task_id, include_result=True
    )
    assert task["status"] == "succeeded"
    assert task["retry_safe"] is False
    assert task["attempt_count"] == 1
    assert task["result"]["task_kind"] == task_handlers.MEMORY_SCAN_TASK_TYPE
    assert isinstance(task["result"]["run_id"], str)
    assert memory.list_memories("owner:one") == original_records

    summary = task_control_center.get_task_result_summary("owner:one", dispatch.task_id)
    assert summary is not None
    assert summary["run_id"] == task["result"]["run_id"]
    assert "payload" not in summary
    assert "result" not in summary


def test_default_handler_registry_contains_only_reviewed_scan_type():
    handlers = task_handlers.build_default_handlers()
    assert tuple(handlers) == (task_handlers.MEMORY_SCAN_TASK_TYPE,)
    assert handlers[task_handlers.MEMORY_SCAN_TASK_TYPE].retryable_exceptions == ()
