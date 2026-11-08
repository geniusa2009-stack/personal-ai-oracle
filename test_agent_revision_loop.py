import json

import pytest

import ai_core
import agent_task_execution as agent_tasks
import durable_task_engine as engine


def _needs_revision_graph(monkeypatch, tmp_path, *, issues=None):
    agent_tasks_test_setup(monkeypatch, tmp_path)
    graph = agent_tasks.create_agent_graph(
        "owner:one", "root-agent-plan", "Prepare a grounded technical proposal.", max_steps=5
    )
    review_issues = issues or ["Add a risk section.", "Clarify technical constraints."]

    def initial_chat(messages, **kwargs):
        role = kwargs["agent_role"]
        if role == "reviewer":
            return json.dumps({
                "decision": "needs_revision",
                "summary": "The proposal needs targeted corrections.",
                "issues": review_issues,
                "completed_requirements": ["Research completed"],
            })
        return f"Original {role} output."

    monkeypatch.setattr(ai_core, "chat", initial_chat)
    agent_tasks.dispatch_agent_tasks("owner:one", "initial-worker", max_tasks=4)
    result = agent_tasks.get_agent_graph_result("owner:one", graph.graph_id)
    assert result["final_review"]["decision"] == "needs_revision"
    return graph


def agent_task_execution_test_plan():
    return {
        "steps": [
            {
                "task_key": "research",
                "agent_role": "researcher",
                "instruction": "Collect evidence.",
                "depends_on": [],
            },
            {
                "task_key": "draft",
                "agent_role": "writer",
                "instruction": "Prepare the draft.",
                "depends_on": ["research"],
            },
            {
                "task_key": "technical_review",
                "agent_role": "coder",
                "instruction": "Review technical feasibility.",
                "depends_on": ["research"],
            },
        ]
    }


def agent_task_execution_test_setup(monkeypatch, tmp_path):
    from cryptography.fernet import Fernet
    import db

    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "agent-revisions.db"))
    monkeypatch.setenv(
        "ORACLE_CHECKPOINT_ENCRYPTION_KEY",
        Fernet.generate_key().decode("ascii"),
    )
    monkeypatch.setattr(
        ai_core, "chat",
        lambda *_args, **_kwargs: json.dumps(agent_task_execution_test_plan()),
    )


def _revision_plan_two_tasks():
    return {
        "revisions": [
            {
                "source_task_key": "draft",
                "issue_indices": [1],
                "instruction": "Add the missing risk section and preserve the existing draft.",
                "depends_on": ["research"],
            },
            {
                "source_task_key": "technical_review",
                "issue_indices": [2],
                "instruction": "Clarify the technical constraints and assumptions.",
                "depends_on": ["draft"],
            },
        ]
    }


def test_revision_loop_reruns_only_affected_agents_and_merges_unchanged_results(monkeypatch, tmp_path):
    root = _needs_revision_graph(monkeypatch, tmp_path)
    calls = []

    def revision_chat(messages, **kwargs):
        role = kwargs["agent_role"]
        calls.append(role)
        if role == "planner":
            return json.dumps(_revision_plan_two_tasks())
        if role == "writer":
            assert "Add a risk section." in messages[-1]["content"]
            return "Revised draft with a dedicated risk section."
        if role == "coder":
            assert "Revised draft with a dedicated risk section." in messages[-1]["content"]
            return "Revised technical review with explicit constraints."
        if role == "reviewer":
            prompt = json.loads(messages[-1]["content"])
            merged = {item["task_key"]: item["output"] for item in prompt["merged_specialist_results"]}
            assert merged["research"] == "Original researcher output."
            assert merged["draft"] == "Revised draft with a dedicated risk section."
            assert merged["technical_review"] == "Revised technical review with explicit constraints."
            return json.dumps({
                "decision": "accepted",
                "summary": "Both requested corrections are now present.",
                "issues": [],
                "completed_requirements": ["Risk section added", "Technical constraints clarified"],
            })
        raise AssertionError(f"unexpected agent role: {role}")

    monkeypatch.setattr(ai_core, "chat", revision_chat)
    revision_graph = agent_tasks.create_revision_graph("owner:one", root.graph_id)

    assert revision_graph.task_count == 3
    assert revision_graph.pending_count == 3
    revision_tasks = engine.list_tasks("owner:one", revision_graph.graph_id, include_payload=True)
    revision_keys = {item["task_key"]: item for item in revision_tasks}
    assert set(revision_keys) == {"r1_draft", "r1_technical_review", "final_review"}
    assert revision_keys["r1_technical_review"]["payload"]["revision_dependency_keys"] == ["r1_draft"]
    assert revision_keys["r1_technical_review"]["depends_on"] == () or revision_keys["r1_technical_review"]["status"] == "queued"

    dispatched = agent_tasks.dispatch_agent_tasks(
        "owner:one", "revision-worker", max_tasks=3
    )
    assert [item.status for item in dispatched] == ["succeeded"] * 3
    assert calls == ["planner", "writer", "coder", "reviewer"]
    result = agent_tasks.get_agent_graph_result("owner:one", revision_graph.graph_id)
    assert result["accepted"] is True
    assert result["revision"]["revision_index"] == 1
    assert result["revision"]["completed_cycles"] == 1
    assert result["revision"]["remaining_cycles"] == agent_tasks.MAX_REVISION_CYCLES - 1
    assert result["final_review"]["decision"] == "accepted"
    assert [item["source_task_key"] for item in result["tasks"] if item["result"]] == [
        "draft", "technical_review"
    ]


