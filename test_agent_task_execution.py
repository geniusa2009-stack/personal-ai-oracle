from cryptography.fernet import Fernet
import json

import pytest

import ai_core
import db
import durable_task_engine as engine
import agent_task_execution as agent_tasks


def _use_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "agent-task-execution.db"))
    monkeypatch.setenv(
        "ORACLE_CHECKPOINT_ENCRYPTION_KEY",
        Fernet.generate_key().decode("ascii"),
    )


def _plan():
    return {
        "steps": [
            {
                "task_key": "research",
                "agent_role": "researcher",
                "instruction": "Collect the most relevant evidence and identify uncertainty.",
                "depends_on": [],
            },
            {
                "task_key": "draft",
                "agent_role": "writer",
                "instruction": "Prepare a concise draft based on the research.",
                "depends_on": ["research"],
            },
            {
                "task_key": "technical_review",
                "agent_role": "coder",
                "instruction": "Review technical feasibility and list implementation risks.",
                "depends_on": ["research"],
            },
        ]
    }


def _create(monkeypatch, scope="owner:one", key="agent-plan-one"):
    monkeypatch.setattr(
        ai_core, "chat",
        lambda *_args, **_kwargs: json.dumps(_plan()),
    )
    return agent_tasks.create_agent_graph(
        scope, key, "Prepare a grounded technical proposal.", max_steps=5
    )


