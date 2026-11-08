from cryptography.fernet import Fernet
import pytest

import db
import durable_task_engine as engine
import task_worker


def _use_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "task-worker.db"))
    monkeypatch.setenv(
        "ORACLE_CHECKPOINT_ENCRYPTION_KEY",
        Fernet.generate_key().decode("ascii"),
    )


def _spec(key, task_type="text.transform", *, retry_safe=False, max_attempts=1):
    return engine.TaskSpec(
        task_key=key,
        task_type=task_type,
        payload={"input": f"payload-{key}", "private": "must-not-be-logged"},
        max_attempts=max_attempts,
        retry_safe=retry_safe,
    )


def test_dispatch_executes_exactly_one_registered_task_and_persists_result(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    graph = engine.create_graph(
        "owner:one",
        "worker-one-task",
        [_spec("first"), _spec("second")],
    )
    seen = []

    def handler(payload, context):
        seen.append((payload["input"], context.task_key))
        assert context.cancellation_requested() is False
        assert context.heartbeat() is True
        assert "must-not-be-logged" not in repr(context)
        return {"status": "success", "output": payload["input"].upper()}

    registry = {
        "text.transform": task_worker.TaskHandler(execute=handler),
    }

    first = task_worker.dispatch_once("owner:one", "worker-a", registry)
    second = task_worker.dispatch_once("owner:one", "worker-a", registry)

    assert first.status == "succeeded"
    assert second.status == "succeeded"
    assert first.task_id != second.task_id
    assert len(seen) == 2
    assert engine.get_graph("owner:one", graph.graph_id).status == "completed"
    stored = engine.get_task("owner:one", first.task_id, include_result=True)
    assert stored["result"]["output"].startswith("PAYLOAD-")


def test_unknown_task_types_are_not_claimed_or_failed(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    graph = engine.create_graph(
        "owner:one",
        "worker-unknown-type",
        [_spec("unknown", task_type="unregistered.task")],
    )
    called = []

    result = task_worker.dispatch_once(
        "owner:one",
        "worker-a",
        {"known.task": task_worker.TaskHandler(
            execute=lambda payload, context: called.append(True) or {"ok": True}
        )},
    )

    assert result is None
    task = engine.list_tasks("owner:one", graph.graph_id)[0]
    assert task["status"] == "queued"
    assert called == []


def test_worker_retries_only_retryable_exceptions_for_explicitly_safe_tasks(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    graph = engine.create_graph(
        "owner:one",
        "worker-retry-safe",
        [_spec("safe", retry_safe=True, max_attempts=2)],
    )
    calls = []

    def handler(_payload, _context):
        calls.append(True)
        if len(calls) == 1:
            raise TimeoutError("private timeout detail")
        return {"status": "success"}

    registry = {
        "text.transform": task_worker.TaskHandler(
            execute=handler,
            retryable_exceptions=(TimeoutError,),
            retry_delay_seconds=0,
        )
    }

    first = task_worker.dispatch_once("owner:one", "worker-a", registry)
    queued = engine.get_task("owner:one", first.task_id)
    assert first.status == "queued"
    assert first.error_code == "TimeoutError"
    assert queued["attempt_count"] == 1

    second = task_worker.dispatch_once("owner:one", "worker-b", registry)
    assert second.status == "succeeded"
    assert second.attempt_number == 2
    attempts = engine.list_attempts("owner:one", second.task_id)
    assert {item["status"] for item in attempts} == {"retryable_failure", "succeeded"}
    assert all(item["error_code"] != "private timeout detail" for item in attempts)


def test_handler_retry_classification_cannot_override_task_retry_safety(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    engine.create_graph("owner:one", "worker-unsafe-retry", [_spec("unsafe")])

    result = task_worker.dispatch_once(
        "owner:one",
        "worker-a",
        {
            "text.transform": task_worker.TaskHandler(
                execute=lambda *_: (_ for _ in ()).throw(TimeoutError("secret")),
                retryable_exceptions=(TimeoutError,),
                retry_delay_seconds=0,
            )
        },
    )

    assert result.status == "failed"
    task = engine.get_task("owner:one", result.task_id)
    assert task["attempt_count"] == 1
    assert engine.claim_next("owner:one", "worker-b") is None


def test_handler_can_observe_graph_cancellation_and_cannot_complete_cancelled_work(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    graph = engine.create_graph(
        "owner:one", "worker-cancel",
        [_spec("cancel-me")],
    )
    observed = []

    def handler(_payload, context):
        assert engine.cancel_graph("owner:one", context.graph_id)
        observed.append(context.cancellation_requested())
        return {"status": "should-not-persist"}

    result = task_worker.dispatch_once(
        "owner:one",
        "worker-a",
        {"text.transform": task_worker.TaskHandler(execute=handler)},
    )

    assert observed == [True]
    assert result.status == "cancelled"
    assert engine.get_graph("owner:one", graph.graph_id).status == "cancelled"
    task = engine.get_task("owner:one", result.task_id, include_result=True)
    assert task["status"] == "cancelled"
    assert "result" not in task


def test_worker_error_records_only_exception_class_and_no_message(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    engine.create_graph("owner:one", "worker-private-error", [_spec("bad")])

    result = task_worker.dispatch_once(
        "owner:one",
        "worker-a",
        {
            "text.transform": task_worker.TaskHandler(
                execute=lambda *_: (_ for _ in ()).throw(RuntimeError("private file path /tmp/secret"))
            )
        },
    )
    attempts = engine.list_attempts("owner:one", result.task_id)

    assert result.status == "failed"
    assert result.error_code == "RuntimeError"
    assert attempts[0]["error_code"] == "RuntimeError"
    assert "private file path" not in repr(attempts)


def test_worker_registry_validation_and_empty_registry(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    with pytest.raises(task_worker.TaskWorkerError):
        task_worker.dispatch_once("owner:one", "worker-a", {"task": object()})
    with pytest.raises(task_worker.TaskWorkerError):
        task_worker.TaskHandler(
            execute=lambda *_: {},
            retryable_exceptions=(str,),
        )
    assert task_worker.dispatch_once("owner:one", "worker-a", {}) is None



def test_dispatch_batch_runs_newly_ready_dependencies_with_a_hard_bound(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    graph = engine.create_graph(
        "owner:one",
        "worker-batch",
        [
            _spec("root"),
            engine.TaskSpec(
                task_key="child",
                task_type="text.transform",
                payload={"input": "child"},
                depends_on=("root",),
            ),
        ],
    )
    order = []

    def handler(payload, context):
        order.append(context.task_key)
        return {"status": "success", "key": context.task_key}

    results = task_worker.dispatch_batch(
        "owner:one",
        "worker-batch",
        {"text.transform": task_worker.TaskHandler(execute=handler)},
        max_tasks=2,
    )

    assert [item.task_key for item in results] == ["root", "child"]
    assert order == ["root", "child"]
    assert engine.get_graph("owner:one", graph.graph_id).status == "completed"


def test_dispatch_batch_rejects_unbounded_or_invalid_limits(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    for value in (0, 101, True, "5"):
        with pytest.raises(task_worker.TaskWorkerError):
            task_worker.dispatch_batch(
                "owner:one", "worker-a", {}, max_tasks=value
            )



def test_worker_registry_and_claim_type_filters_are_bounded(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    oversized_registry = {
        f"type-{index}": task_worker.TaskHandler(execute=lambda *_: {})
        for index in range(task_worker.MAX_REGISTERED_HANDLERS + 1)
    }
    with pytest.raises(task_worker.TaskWorkerError, match="at most"):
        task_worker.dispatch_once("owner:one", "worker-a", oversized_registry)

    with pytest.raises(engine.TaskEngineError, match="task_types"):
        engine.claim_next(
            "owner:one",
            "worker-a",
            task_types=[f"type-{index}" for index in range(engine.MAX_TASK_TYPES_PER_CLAIM + 1)],
        )