def test_revision_creation_is_idempotent_and_old_parent_cannot_branch(monkeypatch, tmp_path):
    root = _needs_revision_graph(monkeypatch, tmp_path)
    calls = []

    def planner(_messages, **kwargs):
        calls.append(kwargs["agent_role"])
        return json.dumps({
            "revisions": [{
                "source_task_key": "draft",
                "issue_indices": [1, 2],
                "instruction": "Resolve both review issues in the draft.",
                "depends_on": ["research"],
            }]
        })

    monkeypatch.setattr(ai_core, "chat", planner)
    first = agent_tasks.create_revision_graph("owner:one", root.graph_id)
    second = agent_tasks.create_revision_graph("owner:one", root.graph_id)

    assert first.graph_id == second.graph_id
    assert calls == ["planner"]
    assert agent_tasks.get_agent_graph_result("owner:one", root.graph_id)["revision"]["can_create_revision"] is False
    with pytest.raises(agent_tasks.AgentTaskExecutionError, match="newer revision"):
        agent_tasks.create_revision_graph("owner:one", root.graph_id)


def test_revision_requires_completed_rejected_review_and_owner_scope(monkeypatch, tmp_path):
    agent_task_execution_test_setup(monkeypatch, tmp_path)
    graph = agent_task_execution.create_agent_graph(
        "owner:one", "root-not-run", "Prepare a grounded technical proposal."
    )
    with pytest.raises(agent_task_execution.AgentTaskExecutionError, match="completed"):
        agent_task_execution.create_revision_graph("owner:one", graph.graph_id)
    with pytest.raises(agent_task_execution.AgentTaskExecutionError, match="owner scope"):
        agent_task_execution.create_revision_graph("owner:two", graph.graph_id)


def test_revision_planner_must_cover_all_review_issues_and_cannot_invent_tasks(monkeypatch, tmp_path):
    root = _needs_revision_graph(monkeypatch, tmp_path)
    monkeypatch.setattr(ai_core, "chat", lambda *_a, **_k: json.dumps({
        "revisions": [{
            "source_task_key": "invented_task",
            "issue_indices": [1, 2],
            "instruction": "Fix the issue.",
            "depends_on": [],
        }]
    }))
    with pytest.raises(agent_task_execution.AgentTaskExecutionError, match="unknown or duplicate"):
        agent_task_execution.create_revision_graph("owner:one", root.graph_id)

    monkeypatch.setattr(ai_core, "chat", lambda *_a, **_k: json.dumps({
        "revisions": [{
            "source_task_key": "draft",
            "issue_indices": [1],
            "instruction": "Fix only the first issue.",
            "depends_on": [],
        }]
    }))
    with pytest.raises(agent_task_execution.AgentTaskExecutionError, match="did not cover every"):
        agent_task_execution.create_revision_graph("owner:one", root.graph_id)


def test_revision_loop_has_a_hard_two_cycle_cap(monkeypatch, tmp_path):
    root = _needs_revision_graph(monkeypatch, tmp_path, issues=["Add a risk section."])
    revision_parent = root.graph_id

    for revision_index in (1, 2):
        def revision_chat(_messages, **kwargs):
            if kwargs["agent_role"] == "planner":
                return json.dumps({
                    "revisions": [{
                        "source_task_key": "draft",
                        "issue_indices": [1],
                        "instruction": f"Address the remaining issue in cycle {revision_index}.",
                        "depends_on": [],
                    }]
                })
            if kwargs["agent_role"] == "reviewer":
                return json.dumps({
                    "decision": "needs_revision",
                    "summary": "One issue remains.",
                    "issues": ["One required detail remains."],
                    "completed_requirements": ["Research completed"],
                })
            return f"Updated draft cycle {revision_index}."

        monkeypatch.setattr(ai_core, "chat", revision_chat)
        revision_graph = agent_task_execution.create_revision_graph("owner:one", revision_parent)
        agent_task_execution.dispatch_agent_tasks(
            "owner:one", f"cycle-worker-{revision_index}", max_tasks=2
        )
        revision_parent = revision_graph.graph_id

    final = agent_task_execution.get_agent_graph_result("owner:one", revision_parent)
    assert final["revision"]["completed_cycles"] == 2
    assert final["revision"]["remaining_cycles"] == 0
    assert final["revision"]["can_create_revision"] is False
    with pytest.raises(agent_task_execution.AgentTaskExecutionError, match="maximum revision cycles"):
        agent_task_execution.create_revision_graph("owner:one", revision_parent)


def test_accepted_graph_cannot_enter_revision_loop(monkeypatch, tmp_path):
    agent_task_execution_test_setup(monkeypatch, tmp_path)
    graph = agent_task_execution.create_agent_graph(
        "owner:one", "root-accepted", "Prepare a grounded technical proposal."
    )
    monkeypatch.setattr(ai_core, "chat", lambda _messages, **kwargs: (
        json.dumps({
            "decision": "accepted",
            "summary": "The work is complete.",
            "issues": [],
            "completed_requirements": ["All requirements"],
        }) if kwargs["agent_role"] == "reviewer" else "Original specialist output."
    ))
    agent_task_execution.dispatch_agent_tasks("owner:one", "accepted-worker", max_tasks=4)
    with pytest.raises(agent_task_execution.AgentTaskExecutionError, match="does not require revision"):
        agent_task_execution.create_revision_graph("owner:one", graph.graph_id)