def test_planner_persists_typed_dag_with_final_review_and_dependencies(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    graph = _create(monkeypatch)

    tasks = engine.list_tasks("owner:one", graph.graph_id, include_payload=True)
    by_key = {item["task_key"]: item for item in tasks}

    assert graph.task_count == 4
    assert set(by_key) == {"research", "draft", "technical_review", "final_review"}
    assert by_key["research"]["task_type"] == agent_tasks.TASK_TYPE_AGENT_STEP
    assert by_key["research"]["payload"]["agent_role"] == "researcher"
    assert by_key["draft"]["payload"]["dependency_keys"] == ["research"]
    assert by_key["technical_review"]["payload"]["agent_role"] == "coder"
    assert by_key["final_review"]["task_type"] == agent_tasks.TASK_TYPE_AGENT_REVIEW
    assert by_key["final_review"]["payload"]["dependency_keys"] == [
        "research", "draft", "technical_review"
    ]
    assert engine.list_graphs("owner:two") == []


@pytest.mark.parametrize("raw", [
    '{"steps":[{"task_key":"bad","agent_role":"executor","instruction":"Do it","depends_on":[]}]}',
    '{"steps":[{"task_key":"bad","agent_role":"writer","instruction":"Do it","depends_on":["missing"]}]}',
    '{"steps":[{"task_key":"bad","agent_role":"writer","instruction":"Do it","depends_on":[],"tool_id":"local.run_command"}]}',
    '{"steps":[]}',
    '{"steps":[{"task_key":"bad","agent_role":"writer","instruction":"Do it","depends_on":["bad"]}]}',
])
def test_planner_rejects_untrusted_or_invalid_plan_shapes(monkeypatch, tmp_path, raw):
    _use_db(monkeypatch, tmp_path)
    monkeypatch.setattr(ai_core, "chat", lambda *_a, **_k: raw)

    with pytest.raises(agent_tasks.AgentTaskExecutionError):
        agent_tasks.create_agent_graph("owner:one", "bad-plan", "Do a bounded task.")


def test_planner_uses_engine_cycle_validation(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    cycle = {
        "steps": [
            {"task_key": "alpha", "agent_role": "writer", "instruction": "Write A", "depends_on": ["beta"]},
            {"task_key": "beta", "agent_role": "researcher", "instruction": "Research B", "depends_on": ["alpha"]},
        ]
    }
    monkeypatch.setattr(ai_core, "chat", lambda *_a, **_k: json.dumps(cycle))

    with pytest.raises(engine.TaskEngineError, match="cycle"):
        agent_tasks.create_agent_graph("owner:one", "cycle-plan", "Do a bounded task.")


def test_dispatch_runs_specialists_in_dependency_order_and_persists_review(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    graph = _create(monkeypatch)
    calls = []

    def fake_chat(messages, **kwargs):
        role = kwargs["agent_role"]
        calls.append(role)
        if role == "reviewer":
            return json.dumps({
                "decision": "accepted",
                "summary": "The requested work is covered by the specialist outputs.",
                "issues": [],
                "completed_requirements": ["Research completed", "Draft and technical review completed"],
            })
        prompt = messages[-1]["content"]
        if role == "researcher":
            return "Research notes: source coverage is limited and needs verification."
        assert "Research notes" in prompt
        if role == "writer":
            return "Draft based on the supplied research notes."
        if role == "coder":
            return "Technical review: implementation is feasible with the listed constraints."
        raise AssertionError(f"unexpected agent role: {role}")

    monkeypatch.setattr(ai_core, "chat", fake_chat)
    dispatched = agent_tasks.dispatch_agent_tasks(
        "owner:one", "control-center-agent-worker", max_tasks=4
    )

    assert [item.status for item in dispatched] == ["succeeded"] * 4
    assert calls == ["researcher", "writer", "coder", "reviewer"]
    result = agent_tasks.get_agent_graph_result("owner:one", graph.graph_id)
    assert result is not None
    assert result["status"] == "completed"
    assert result["accepted"] is True
    assert result["final_review"]["decision"] == "accepted"
    assert result["final_review"]["factual_truth_verified"] is False
    assert result["succeeded_count"] == 4
    assert all(
        item["result"] for item in result["tasks"]
        if item["task_type"] == agent_tasks.TASK_TYPE_AGENT_STEP
    )


def test_graph_can_resume_after_app_restart_without_losing_completed_agent_results(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    graph = _create(monkeypatch)
    calls = []

    def fake_chat(_messages, **kwargs):
        calls.append(kwargs["agent_role"])
        if kwargs["agent_role"] == "reviewer":
            return json.dumps({
                "decision": "accepted", "summary": "All steps were reviewed.",
                "issues": [], "completed_requirements": ["All planned steps"],
            })
        return f"Persisted output from {kwargs['agent_role']}."

    monkeypatch.setattr(ai_core, "chat", fake_chat)
    first_batch = agent_tasks.dispatch_agent_tasks(
        "owner:one", "worker-before-restart", max_tasks=1
    )
    assert len(first_batch) == 1
    first_task_id = first_batch[0].task_id
    first_result = engine.get_task("owner:one", first_task_id, include_result=True)
    assert first_result["status"] == "succeeded"

    # Simulate a fresh app process: all state is reconstructed from the DB.
    resumed_graph = engine.get_graph("owner:one", graph.graph_id)
    assert resumed_graph is not None
    assert resumed_graph.succeeded_count == 1
    second_batch = agent_tasks.dispatch_agent_tasks(
        "owner:one", "worker-after-restart", max_tasks=3
    )
    assert len(second_batch) == 3
    assert all(item.status == "succeeded" for item in second_batch)
    assert calls.count("researcher") == 1
    final = agent_tasks.get_agent_graph_result("owner:one", graph.graph_id)
    assert final["accepted"] is True
    assert engine.get_task("owner:one", first_task_id, include_result=True)["result"] == first_result["result"]


def test_review_needs_revision_is_not_reported_as_accepted(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    graph = _create(monkeypatch)

    def fake_chat(_messages, **kwargs):
        if kwargs["agent_role"] == "reviewer":
            return json.dumps({
                "decision": "needs_revision",
                "summary": "The requested proposal is missing a risk section.",
                "issues": ["Risk section is missing"],
                "completed_requirements": ["Research completed"],
            })
        return "A specialist result."

    monkeypatch.setattr(ai_core, "chat", fake_chat)
    agent_tasks.dispatch_agent_tasks("owner:one", "review-worker", max_tasks=4)
    result = agent_tasks.get_agent_graph_result("owner:one", graph.graph_id)

    assert result["status"] == "completed"
    assert result["accepted"] is False
    assert result["final_review"]["decision"] == "needs_revision"


def test_failed_dependency_blocks_descendants_and_final_review(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    graph = _create(monkeypatch)
    calls = []

    def fake_chat(_messages, **kwargs):
        calls.append(kwargs["agent_role"])
        if kwargs["agent_role"] == "researcher":
            raise RuntimeError("provider unavailable")
        return "unexpected"

    monkeypatch.setattr(ai_core, "chat", fake_chat)
    dispatched = agent_tasks.dispatch_agent_tasks(
        "owner:one", "failing-worker", max_tasks=8
    )
    result = agent_tasks.get_agent_graph_result("owner:one", graph.graph_id)

    assert len(dispatched) == 1
    assert dispatched[0].status == "failed"
    assert calls == ["researcher"]
    assert result["failed_count"] == 1
    assert result["blocked_count"] == 3
    assert result["final_review"] is None


def test_result_projection_is_scope_bound_and_does_not_expose_payloads(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    graph = _create(monkeypatch)
    monkeypatch.setattr(ai_core, "chat", lambda *_a, **kw: (
        json.dumps({
            "decision": "accepted", "summary": "Reviewed.",
            "issues": [], "completed_requirements": ["Done"],
        }) if kw["agent_role"] == "reviewer" else "Specialist output."
    ))
    agent_tasks.dispatch_agent_tasks("owner:one", "worker-a", max_tasks=4)

    assert agent_tasks.get_agent_graph_result("owner:two", graph.graph_id) is None
    visible = agent_tasks.get_agent_graph_result("owner:one", graph.graph_id)
    assert visible is not None
    assert "payload" not in repr(visible)
    assert "lease_token" not in repr(visible)
    assert visible["accepted"] is True


def test_dispatch_batch_limit_is_bounded(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    for invalid in (0, 9, True, "3"):
        with pytest.raises(agent_tasks.AgentTaskExecutionError):
            agent_tasks.dispatch_agent_tasks("owner:one", "worker", max_tasks=invalid)


def test_expired_in_progress_agent_task_is_reclaimed_after_process_restart(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    graph = _create(monkeypatch)
    interrupted = engine.claim_next(
        "owner:one",
        "worker-before-crash",
        task_types=(agent_tasks.TASK_TYPE_AGENT_STEP,),
        lease_seconds=30,
    )
    assert interrupted is not None
    assert interrupted.task_key == "research"
    engine.start_task(
        "owner:one", interrupted.task_id,
        interrupted.worker_id, interrupted.lease_token,
    )
    conn = db.get_conn()
    try:
        conn.execute(
            "UPDATE oracle_durable_tasks SET lease_expires_at=0 WHERE task_id=?",
            (interrupted.task_id,),
        )
        conn.commit()
    finally:
        conn.close()

    def fake_chat(_messages, **kwargs):
        if kwargs["agent_role"] == "reviewer":
            return json.dumps({
                "decision": "accepted",
                "summary": "Recovered graph completed and reviewed.",
                "issues": [],
                "completed_requirements": ["All planned specialist tasks"],
            })
        return f"Recovered output from {kwargs['agent_role']}."

    monkeypatch.setattr(ai_core, "chat", fake_chat)
    recovered = agent_tasks.dispatch_agent_tasks(
        "owner:one", "worker-after-restart", max_tasks=4
    )

    assert len(recovered) == 4
    assert recovered[0].task_key == "research"
    assert recovered[0].attempt_number == 2
    assert all(item.status == "succeeded" for item in recovered)
    attempts = engine.list_attempts("owner:one", interrupted.task_id)
    assert len(attempts) == 2
    assert {item["status"] for item in attempts} == {"lease_expired", "succeeded"}
    final = agent_tasks.get_agent_graph_result("owner:one", graph.graph_id)
    assert final["accepted"] is True
