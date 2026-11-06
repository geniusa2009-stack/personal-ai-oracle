import sqlite3

import db
import pytest
import workflow_ledger


def _use_test_database(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "workflow-ledger.db"))


def test_workflow_trace_stores_only_digests_and_step_metadata(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    private_task = "private-task-content-should-not-be-stored"
    private_input = "private-file-content-should-not-be-stored"
    private_output = "private-tool-output-should-not-be-stored"

    workflow_id = workflow_ledger.start_run("owner:one", private_task, 4)
    workflow_ledger.begin_step("owner:one", workflow_id, 0, "local.read_file", private_input)
    workflow_ledger.complete_step(
        "owner:one",
        workflow_id,
        0,
        {"status": "success", "result": private_output},
        duration_ms=123,
    )
    assert workflow_ledger.finish_run("owner:one", workflow_id, "completed") is True

    run = workflow_ledger.list_runs("owner:one")[0]
    step = workflow_ledger.list_steps("owner:one", workflow_id)[0]
    conn = db.get_conn()
    try:
        run_raw = " ".join(str(row) for row in conn.execute(
            "SELECT * FROM oracle_workflow_runs"
        ).fetchall())
        step_raw = " ".join(str(row) for row in conn.execute(
            "SELECT * FROM oracle_workflow_steps"
        ).fetchall())
        raw = run_raw + " " + step_raw
    finally:
        conn.close()

    assert run["workflow_id"] == workflow_id
    assert run["status"] == "completed"
    assert len(run["task_digest"]) == 64
    assert step["status"] == "success"
    assert len(step["input_digest"]) == 64
    assert len(step["output_digest"]) == 64
    assert step["duration_ms"] == 123
    assert private_task not in raw
    assert private_input not in raw
    assert private_output not in raw


def test_workflow_ledger_enforces_scope_ownership(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    workflow_id = workflow_ledger.start_run("owner:one", "task", 2)
    workflow_ledger.begin_step("owner:one", workflow_id, 0, "web.search", "query")

    assert workflow_ledger.list_runs("owner:two") == []
    assert workflow_ledger.list_steps("owner:two", workflow_id) == []
    with pytest.raises(workflow_ledger.WorkflowLedgerError):
        workflow_ledger.complete_step(
            "owner:two", workflow_id, 0, {"status": "success"}, duration_ms=1
        )
    assert workflow_ledger.finish_run("owner:two", workflow_id, "completed") is False
    assert workflow_ledger.list_runs("owner:one")[0]["status"] == "running"
    assert workflow_ledger.finish_run("owner:one", workflow_id, "failed", error_code="AgentError")


def test_workflow_ledger_rejects_invalid_states_and_unbounded_inputs(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    for invalid in (("", "task", 1), ("owner:one", "", 1), ("owner:one", "task", 31)):
        with pytest.raises(workflow_ledger.WorkflowLedgerError):
            workflow_ledger.start_run(*invalid)

    workflow_id = workflow_ledger.start_run("owner:one", "task", 1)
    with pytest.raises(workflow_ledger.WorkflowLedgerError):
        workflow_ledger.begin_step("owner:one", workflow_id, 0, "x", "input")
    with pytest.raises(workflow_ledger.WorkflowLedgerError):
        workflow_ledger.begin_step("owner:one", workflow_id, 31, "local.read_file", "input")
    with pytest.raises(workflow_ledger.WorkflowLedgerError):
        workflow_ledger.finish_run("owner:one", workflow_id, "unknown")


def test_workflow_ledger_records_interrupted_step_as_running(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    workflow_id = workflow_ledger.start_run("owner:one", "task", 2)
    workflow_ledger.begin_step("owner:one", workflow_id, 0, "local.run_command", {"command": ["git", "status"]})

    steps = workflow_ledger.list_steps("owner:one", workflow_id)

    assert len(steps) == 1
    assert steps[0]["status"] == "running"
    assert workflow_ledger.list_runs("owner:one")[0]["status"] == "running"
