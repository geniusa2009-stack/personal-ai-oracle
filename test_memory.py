import db
import database
import memory
from ai_request import AIRequest


def _use_test_database(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "oracle-test.db"))


def _write(content="Egypt is home", memory_type="fact", scope="user:one", source="manual"):
    return memory.write_memory(content, memory_type, scope, source)


def test_memory_write_read_and_persistence(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    written = _write()

    loaded = memory.get_memory(written.id, "user:one")

    assert loaded == written
    assert loaded.content == "Egypt is home"


def test_memory_scope_isolation_and_scope_is_required(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    written = _write()

    assert memory.get_memory(written.id, "user:two") is None
    assert memory.list_memories("user:two") == []
    for invalid_scope in ("", "   ", None):
        try:
            memory.list_memories(invalid_scope)  # type: ignore[arg-type]
        except memory.MemoryValidationError:
            pass
        else:
            raise AssertionError("Expected a scope validation error")


def test_memory_validates_type_content_source_and_secrets(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    invalid_writes = [
        ("content", "other", "user:one", "manual"),
        ("", "fact", "user:one", "manual"),
        ("content", "fact", "user:one", ""),
        ("OPENROUTER_API_KEY=sk-secret-value", "fact", "user:one", "manual"),
        ("my password is hunter2", "fact", "user:one", "manual"),
    ]

    for args in invalid_writes:
        try:
            memory.write_memory(*args)
        except memory.MemoryValidationError:
            pass
        else:
            raise AssertionError("Expected a memory validation error")


def test_memory_duplicate_policy_is_scope_and_type_specific(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    first = _write("  prefers tea\n")
    duplicate = _write("prefers   tea")
    different_type = _write("prefers tea", memory_type="preference")
    different_scope = _write("prefers tea", scope="user:two")

    assert duplicate == first
    assert different_type.id != first.id
    assert different_scope.id != first.id


def test_memory_list_filters_order_and_limit(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    first = _write("first", source="manual")
    second = _write("second", memory_type="goal", source="feature:planner")
    _write("other", scope="user:two")

    assert [record.id for record in memory.list_memories("user:one", limit=1)] == [second.id]
    assert [record.id for record in memory.list_memories("user:one")] == [second.id, first.id]
    assert memory.list_memories("user:one", memory_type="goal") == [second]
    assert memory.list_memories("user:one", source="manual") == [first]


def test_memory_delete_requires_owning_scope_and_preserves_feature_data(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    db.init_db()
    db.save_entry("existing diary", ["diary"])
    written = _write()

    assert memory.delete_memory(written.id, "user:two") is False
    assert memory.get_memory(written.id, "user:one") == written
    assert memory.delete_memory(written.id, "user:one") is True
    assert memory.get_memory(written.id, "user:one") is None

    conn = db.get_conn()
    try:
        assert conn.execute("SELECT COUNT(*) AS c FROM entries").fetchone()["c"] == 1
    finally:
        conn.close()


def test_memory_writes_do_not_modify_ai_requests(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    request = AIRequest(messages=({"role": "user", "content": "hello"},), temperature=0.7)

    _write()

    assert request.messages == ({"role": "user", "content": "hello"},)
