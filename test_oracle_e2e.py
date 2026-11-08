from cryptography.fernet import Fernet
import json

import ai_core
import agent_task_execution
import db
import deep_research
import durable_task_engine
import memory
import task_control_center


def _use_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "oracle-e2e.db"))
    monkeypatch.setenv(
        "ORACLE_CHECKPOINT_ENCRYPTION_KEY",
        Fernet.generate_key().decode("ascii"),
    )


def _research_report():
    return {
        "status": "success",
        "query": "Prepare a grounded technical proposal.",
        "answer": "The inspected source supports the core finding [S1].",
        "key_findings": ["The source documents the core behavior."],
        "limitations": ["Only one bounded source was inspected."],
        "citations": [{
            "id": "S1",
            "title": "Official technical documentation",
            "url": "https://example.org/docs",
            "domain": "example.org",
            "publisher": "Example",
            "published_at": "2026-11-01",
            "updated_at": None,
        }],
        "sources": [{
            "citation_id": "S1",
            "title": "Official technical documentation",
            "domain": "example.org",
            "page_status": "extracted",
            "evidence_excerpt": "The inspected page describes the documented behavior.",
            "evidence_level": "extracted_page",
        }],
        "evidence_summary": {
            "source_count": 1,
            "extracted_page_count": 1,
            "snippet_only_count": 0,
            "unavailable_or_partial_count": 0,
            "claim_candidate_count": 1,
            "semantic_verification": "complete",
            "freshness_profile": "general",
            "freshness_policy_source": "default",
            "freshness_max_age_days": None,
            "freshness_counts": {"fresh": 1},
        },
        "quality_assessment": {
            "status": "assessed",
            "assessment_scope": "citation_integrity",
            "semantic_entailment_checked": True,
            "truth_verified": False,
            "claim_count": 1,
            "citation_coverage": 1.0,
            "uncited_claim_count": 0,
            "invalid_reference_claim_count": 0,
        },
        "semantic_verification": {
            "status": "complete",
            "semantic_entailment_checked": True,
            "factual_truth_verified": False,
            "checked_claim_count": 1,
            "unverified_claim_count": 0,
        },
        "freshness_assessment": {
            "profile": "general",
            "policy_source": "default",
            "max_age_days": None,
            "counts": {"fresh": 1},
        },
    }


