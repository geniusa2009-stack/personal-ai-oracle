import pytest

import db
import memory
import memory_consolidation
import memory_lifecycle


def _use_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "memory-consolidation.db"))


def _seed_three_candidate_kinds():
    duplicate_a = memory.write_memory(
        "Oracle memory stores durable project context for later retrieval",
        "fact", "owner:one", "architecture-note",
    )
    duplicate_b = memory.write_memory(
        "Oracle memory stores durable project context for later retrieval across sessions",
        "fact", "owner:one", "meeting-note",
    )
    conflict_a = memory.write_memory(
        "AgriSmart uses 3 soil sensors in the field",
        "fact", "owner:one", "design-v1",
    )
    conflict_b = memory.write_memory(
        "AgriSmart uses 5 soil sensors in the field",
        "fact", "owner:one", "design-v2",
    )
    related_a = memory.write_memory(
        "ChessMaster lesson tracks student mastery progress",
        "fact", "owner:one", "learning-note",
    )
    related_b = memory.write_memory(
        "ChessMaster assessment tracks student mastery progress",
        "fact", "owner:one", "assessment-note",
    )
    return duplicate_a, duplicate_b, conflict_a, conflict_b, related_a, related_b


def test_scan_creates_duplicate_contradiction_and_related_review_proposals_without_mutating_memories(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    originals = _seed_three_candidate_kinds()
    before = [memory.get_memory(item.id, "owner:one") for item in originals]

    run = memory_consolidation.scan_scope("owner:one")
    proposals = memory_consolidation.list_proposals("owner:one")

    assert run.status == "completed"
    assert run.scanned_count == 6
    assert run.comparison_count > 0
    assert run.proposal_count == len(proposals)
    assert {item.proposal_type for item in proposals} >= {
        "potential_duplicate", "potential_contradiction", "related"
    }
    assert all(item.status == "pending_review" for item in proposals)
    assert all(len(item.member_ids) == 2 for item in proposals)
    assert all(len(item.members) == 2 for item in proposals)
    assert all(len(item.member_content_hashes[0]) == 64 for item in proposals)
    assert [memory.get_memory(item.id, "owner:one") for item in originals] == before

    contradiction = next(item for item in proposals if item.proposal_type == "potential_contradiction")
    assert "numeric_values_differ" in contradiction.signals["conflict_signals"]
    assert "review signal" in contradiction.explanation


def test_scan_is_scope_isolated_and_idempotently_updates_observation_count(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    first = memory.write_memory(
        "ChessMaster lesson tracks student mastery progress",
        "fact", "owner:one", "manual",
    )
    second = memory.write_memory(
        "ChessMaster assessment tracks student mastery progress",
        "fact", "owner:one", "manual",
    )
    memory.write_memory(
        "ChessMaster lesson tracks student mastery progress",
        "fact", "owner:two", "private",
    )
    memory.write_memory(
        "ChessMaster assessment tracks student mastery progress",
        "fact", "owner:two", "private",
    )

    first_run = memory_consolidation.scan_scope("owner:one")
    first_proposals = memory_consolidation.list_proposals("owner:one")
    second_run = memory_consolidation.scan_scope("owner:one")
    second_proposals = memory_consolidation.list_proposals("owner:one")

    assert first_run.run_id != second_run.run_id
    assert first_run.proposal_count >= 1
    assert {item.id for item in first_proposals} == {item.id for item in second_proposals}
    assert all(item.observation_count == 2 for item in second_proposals)
    assert all(item.scope == "owner:one" for item in second_proposals)
    assert all(first.id in item.member_ids or second.id in item.member_ids for item in second_proposals)
    assert memory_consolidation.list_proposals("owner:two") == []


def test_proposal_review_accepts_or_dismisses_without_changing_memory_content(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    original_a = memory.write_memory(
        "Oracle memory stores durable project context for later retrieval",
        "fact", "owner:one", "manual",
    )
    original_b = memory.write_memory(
        "Oracle memory stores durable project context for later retrieval across sessions",
        "fact", "owner:one", "manual",
    )
    memory_consolidation.scan_scope("owner:one")
    proposals = memory_consolidation.list_proposals(
        "owner:one", proposal_type="potential_duplicate"
    )
    assert proposals

    reviewed = memory_consolidation.review_proposal(
        "owner:one",
        proposals[0].id,
        decision="accepted",
        reviewer="owner",
        reason="Reviewed both sources; keep both until a separate manual resolution",
    )

    assert reviewed.status == "accepted"
    assert reviewed.reviewer == "owner"
    assert reviewed.review_reason.startswith("Reviewed both sources")
    assert memory.get_memory(original_a.id, "owner:one") == original_a
    assert memory.get_memory(original_b.id, "owner:one") == original_b
    assert memory_consolidation.list_proposals("owner:one", status="accepted") == [reviewed]

    with pytest.raises(memory_consolidation.MemoryConsolidationError):
        memory_consolidation.review_proposal(
            "owner:two",
            proposals[0].id,
            decision="dismissed",
            reviewer="owner",
            reason="Wrong scope",
        )


def test_review_marks_a_proposal_stale_after_a_source_memory_is_superseded(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    original_a = memory.write_memory(
        "Oracle project stores durable records in SQLite",
        "fact", "owner:one", "manual",
    )
    memory.write_memory(
        "Oracle project stores durable records in a SQLite database",
        "fact", "owner:one", "manual",
    )
    memory_consolidation.scan_scope("owner:one")
    proposal = next(
        item for item in memory_consolidation.list_proposals("owner:one")
        if original_a.id in item.member_ids
    )

    memory_lifecycle.revise_memory(
        original_a.id,
        "owner:one",
        "Oracle project stores durable records in PostgreSQL",
        reason="The architecture decision changed",
        source="owner-confirmed",
    )
    reviewed = memory_consolidation.review_proposal(
        "owner:one",
        proposal.id,
        decision="accepted",
        reviewer="owner",
        reason="Review after change",
    )

    assert reviewed.status == "stale"
    assert original_a.id in reviewed.stale_member_ids
    assert memory.get_memory(original_a.id, "owner:one") == original_a


def test_scan_is_bounded_and_reports_partial_runs(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    for i in range(6):
        memory.write_memory(
            f"Project Atlas stores durable context record number {i}",
            "fact", "owner:one", "manual",
        )

    run = memory_consolidation.scan_scope(
        "owner:one",
        candidate_limit=6,
        max_pair_checks=2,
        max_proposals=20,
    )

    assert run.status == "partial"
    assert run.truncated is True
    assert run.comparison_count == 2
    assert memory_consolidation.get_run("owner:one", run.run_id) == run


def test_invalid_scan_and_review_arguments_are_rejected(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    with pytest.raises(memory_consolidation.MemoryConsolidationError):
        memory_consolidation.scan_scope("owner:one", candidate_limit=True)
    with pytest.raises(memory_consolidation.MemoryConsolidationError):
        memory_consolidation.scan_scope("owner:one", duplicate_threshold=float("nan"))
    with pytest.raises(memory_consolidation.MemoryConsolidationError):
        memory_consolidation.scan_scope("owner:one", related_threshold=0.9, duplicate_threshold=0.8)
    with pytest.raises(memory_consolidation.MemoryConsolidationError):
        memory_consolidation.review_proposal(
            "owner:one", 1, decision="merge", reviewer="owner", reason="not supported"
        )


def test_explicit_memory_deletion_cleans_proposals_that_reference_it(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    first = memory.write_memory(
        "Oracle memory stores durable project context for later retrieval",
        "fact", "owner:one", "manual",
    )
    memory.write_memory(
        "Oracle memory stores durable project context for later retrieval across sessions",
        "fact", "owner:one", "manual",
    )
    memory_consolidation.scan_scope("owner:one")
    assert memory_consolidation.list_proposals("owner:one")

    assert memory.delete_memory(first.id, "owner:one") is True
    assert memory_consolidation.list_proposals("owner:one") == []

    conn = db.get_conn()
    try:
        assert conn.execute(
            "SELECT COUNT(*) AS c FROM memory_consolidation_proposal_members WHERE memory_id=?",
            (first.id,),
        ).fetchone()["c"] == 0
        assert conn.execute(
            "SELECT COUNT(*) AS c FROM memory_consolidation_observations"
        ).fetchone()["c"] == 0
    finally:
        conn.close()
