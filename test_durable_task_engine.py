import pytest

import database
import db
import durable_task_engine as engine
from cryptography.fernet import Fernet


def _use_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "durable-task-engine.db"))
    monkeypatch.setenv(
        "ORACLE_CHECKPOINT_ENCRYPTION_KEY",
        Fernet.generate_key().decode("ascii"),
    )


def _task(key, *, deps=(), payload=None, retry_safe=False, max_attempts=1):
    return engine.TaskSpec(
        task_key=key,
        task_type="unit_test",
        payload=payload or {"key": key, "private": "not-plaintext"},
        depends_on=tuple(deps),
        retry_safe=retry_safe,
        max_attempts=max_attempts,
    )


def _claim(scope, worker="worker-a"):
    lease = engine.claim_next(scope, worker, lease_seconds=30)
    assert lease is not None
    return lease


def _start(lease):
    assert engine.start_task(
        lease.scope, lease.task_id, lease.worker_id, lease.lease_token
    )


def _complete(lease, result=None):
    _start(lease)
    assert engine.complete_task(
        lease.scope, lease.task_id, lease.worker_id, lease.lease_token,
        result or {"status": "ok"},
    )


def test_create_graph_validates_dag_and_is_idempotent(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    specs = [
        _task("discover"),
        _task("verify", deps=("discover",)),
        _task("summarize", deps=("verify",)),
    ]

    first = engine.create_graph("owner:one", "request-123", specs)
    repeated = engine.create_graph("owner:one", "request-123", specs)

    assert first.graph_id == repeated.graph_id
    assert first.status == "active"
    assert first.task_count == 3
    assert len(engine.list_tasks("owner:one", first.graph_id)) == 3
    with pytest.raises(engine.TaskIdempotencyConflict):
        engine.create_graph("owner:one", "request-123", [_task("different")])

    with pytest.raises(engine.TaskEngineError, match="cycle"):
        engine.create_graph(
            "owner:one", "cycle",
            [_task("a", deps=("b",)), _task("b", deps=("a",))],
        )
    with pytest.raises(engine.TaskEngineError, match="unknown"):
        engine.create_graph("owner:one", "missing", [_task("a", deps=("absent",))])


def test_dependency_order_and_encrypted_payload_result_round_trip(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    graph = engine.create_graph(
        "owner:one",
        "dag-1",
        [
            _task("first", payload={"secret": "source-material"}),
            _task("second", deps=("first",), payload={"secret": "verification-input"}),
        ],
    )

    first = _claim("owner:one")
    assert first.task_key == "first"
    assert first.payload == {"secret": "source-material"}
    assert engine.claim_next("owner:one", "worker-b") is None

    _complete(first, {"status": "success", "private_result": "confidential-output"})
    second = _claim("owner:one", "worker-b")
    assert second.task_key == "second"
    _complete(second, {"status": "success", "summary": "done"})

    result = engine.get_task(
        "owner:one", first.task_id, include_payload=True, include_result=True
    )
    assert result["status"] == "succeeded"
    assert result["payload"] == {"secret": "source-material"}
    assert result["result"]["private_result"] == "confidential-output"
    assert engine.get_graph("owner:one", graph.graph_id).status == "completed"

    conn = db.get_conn()
    try:
        raw = " ".join(
            str(row)
            for table in ("oracle_durable_tasks", "oracle_task_attempts")
            for row in conn.execute(f"SELECT * FROM {table}").fetchall()
        )
    finally:
        conn.close()
    assert "source-material" not in raw
    assert "confidential-output" not in raw


def test_atomic_claims_do_not_lease_the_same_task_twice(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    graph = engine.create_graph(
        "owner:one", "parallel",
        [_task("one"), _task("two"), _task("three")],
    )

    leases = [
        engine.claim_next("owner:one", f"worker-{index}", lease_seconds=30)
        for index in range(3)
    ]

    assert all(item is not None for item in leases)
    assert len({item.task_id for item in leases}) == 3
    assert engine.claim_next("owner:one", "worker-extra") is None
    assert all(engine.start_task(
        item.scope, item.task_id, item.worker_id, item.lease_token
    ) for item in leases)


def test_lease_is_owner_and_token_bound_and_heartbeat_extends_it(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    engine.create_graph("owner:one", "lease", [_task("work")])
    lease = _claim("owner:one")

    with pytest.raises(engine.TaskEngineError, match="lease"):
        engine.start_task("owner:one", lease.task_id, "worker-other", lease.lease_token)
    with pytest.raises(engine.TaskEngineError, match="lease"):
        engine.start_task("owner:one", lease.task_id, lease.worker_id, "x" * 40)

    before = lease.lease_expires_at
    assert engine.heartbeat(
        "owner:one", lease.task_id, lease.worker_id, lease.lease_token,
        lease_seconds=90,
    )
    current = engine.get_task("owner:one", lease.task_id)
    assert current["lease_expires_at"] > before


def test_retry_is_disabled_by_default_even_when_failure_is_retryable(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    graph = engine.create_graph(
        "owner:one", "no-auto-retry",
        [_task("send_email", payload={"action": "send"}, retry_safe=False)],
    )
    lease = _claim("owner:one")
    _start(lease)
    failed = engine.fail_task(
        "owner:one", lease.task_id, lease.worker_id, lease.lease_token,
        error_code="TimeoutError", retryable=True, retry_delay_seconds=0,
    )

    assert failed["status"] == "failed"
    assert failed["attempt_count"] == 1
    assert engine.claim_next("owner:one", "worker-b") is None
    assert engine.get_graph("owner:one", graph.graph_id).status == "failed"


def test_only_explicit_retry_safe_task_can_retry_with_bounded_backoff(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    engine.create_graph(
        "owner:one", "retry-safe",
        [_task("pure_transform", retry_safe=True, max_attempts=2)],
    )
    first = _claim("owner:one")
    _start(first)
    retry = engine.fail_task(
        "owner:one", first.task_id, first.worker_id, first.lease_token,
        error_code="TemporaryError", retryable=True, retry_delay_seconds=0,
    )

    assert retry["status"] == "queued"
    assert retry["attempt_count"] == 1
    second = _claim("owner:one", "worker-b")
    assert second.attempt_number == 2
    _complete(second)
    attempts = engine.list_attempts("owner:one", second.task_id)
    assert [item["status"] for item in attempts] == ["succeeded", "retryable_failure"]


def test_expired_lease_requeues_only_retry_safe_work(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    retry_graph = engine.create_graph(
        "owner:one", "expiry-retry",
        [_task("safe", retry_safe=True, max_attempts=2)],
    )
    safe = _claim("owner:one", "worker-safe")
    _start(safe)
    conn = db.get_conn()
    try:
        conn.execute(
            "UPDATE oracle_durable_tasks SET lease_expires_at=? WHERE task_id=?",
            (0, safe.task_id),
        )
        conn.commit()
    finally:
        conn.close()

    assert engine.reap_expired_leases("owner:one") == 1
    safe_task = engine.get_task("owner:one", safe.task_id)
    assert safe_task["status"] == "queued"
    second = _claim("owner:one", "worker-safe-2")
    assert second.attempt_number == 2

    no_retry_graph = engine.create_graph(
        "owner:two", "expiry-no-retry", [_task("unsafe")]
    )
    unsafe = _claim("owner:two", "worker-unsafe")
    conn = db.get_conn()
    try:
        conn.execute(
            "UPDATE oracle_durable_tasks SET lease_expires_at=? WHERE task_id=?",
            (0, unsafe.task_id),
        )
        conn.commit()
    finally:
        conn.close()

    assert engine.reap_expired_leases("owner:two") == 1
    assert engine.get_task("owner:two", unsafe.task_id)["status"] == "failed"
    assert engine.get_graph("owner:two", no_retry_graph.graph_id).status == "failed"


def test_failed_dependency_blocks_descendants_and_fails_graph(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    graph = engine.create_graph(
        "owner:one", "dependency-failure",
        [_task("root"), _task("child", deps=("root",)), _task("leaf", deps=("child",))],
    )
    root = _claim("owner:one")
    _start(root)
    engine.fail_task(
        "owner:one", root.task_id, root.worker_id, root.lease_token,
        error_code="PermanentError", retryable=False,
    )

    tasks = engine.list_tasks("owner:one", graph.graph_id)
    by_key = {item["task_key"]: item["status"] for item in tasks}
    assert by_key == {"root": "failed", "child": "blocked", "leaf": "blocked"}
    assert engine.claim_next("owner:one", "worker-b") is None
    assert engine.get_graph("owner:one", graph.graph_id).status == "failed"


def test_pause_resume_and_cancel_graph_control_claims(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    graph = engine.create_graph("owner:one", "pause-cancel", [_task("one"), _task("two")])
    preleased = _claim("owner:one", "worker-before-pause")
    assert engine.pause_graph("owner:one", graph.graph_id)
    assert engine.claim_next("owner:one", "worker-a") is None
    assert engine.get_task("owner:one", preleased.task_id)["status"] == "queued"
    with pytest.raises(engine.TaskEngineError):
        engine.start_task(
            "owner:one", preleased.task_id, preleased.worker_id, preleased.lease_token
        )
    assert engine.resume_graph("owner:one", graph.graph_id)

    lease = _claim("owner:one")
    assert lease.task_id == preleased.task_id
    assert lease.attempt_number == 1
    assert engine.cancel_graph("owner:one", graph.graph_id)
    assert engine.claim_next("owner:one", "worker-b") is None
    assert engine.get_graph("owner:one", graph.graph_id).status == "cancelled"
    with pytest.raises(engine.TaskEngineError):
        engine.start_task("owner:one", lease.task_id, lease.worker_id, lease.lease_token)


def test_scope_isolation_and_sensitive_panic_wipe(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    graph = engine.create_graph("owner:one", "scope-one", [_task("private")])
    assert engine.get_graph("owner:two", graph.graph_id) is None
    assert engine.list_graphs("owner:two") == []
    assert engine.list_tasks("owner:two", graph.graph_id) == []

    wiped = database.panic_wipe(tables=[
        "oracle_task_graphs",
        "oracle_durable_tasks",
        "oracle_task_dependencies",
        "oracle_task_attempts",
    ])
    assert wiped["oracle_task_graphs"] == 1
    assert wiped["oracle_durable_tasks"] == 1
    assert engine.get_graph("owner:one", graph.graph_id) is None


def test_invalid_retry_policy_and_worker_arguments_are_rejected(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    with pytest.raises(engine.TaskEngineError, match="max_attempts=1"):
        engine.create_graph(
            "owner:one", "unsafe-retry",
            [_task("write_file", retry_safe=False, max_attempts=2)],
        )
    graph = engine.create_graph("owner:one", "bad-worker", [_task("one")])
    with pytest.raises(engine.TaskEngineError):
        engine.claim_next("owner:one", "worker with spaces")
    with pytest.raises(engine.TaskEngineError):
        engine.claim_next("owner:one", "worker", lease_seconds=1)



def test_task_lease_representation_does_not_disclose_payload_or_lease_token(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    graph = engine.create_graph(
        "owner:one",
        "redacted-repr",
        [_task("private", payload={"api_key": "never-print-this-value"})],
    )
    lease = _claim("owner:one")

    rendered = repr(lease)
    assert "never-print-this-value" not in rendered
    assert lease.lease_token not in rendered
    assert graph.graph_id in rendered



def test_task_error_code_rejects_free_form_exception_details(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    engine.create_graph("owner:one", "error-code", [_task("work")])
    lease = _claim("owner:one")
    _start(lease)

    with pytest.raises(engine.TaskEngineError, match="error_code"):
        engine.fail_task(
            "owner:one", lease.task_id, lease.worker_id, lease.lease_token,
            error_code="TimeoutError leaked private path /Users/owner/secret",
            retryable=False,
        )

    assert engine.get_task("owner:one", lease.task_id)["status"] == "running"
    failed = engine.fail_task(
        "owner:one", lease.task_id, lease.worker_id, lease.lease_token,
        error_code="TimeoutError", retryable=False,
    )
    assert failed["status"] == "failed"
    assert failed["last_error_code"] == "TimeoutError"


def test_claim_next_reclaims_expired_retry_safe_lease_in_the_same_call(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    graph = engine.create_graph(
        "owner:one",
        "same-call-expired-lease",
        [_task("recover", retry_safe=True, max_attempts=2)],
    )
    first = _claim("owner:one", "worker-before-restart")
    _start(first)
    conn = db.get_conn()
    try:
        conn.execute(
            "UPDATE oracle_durable_tasks SET lease_expires_at=0 WHERE task_id=?",
            (first.task_id,),
        )
        conn.commit()
    finally:
        conn.close()

    recovered = engine.claim_next("owner:one", "worker-after-restart")

    assert recovered is not None
    assert recovered.task_id == first.task_id
    assert recovered.attempt_number == 2
    assert recovered.lease_token != first.lease_token
    assert engine.get_graph("owner:one", graph.graph_id).status == "active"