def test_end_to_end_evidence_agent_revision_persistence_and_control_center(
    monkeypatch, tmp_path
):
    _use_db(monkeypatch, tmp_path)
    scope = "owner:e2e"
    memory.write_memory(
        "Oracle proposals must distinguish extracted evidence from unverified claims.",
        "fact",
        scope,
        "e2e-fixture",
    )

    # Exercise the same memory-context builder used by ai_core.chat.
    memory_messages = ai_core._messages_with_memory(
        [{"role": "user", "content": "Oracle evidence proposal"}],
        scope,
    )
    assert any("personal_memory" in str(item.get("content", "")) for item in memory_messages)

    monkeypatch.setattr(
        deep_research,
        "run_research",
        lambda query, **kwargs: _research_report(),
    )
    calls = []
    reviewer_calls = {"count": 0}

    def fake_chat(messages, **kwargs):
        role = kwargs.get("agent_role")
        prepared = ai_core._messages_with_memory(messages, kwargs.get("memory_scope"))
        calls.append({
            "role": role,
            "memory_injected": any(
                "personal_memory" in str(item.get("content", ""))
                for item in prepared
            ),
            "content": str(prepared[-1].get("content", "")),
            "system": str(prepared[0].get("content", "")),
        })

        if role == "planner" and "bounded revision planner" in str(messages[0]["content"]).lower():
            return json.dumps({
                "revisions": [{
                    "source_task_key": "draft",
                    "issue_indices": [1],
                    "instruction": "Add the missing evidence limitations to the draft.",
                    "depends_on": [],
                }]
            })
        if role == "planner":
            return json.dumps({
                "steps": [
                    {
                        "task_key": "draft",
                        "agent_role": "writer",
                        "instruction": "Write a concise proposal using the inspected evidence.",
                        "depends_on": [],
                    },
                    {
                        "task_key": "technical_review",
                        "agent_role": "coder",
                        "instruction": "Review technical feasibility and identify risks.",
                        "depends_on": ["draft"],
                    },
                ]
            })
        if role == "writer":
            if "review_issues" in calls[-1]["content"] or "previous_output_for_this_task" in calls[-1]["content"]:
                return "Revised proposal: finding [S1], with the limitation that only one source was inspected."
            return "Initial proposal: finding [S1]."
        if role == "coder":
            return "Technical review: implementation is feasible; validate deployment separately."
        if role == "reviewer":
            reviewer_calls["count"] += 1
            if reviewer_calls["count"] == 1:
                return json.dumps({
                    "decision": "needs_revision",
                    "summary": "The draft needs an explicit evidence limitation.",
                    "issues": ["The draft must state that only one source was inspected."],
                    "completed_requirements": ["Evidence was collected", "Technical review completed"],
                })
            return json.dumps({
                "decision": "accepted",
                "summary": "The revised output covers the request and states the evidence limitation.",
                "issues": [],
                "completed_requirements": ["Evidence collected", "Draft corrected", "Technical review retained"],
            })
        raise AssertionError(f"Unexpected agent role: {role}")

    monkeypatch.setattr(ai_core, "chat", fake_chat)

    graph = agent_task_execution.create_agent_graph(
        scope,
        "e2e-integrated-evidence-agent-graph",
        "Prepare a grounded technical proposal.",
        max_steps=3,
        include_evidence_research=True,
        research_max_queries=1,
        research_max_sources=1,
        research_fetch_pages=False,
        research_verify_claims=False,
    )

    tasks = durable_task_engine.list_tasks(scope, graph.graph_id, include_payload=True)
    by_key = {item["task_key"]: item for item in tasks}
    assert set(by_key) == {"evidence_research", "draft", "technical_review", "final_review"}
    assert by_key["evidence_research"]["task_type"] == "oracle.agent.evidence_research"
    assert by_key["draft"]["payload"]["dependency_keys"] == ["evidence_research"]
    assert by_key["technical_review"]["payload"]["dependency_keys"] == [
        "evidence_research", "draft"
    ]
    assert by_key["final_review"]["payload"]["dependency_keys"] == [
        "evidence_research", "draft", "technical_review"
    ]

    dispatched = agent_task_execution.dispatch_agent_tasks(
        scope, "e2e-worker", max_tasks=8, graph_id=graph.graph_id
    )
    assert len(dispatched) == 4
    assert all(item.status == "succeeded" for item in dispatched)

    initial = agent_task_execution.get_agent_graph_result(scope, graph.graph_id)
    assert initial is not None
    assert initial["status"] == "completed"
    assert initial["accepted"] is False
    assert initial["final_review"]["decision"] == "needs_revision"
    evidence_result = next(
        item for item in initial["effective_results"]
        if item["task_key"] == "evidence_research"
    )
    evidence = json.loads(evidence_result["output"])
    assert evidence["citations"][0]["id"] == "S1"
    assert evidence["sources"][0]["evidence_level"] == "extracted_page"
    assert evidence["semantic_summary"]["factual_truth_verified"] is False

    # The specialist received the evidence payload and the scope-local memory context.
    writer_call = next(item for item in calls if item["role"] == "writer")
    assert writer_call["memory_injected"] is True
    initial_review_call = next(
        item for item in calls
        if item["role"] == "reviewer" and "specialist_results" in item["content"]
    )
    initial_review_payload = json.loads(initial_review_call["content"])
    assert any(
        item["task_key"] == "evidence_research"
        for item in initial_review_payload["specialist_results"]
    )
    writer_payload = json.loads(writer_call["content"])
    assert writer_payload["dependency_results"][0]["task_key"] == "evidence_research"
    writer_evidence = json.loads(writer_payload["dependency_results"][0]["output"])
    assert writer_evidence["citations"][0]["id"] == "S1"

    revision = agent_task_execution.create_revision_graph(scope, graph.graph_id)
    revision_tasks = durable_task_engine.list_tasks(scope, revision.graph_id)
    assert {item["task_key"] for item in revision_tasks} == {"r1_draft", "final_review"}
    revision_dispatches = agent_task_execution.dispatch_agent_tasks(
        scope, "e2e-revision-worker", max_tasks=4, graph_id=revision.graph_id
    )
    revision_review_call = [
        item for item in calls
        if item["role"] == "reviewer" and "merged_specialist_results" in item["content"]
    ][-1]
    revision_review_payload = json.loads(revision_review_call["content"])
    assert any(
        item["task_key"] == "evidence_research"
        for item in revision_review_payload["merged_specialist_results"]
    )
    assert len(revision_dispatches) == 2
    assert all(item.status == "succeeded" for item in revision_dispatches)

    final = agent_task_execution.get_agent_graph_result(scope, revision.graph_id)
    assert final is not None
    assert final["accepted"] is True
    assert final["final_review"]["decision"] == "accepted"
    assert {item["task_key"] for item in final["effective_results"]} == {
        "evidence_research", "draft", "technical_review"
    }
    assert "limitation" in next(
        item["output"] for item in final["effective_results"] if item["task_key"] == "draft"
    ).lower()

    # The same persisted graph state consumed by the UI is owner-scoped and complete.
    control_center = task_control_center.get_graph_detail(scope, revision.graph_id)
    assert control_center is not None
    assert control_center["graph"]["status"] == "completed"
    assert all(item["status"] == "succeeded" for item in control_center["tasks"])
    assert task_control_center.get_graph_detail("owner:other", revision.graph_id) is None
