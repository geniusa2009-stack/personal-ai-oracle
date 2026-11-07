import pytest

import db
import database


def _use_test_database(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "panic-wipe.db"))
    db.init_db()
    database.init_database()


def test_panic_wipe_rejects_untrusted_table_names_without_deleting(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    db.save_entry("private entry", ["test"])

    with pytest.raises(ValueError):
        database.panic_wipe(["entries; DROP TABLE settings;--"])

    conn = db.get_conn()
    try:
        assert conn.execute("SELECT text FROM entries").fetchone()["text"] == "private entry"
        assert conn.execute("SELECT 1 FROM settings LIMIT 1").fetchone() is None
    finally:
        conn.close()


def test_panic_wipe_empty_selection_is_a_noop(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    db.save_entry("private entry", ["test"])

    assert database.panic_wipe([]) == {}
    conn = db.get_conn()
    try:
        assert conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0] == 1
    finally:
        conn.close()


def test_panic_wipe_deletes_only_selected_allowlisted_tables(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    db.save_entry("private entry", ["test"])
    database.save_content("type", "topic", "generated")

    result = database.panic_wipe(["entries"])

    assert result == {"entries": 1}
    conn = db.get_conn()
    try:
        assert conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0] == 0
    finally:
        conn.close()
    assert len(database.list_content(limit=10)) == 1


def test_panic_wipe_rejects_non_string_table_names(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        database.panic_wipe(["entries", {"table": "settings"}])
