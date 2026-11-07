import pytest

import db
import memory


def _use_test_database(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "memory-retrieval.db"))


def test_retrieve_memories_ranks_relevant_items_and_respects_scope(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    relevant = memory.write_memory(
        "Prefers concise Egyptian Arabic responses",
        "preference",
        "user:owner",
        "manual",
    )
    irrelevant = memory.write_memory(
        "Wants to learn astronomy and telescope operation",
        "goal",
        "user:owner",
        "manual",
    )
    private = memory.write_memory(
        "Builds an AI project using Python and agents",
        "fact",
        "user:other",
        "manual",
    )

    found = memory.retrieve_memories(
        "user:owner",
        "Help me write a concise answer in Egyptian Arabic",
        limit=5,
    )

    assert [item.id for item in found] == [relevant.id]
    assert irrelevant.id not in [item.id for item in found]
    assert private.id not in [item.id for item in found]


def test_retrieve_memories_uses_recent_preferences_when_query_has_no_terms(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    preference = memory.write_memory(
        "Prefers short answers",
        "preference",
        "user:owner",
        "manual",
    )
    memory.write_memory(
        "Lives near the central library",
        "fact",
        "user:owner",
        "manual",
    )

    found = memory.retrieve_memories("user:owner", "في و من", limit=8)

    assert preference.id in [item.id for item in found]
    assert all(item.memory_type in {"preference", "goal"} for item in found)


def test_retrieve_memories_validates_limits_and_query_type(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)

    for kwargs in ({"limit": 0}, {"limit": 51}, {"candidate_limit": 0}):
        with pytest.raises(memory.MemoryValidationError):
            memory.retrieve_memories("user:owner", "AI", **kwargs)

    with pytest.raises(memory.MemoryValidationError):
        memory.retrieve_memories("user:owner", None)
