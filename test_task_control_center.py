from cryptography.fernet import Fernet
import pytest

import db
import durable_task_engine as engine
import task_control_center as control


def _use_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "task-control-center.db"))
    monkeypatch.setenv(
        "ORACLE_CHECKPOINT_ENCRYPTION_KEY",
        Fernet.generate_key().decode("ascii"),
    )


def _create_graph(scope, key):
    return engine.create_graph(
        scope,
        key,
        [
            engine.TaskSpec(
                task_key="inspect",
                task_type="metadata.inspect",
                payload={
                    "private_payload": "DO-NOT-SHOW-THIS",
                    "path": "/private/location",
                },
            )
        ],
    )


def test_control_center_graph_projection_is_scope_isolated(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    own = _create_graph("owner:one", "own-graph")
    _create_graph("owner:two", "other-graph")

    rows = control.list_graph_summaries("owner:one")

    assert len(rows) == 1
    assert rows[0]["graph_id"] == own.graph_id
    assert rows[0]["status"] == "active"
    assert control.list_graph_summaries("owner:two")[0]["idempotency_key"] == "other-graph"


def test_control_center_task_projection_never_returns_payload_ciphertext_or_result(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    graph = _create_graph("owner:one", "safe-projection")
    lease = engine.claim_next("owner:one", "worker-a")
    assert lease is not None
    engine.start_task("owner:one", lease.task_id, lease.worker_id, lease.lease_token)
    engine.complete_task(
        "owner:one", lease.task_id, lease.worker_id, lease.lease_token,
        {"private_result": "DO-NOT-SHOW-RESULT"},
    )

    detail = control.get_graph_detail("owner:one", graph.graph_id)
    task = detail["tasks"][0]
    rendered = repr(detail)

    assert detail["graph"]["status"] == "completed"
    assert task["status"] == "succeeded"
    assert "payload" not in task
    assert "result" not in task
    assert "payload_ciphertext" not in rendered
    assert "result_ciphertext" not in rendered
    assert "DO-NOT-SHOW-THIS" not in rendered
    assert "DO-NOT-SHOW-RESULT" not in rendered
    assert "/private/location" not in rendered


def test_control_center_exposes_attempt_metadata_without_exception_text(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    graph = _create_graph("owner:one", "attempts")
    lease = engine.claim_next("owner:one", "worker-a")
    assert lease is not None
    engine.start_task("owner:one", lease.task_id, lease.worker_id, lease.lease_token)
    engine.fail_task(
        "owner:one", lease.task_id, lease.worker_id, lease.lease_token,
        error_code="TimeoutError", retryable=False,
    )

    attempts = control.list_task_attempts("owner:one", lease.task_id)

    assert len(attempts) == 1
    assert attempts[0]["status"] == "permanent_failure"
    assert attempts[0]["error_code"] == "TimeoutError"
    assert all("message" not in item for item in attempts)
    assert engine.get_graph("owner:one", graph.graph_id).status == "failed"


def test_control_center_can_pause_resume_and_cancel_graph(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    graph = _create_graph("owner:one", "graph-controls")

    paused = control.transition_graph("owner:one", graph.graph_id, "pause")
    assert paused["status"] == "paused"

    resumed = control.transition_graph("owner:one", graph.graph_id, "resume")
    assert resumed["status"] == "active"

    cancelled = control.transition_graph("owner:one", graph.graph_id, "cancel")
    assert cancelled["status"] == "cancelled"

    with pytest.raises(control.TaskControlCenterError, match="unsupported"):
        control.transition_graph("owner:one", graph.graph_id, "delete")

    with pytest.raises(control.TaskControlCenterError, match="no longer allows"):
        control.transition_graph("owner:one", graph.graph_id, "cancel")


def test_control_center_returns_none_for_graph_outside_scope_or_missing(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    graph = _create_graph("owner:one", "scope-bound")

    assert control.get_graph_detail("owner:two", graph.graph_id) is None
    assert control.get_graph_detail("owner:one", "0" * 32) is None



def test_memory_scan_result_summary_is_allowlisted_and_scope_bound(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    graph = engine.create_graph(
        "owner:one",
        "scan-result-summary",
        [
            engine.TaskSpec(
                task_key="scan",
                task_type="memory.consolidation.scan",
                payload={"candidate_limit": 10, "max_pair_checks": 20, "max_proposals": 5},
            )
        ],
    )
    lease = engine.claim_next("owner:one", "worker-a")
    assert lease is not None
    engine.start_task("owner:one", lease.task_id, lease.worker_id, lease.lease_token)
    engine.complete_task(
        "owner:one",
        lease.task_id,
        lease.worker_id,
        lease.lease_token,
        {
            "task_kind": "memory.consolidation.scan",
            "run_id": "a" * 32,
            "algorithm_version": "lexical-review-v1",
            "status": "partial",
            "scanned_count": 12,
            "comparison_count": 50,
            "proposal_count": 3,
            "truncated": True,
            "created_at": "2026-11-08T00:00:00+00:00",
            "finished_at": "2026-11-08T00:00:01+00:00",
            "payload": "must-not-leak",
            "secret": "must-not-leak",
        },
    )

    summary = control.get_task_result_summary("owner:one", lease.task_id)

    assert summary == {
        "run_id": "a" * 32,
        "algorithm_version": "lexical-review-v1",
        "status": "partial",
        "scanned_count": 12,
        "comparison_count": 50,
        "proposal_count": 3,
        "truncated": True,
        "created_at": "2026-11-08T00:00:00+00:00",
        "finished_at": "2026-11-08T00:00:01+00:00",
    }
    assert control.get_task_result_summary("owner:two", lease.task_id) is None
    assert "must-not-leak" not in repr(summary)


def test_result_summary_is_hidden_for_non_scan_task_and_invalid_shape(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    graph = engine.create_graph(
        "owner:one",
        "non-scan-result",
        [
            engine.TaskSpec(
                task_key="other",
                task_type="other.task",
                payload={},
            )
        ],
    )
    lease = engine.claim_next("owner:one", "worker-a")
    engine.start_task("owner:one", lease.task_id, lease.worker_id, lease.lease_token)
    engine.complete_task(
        "owner:one", lease.task_id, lease.worker_id, lease.lease_token,
        {"task_kind": "memory.consolidation.scan", "run_id": "a" * 32},
    )
    assert control.get_task_result_summary("owner:one", lease.task_id) is None
