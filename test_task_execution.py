from cryptography.fernet import Fernet
import pytest

import db
import deep_research
import durable_task_engine as engine
import task_execution


def _use_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "explicit-task-execution.db"))
    monkeypatch.setenv(
        "ORACLE_CHECKPOINT_ENCRYPTION_KEY",
        Fernet.generate_key().decode("ascii"),
    )


def _report(status="success"):
    return {
        "status": status,
        "query": "How does the example work?",
        "answer": "A concise evidence-grounded answer. [S1]",
        "key_findings": ["Finding one", "Finding two"],
        "limitations": [],
        "citations": [{
            "id": "S1",
            "title": "Official documentation",
            "url": "https://example.org/docs",
            "domain": "example.org",
            "publisher": "Example",
            "published_at": "2026-11-01",
            "updated_at": None,
        }],
        "sources": [{
            "citation_id": "S1",
            "title": "Official documentation",
            "domain": "example.org",
            "page_status": "extracted",
            "evidence_excerpt": "A short excerpt from the inspected page.",
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
            "semantic_entailment_checked": False,
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
        "private_internal_field": "must-not-be-stored",
    }


def _create(scope="owner:one", key="research-one", query="How does the example work?"):
    return task_execution.create_research_graph(
        scope,
        key,
        query,
        max_queries=2,
        max_sources=4,
        fetch_pages=False,
        verify_claims=True,
        freshness_profile="general",
    )


def test_create_research_graph_is_encrypted_scoped_and_idempotent(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)

    first = _create()
    second = _create()

    assert first.graph_id == second.graph_id
    assert first.task_count == 1
    assert first.status == "active"
    tasks = engine.list_tasks("owner:one", first.graph_id, include_payload=True)
    assert len(tasks) == 1
    assert tasks[0]["task_type"] == task_execution.TASK_TYPE_RESEARCH
    assert tasks[0]["payload"]["query"] == "How does the example work?"
    assert engine.list_graphs("owner:two") == []


def test_submission_rejects_invalid_query_options_and_profile(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)

    with pytest.raises(task_execution.TaskExecutionError):
        _create(query="   ")
    with pytest.raises(task_execution.TaskExecutionError):
        task_execution.create_research_graph(
            "owner:one", "bad-max", "valid query", max_queries=True
        )
    with pytest.raises(task_execution.TaskExecutionError):
        task_execution.create_research_graph(
            "owner:one", "bad-bool", "valid query", fetch_pages="yes"
        )
    with pytest.raises(task_execution.TaskExecutionError):
        task_execution.create_research_graph(
            "owner:one", "bad-profile", "valid query", freshness_profile="made_up"
        )


def test_research_dispatch_runs_one_allowlisted_handler_and_exposes_safe_result(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    graph = _create()
    calls = []

    def fake_research(query, **kwargs):
        calls.append((query, kwargs))
        return _report()

    monkeypatch.setattr(deep_research, "run_research", fake_research)

    dispatched = task_execution.dispatch_research_once(
        "owner:one", "manual-control-center"
    )

    assert dispatched is not None
    assert dispatched.status == "succeeded"
    assert dispatched.task_type == task_execution.TASK_TYPE_RESEARCH
    assert len(calls) == 1
    assert calls[0][0] == "How does the example work?"
    assert calls[0][1]["memory_scope"] == "owner:one"
    assert calls[0][1]["max_correction_retries"] == 1
    assert engine.get_graph("owner:one", graph.graph_id).status == "completed"

    preview = task_execution.get_research_result("owner:one", dispatched.task_id)
    assert preview is not None
    assert preview["answer"].startswith("A concise evidence-grounded answer")
    assert preview["citations"][0]["url"] == "https://example.org/docs"
    assert preview["semantic_summary"]["factual_truth_verified"] is False
    assert "private_internal_field" not in repr(preview)
    assert task_execution.get_research_result("owner:two", dispatched.task_id) is None


def test_research_with_no_sources_fails_without_retry_or_message_leak(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    graph = _create(key="research-no-sources")
    monkeypatch.setattr(
        deep_research,
        "run_research",
        lambda *_args, **_kwargs: _report(status="error"),
    )

    dispatched = task_execution.dispatch_research_once(
        "owner:one", "manual-control-center"
    )

    assert dispatched is not None
    assert dispatched.status == "failed"
    assert dispatched.error_code == "ResearchTaskFailed"
    task = engine.list_tasks("owner:one", graph.graph_id)[0]
    assert task["attempt_count"] == 1
    attempts = engine.list_attempts("owner:one", task["task_id"])
    assert attempts[0]["error_code"] == "ResearchTaskFailed"
    assert "no usable sources" not in repr(attempts)


def test_unknown_payload_fields_fail_closed(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    graph = engine.create_graph(
        "owner:one",
        "research-unknown-field",
        [engine.TaskSpec(
            task_key="research",
            task_type=task_execution.TASK_TYPE_RESEARCH,
            payload={
                "query": "valid query",
                "max_queries": 1,
                "max_sources": 2,
                "fetch_pages": False,
                "verify_claims": False,
                "freshness_profile": None,
                "unexpected": "must-not-be-accepted",
            },
        )],
    )
    monkeypatch.setattr(deep_research, "run_research", lambda *_a, **_k: pytest.fail("must not call research"))

    dispatched = task_execution.dispatch_research_once(
        "owner:one", "manual-control-center"
    )

    assert dispatched is not None
    assert dispatched.status == "failed"
    assert dispatched.error_code == "TaskExecutionError"
    assert engine.get_graph("owner:one", graph.graph_id).status == "failed"


def test_dispatch_returns_none_when_no_registered_research_task_is_queued(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    result = task_execution.dispatch_research_once(
        "owner:one", "manual-control-center"
    )
    assert result is None


def test_same_idempotency_key_cannot_be_reused_for_different_research(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    _create(key="same-key")
    with pytest.raises(engine.TaskIdempotencyConflict):
        _create(key="same-key", query="A different question")


def test_result_preview_revalidates_urls_and_summary_allowlists(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    graph = engine.create_graph(
        "owner:one",
        "research-result-projection",
        [engine.TaskSpec(
            task_key="research",
            task_type=task_execution.TASK_TYPE_RESEARCH,
            payload={"query": "safe query"},
        )],
    )
    lease = engine.claim_next("owner:one", "manual-control-center")
    assert lease is not None
    engine.start_task("owner:one", lease.task_id, lease.worker_id, lease.lease_token)
    engine.complete_task(
        "owner:one",
        lease.task_id,
        lease.worker_id,
        lease.lease_token,
        {
            "kind": "research_report",
            "status": "success",
            "query": "safe query",
            "answer": "Safe answer",
            "key_findings": "not-a-list",
            "limitations": [],
            "citations": [
                {"id": "S0", "title": "Unsafe", "url": "javascript:alert(1)", "domain": "bad"},
                {"id": "S1", "title": "Safe", "url": "https://example.org", "domain": "example.org"},
            ],
            "evidence_summary": {"source_count": 1, "private_secret": "never-render"},
            "quality_summary": {"truth_verified": False, "private_prompt": "never-render"},
            "semantic_summary": {
                "status": "complete",
                "factual_truth_verified": True,
                "private_value": "never-render",
            },
            "freshness_summary": {
                "profile": "general",
                "counts": {"fresh": 1},
                "private_value": "never-render",
            },
            "unexpected_result_field": "never-render",
        },
    )

    preview = task_execution.get_research_result("owner:one", lease.task_id)

    assert preview is not None
    assert preview["key_findings"] == []
    assert [item["id"] for item in preview["citations"]] == ["S1"]
    assert preview["semantic_summary"]["factual_truth_verified"] is False
    assert "private_secret" not in repr(preview)
    assert "private_prompt" not in repr(preview)
    assert "unexpected_result_field" not in repr(preview)
    assert engine.get_graph("owner:one", graph.graph_id).status == "completed"
