from datetime import datetime, timedelta, timezone

import pytest

import db
import memory
import memory_lifecycle


def _use_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "memory-lifecycle.db"))


def _memory(text="Oracle stores project notes", scope="owner:one"):
    return memory.write_memory(text, "fact", scope, "manual")


def test_new_memory_gets_default_metadata_and_created_revision(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    record = _memory()

    metadata = memory_lifecycle.get_memory_metadata(record.id, "owner:one")
    history = memory_lifecycle.get_memory_revision_history(record.id, "owner:one")

    assert metadata is not None
    assert metadata.confidence == 0.5
    assert metadata.importance == 0.5
    assert metadata.status == "active"
    assert metadata.access_count == 0
    assert metadata.valid_from is not None
    assert len(history) == 1
    assert history[0].revision_kind == "created"
    assert history[0].actor == "manual"
    assert len(history[0].content_hash) == 64


def test_metadata_updates_are_scope_isolated_and_append_revision_snapshots(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    record = _memory()
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=30)

    updated = memory_lifecycle.set_memory_metadata(
        record.id,
        "owner:one",
        confidence=0.9,
        importance=0.8,
        valid_until=expires,
        reason="Confirmed from a primary project document",
        actor="owner-confirmed",
    )
    history = memory_lifecycle.get_memory_revision_history(record.id, "owner:one")

    assert updated.confidence == pytest.approx(0.9)
    assert updated.importance == pytest.approx(0.8)
    assert updated.valid_until is not None
    assert history[0].revision_kind == "metadata_updated"
    assert history[0].reason == "Confirmed from a primary project document"
    assert history[0].metadata["confidence"] == pytest.approx(0.9)
    assert history[1].revision_kind == "created"
    assert memory_lifecycle.get_memory_metadata(record.id, "owner:two") is None


def test_metadata_validation_rejects_invalid_scores_and_time_ranges(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    record = _memory()
    past = datetime.now(timezone.utc) - timedelta(days=2)
    future = datetime.now(timezone.utc) + timedelta(days=2)

    with pytest.raises(memory_lifecycle.MemoryLifecycleError):
        memory_lifecycle.set_memory_metadata(
            record.id, "owner:one", confidence=1.2, reason="invalid"
        )
    with pytest.raises(memory_lifecycle.MemoryLifecycleError):
        memory_lifecycle.set_memory_metadata(
            record.id, "owner:one", importance=True, reason="invalid"
        )
    with pytest.raises(memory_lifecycle.MemoryLifecycleError):
        memory_lifecycle.set_memory_metadata(
            record.id, "owner:one", valid_from=future, valid_until=past, reason="invalid range"
        )


def test_retrieval_excludes_future_and_expired_memories(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    expired = _memory("Oracle project uses a SQLite database")
    future = _memory("Oracle project uses a PostgreSQL database")
    now = datetime.now(timezone.utc)

    memory_lifecycle.set_memory_metadata(
        expired.id,
        "owner:one",
        valid_until=now - timedelta(days=1),
        reason="This information is no longer valid",
    )
    memory_lifecycle.set_memory_metadata(
        future.id,
        "owner:one",
        valid_from=now + timedelta(days=1),
        reason="This policy becomes valid later",
    )

    assert memory.retrieve_memories("owner:one", "Oracle project database") == []


def test_confidence_and_importance_weight_retrieval_ranking(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    low = _memory("Apollo mission records use a PostgreSQL database")
    high = _memory("Apollo mission records use a SQLite database")

    memory_lifecycle.set_memory_metadata(
        high.id,
        "owner:one",
        confidence=1.0,
        importance=1.0,
        reason="Confirmed and highly important project decision",
    )

    results = memory.retrieve_memories(
        "owner:one", "Apollo mission records database", limit=1
    )

    assert results == [high]
    assert low.id != high.id


def test_revision_preserves_old_content_and_supersedes_it_for_retrieval(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    original = _memory("Oracle project stores its records in SQLite")

    revised = memory_lifecycle.revise_memory(
        original.id,
        "owner:one",
        "Oracle project stores its records in PostgreSQL",
        reason="The persistence decision changed after an architecture review",
        source="owner-confirmed",
        confidence=0.95,
        importance=0.9,
    )

    assert memory.get_memory(original.id, "owner:one") == original
    assert revised.id != original.id
    assert revised.content.endswith("PostgreSQL")
    assert memory_lifecycle.get_memory_metadata(original.id, "owner:one").status == "superseded"
    assert memory_lifecycle.get_memory_metadata(original.id, "owner:one").superseded_by_id == revised.id
    assert memory_lifecycle.get_memory_metadata(revised.id, "owner:one").status == "active"
    assert memory.list_memories("owner:one") == [revised]
    assert {item.id for item in memory.list_memories("owner:one", include_superseded=True)} == {
        original.id, revised.id
    }
    assert memory.retrieve_memories("owner:one", "Oracle project PostgreSQL") == [revised]

    old_history = memory_lifecycle.get_memory_revision_history(original.id, "owner:one")
    new_history = memory_lifecycle.get_memory_revision_history(revised.id, "owner:one")
    assert [entry.revision_kind for entry in old_history] == ["superseded", "created"]
    assert new_history[0].revision_kind == "created"
    assert new_history[0].actor == "owner-confirmed"


def test_revision_rejects_cross_scope_unknown_and_unchanged_content(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    original = _memory()

    with pytest.raises(memory_lifecycle.MemoryLifecycleError):
        memory_lifecycle.revise_memory(
            original.id, "owner:two", "Private replacement", reason="wrong scope", source="manual"
        )
    with pytest.raises(memory_lifecycle.MemoryLifecycleError):
        memory_lifecycle.revise_memory(
            original.id, "owner:one", original.content, reason="same content", source="manual"
        )
    with pytest.raises(memory_lifecycle.MemoryLifecycleError):
        memory_lifecycle.revise_memory(
            99999, "owner:one", "New version", reason="unknown id", source="manual"
        )


def test_retrieval_increments_access_statistics_without_revision_noise(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    record = _memory("Oracle project depends on SQLite database")
    before = memory_lifecycle.get_memory_revision_history(record.id, "owner:one")

    assert memory.retrieve_memories("owner:one", "Oracle project SQLite database") == [record]
    metadata = memory_lifecycle.get_memory_metadata(record.id, "owner:one")
    after = memory_lifecycle.get_memory_revision_history(record.id, "owner:one")

    assert metadata.access_count == 1
    assert metadata.last_accessed_at is not None
    assert len(after) == len(before)
