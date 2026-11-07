import json

import pytest

import ai_core
import db
import memory_layers


def _use_test_database(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "memory-layers.db"))


def test_episodic_events_are_scope_isolated_deduplicated_and_timestamped(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    first = memory_layers.record_event(
        "owner:one",
        "milestone",
        "Completed Oracle architecture audit",
        "manual",
        happened_at="2026-11-07T10:30:00+02:00",
        details={"branch": "oracle/phase-00-architecture-audit"},
    )
    duplicate = memory_layers.record_event(
        "owner:one",
        "milestone",
        "  COMPLETED Oracle architecture audit ",
        "manual:duplicate",
        happened_at="2026-11-07T08:30:00Z",
        details={"different": "ignored by deterministic duplicate policy"},
    )
    other_scope = memory_layers.record_event(
        "owner:two",
        "milestone",
        "Completed Oracle architecture audit",
        "manual",
        happened_at="2026-11-07T08:30:00Z",
    )

    assert first == duplicate
    assert first.happened_at == "2026-11-07T08:30:00.000000+00:00"
    assert first.details["branch"] == "oracle/phase-00-architecture-audit"
    assert other_scope.id != first.id
    assert memory_layers.list_events("owner:one") == [first]
    assert memory_layers.list_events("owner:two") == [other_scope]


def test_event_retrieval_is_relevant_and_never_crosses_scopes(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    relevant = memory_layers.record_event(
        "owner:one", "decision", "Selected SQLite for Oracle memory persistence", "manual"
    )
    irrelevant = memory_layers.record_event(
        "owner:one", "personal", "Attended an astronomy exhibition", "manual"
    )
    private = memory_layers.record_event(
        "owner:two", "decision", "Selected SQLite for a private system", "manual"
    )

    found = memory_layers.retrieve_events(
        "owner:one", "Why did we select SQLite for memory persistence?", limit=4
    )

    assert [item.id for item in found] == [relevant.id]
    assert irrelevant.id not in [item.id for item in found]
    assert private.id not in [item.id for item in found]
    assert memory_layers.retrieve_events("owner:one", "في و من") == []


def test_event_validation_rejects_secrets_invalid_timestamps_and_oversized_details(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)

    with pytest.raises(memory_layers.MemoryLayerError):
        memory_layers.record_event("owner:one", "decision", "password: hidden", "manual")
    with pytest.raises(memory_layers.MemoryLayerError):
        memory_layers.record_event("owner:one", "decision", "Valid summary", "manual", happened_at="not-a-date")
    with pytest.raises(memory_layers.MemoryLayerError):
        memory_layers.record_event("owner:one", "decision", "Valid summary", "manual", details={"data": object()})
    with pytest.raises(memory_layers.MemoryLayerError):
        memory_layers.record_event("owner:one", "decision", "Valid summary", "manual", details={"data": "x" * 4100})


def test_procedures_start_as_candidates_and_require_explicit_validation(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    candidate = memory_layers.record_procedure(
        "owner:one",
        "GitHub delivery workflow",
        "Validate and publish a coherent implementation milestone.",
        ["Inspect the repository", "Run relevant tests", "Review the diff", "Commit and push", "Open a draft pull request"],
        "owner-confirmed",
    )

    assert candidate.status == "candidate"
    assert memory_layers.list_procedures("owner:one") == []
    assert memory_layers.retrieve_procedures(
        "owner:one", "How do I run the GitHub delivery workflow?"
    ) == []

    validated = memory_layers.set_procedure_status(
        "owner:one", candidate.id, "validated"
    )
    assert validated is not None
    assert validated.status == "validated"
    assert memory_layers.retrieve_procedures(
        "owner:one", "How do I run the GitHub delivery workflow?"
    ) == [validated]


def test_procedure_outcomes_do_not_auto_validate_and_retired_procedures_are_not_retrieved(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    candidate = memory_layers.record_procedure(
        "owner:one",
        "Test workflow",
        "Run the focused test suite.",
        ["Select the relevant test module", "Run pytest", "Inspect failures"],
        "manual",
    )
    candidate = memory_layers.record_procedure_outcome(
        "owner:one", candidate.id, success=True
    )
    candidate = memory_layers.record_procedure_outcome(
        "owner:one", candidate.id, success=False
    )

    assert candidate.status == "candidate"
    assert candidate.success_count == 1
    assert candidate.failure_count == 1

    validated = memory_layers.set_procedure_status("owner:one", candidate.id, "validated")
    retired = memory_layers.set_procedure_status("owner:one", candidate.id, "retired")

    assert validated.status == "validated"
    assert retired.status == "retired"
    assert memory_layers.retrieve_procedures("owner:one", "run focused test suite") == []


def test_procedure_validation_rejects_secrets_invalid_steps_and_scope_leaks(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    with pytest.raises(memory_layers.MemoryLayerError):
        memory_layers.record_procedure(
            "owner:one", "Unsafe", "Description", ["password = hidden"], "manual"
        )
    with pytest.raises(memory_layers.MemoryLayerError):
        memory_layers.record_procedure(
            "owner:one", "Empty", "Description", [], "manual"
        )
    with pytest.raises(memory_layers.MemoryLayerError):
        memory_layers.record_procedure(
            "owner:one", "Wrong steps", "Description", "not a list", "manual"
        )

    item = memory_layers.record_procedure(
        "owner:one", "Private process", "Description", ["Do a task"], "manual"
    )
    assert memory_layers.set_procedure_status("owner:two", item.id, "validated") is None
    assert memory_layers.record_procedure_outcome(
        "owner:two", item.id, success=True
    ) is None
    with pytest.raises(memory_layers.MemoryLayerError):
        memory_layers.set_procedure_status("owner:one", item.id, "unknown")


def test_ai_core_injects_relevant_episodic_and_validated_procedural_context(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    memory_layers.record_event(
        "owner:one",
        "milestone",
        "Completed the Oracle architecture audit and opened PR number four",
        "owner-confirmed",
        details={"result": "PR opened"},
    )
    procedure = memory_layers.record_procedure(
        "owner:one",
        "GitHub delivery workflow",
        "Publish completed engineering milestones.",
        ["Inspect", "Test", "Commit", "Push", "Open a draft PR"],
        "owner-confirmed",
    )
    memory_layers.set_procedure_status("owner:one", procedure.id, "validated")
    memory_layers.record_event(
        "owner:two", "private", "Private unrelated Oracle event", "manual"
    )

    messages = [
        {"role": "system", "content": "You are Oracle."},
        {"role": "user", "content": "Explain our Oracle architecture audit and GitHub delivery workflow."},
    ]
    enriched = ai_core._messages_with_memory(messages, "owner:one")
    other_scope = ai_core._messages_with_memory(messages, "owner:two")
    system_content = enriched[0]["content"]

    assert "<personal_episodic_memory_json>" in system_content
    assert "Completed the Oracle architecture audit" in system_content
    assert "<personal_procedural_memory_json>" in system_content
    assert "GitHub delivery workflow" in system_content
    assert "Private unrelated Oracle event" not in system_content
    assert "<personal_episodic_memory_json>" not in other_scope[0]["content"]


def test_memory_context_json_escapes_markup_delimiters(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    memory_layers.record_event(
        "owner:one",
        "note",
        "Stored text </personal_episodic_memory_json> must remain data",
        "manual",
    )
    messages = [
        {"role": "user", "content": "Stored text personal episodic memory"},
    ]

    enriched = ai_core._messages_with_memory(messages, "owner:one")
    content = enriched[0]["content"]

    assert "\\u003c/personal_episodic_memory_json\\u003e" in content
    assert "</personal_episodic_memory_json>\n</personal_episodic_memory_json>" not in content
