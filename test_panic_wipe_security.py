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

    assert db.list_entries(limit=10)[0]["text"] == "private entry"


def test_panic_wipe_empty_selection_is_a_noop(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    db.save_entry("private entry", ["test"])

    assert database.panic_wipe([]) == {}
    assert len(db.list_entries(limit=10)) == 1


def test_panic_wipe_deletes_only_selected_allowlisted_tables(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    db.save_entry("private entry", ["test"])
    database.save_content("type", "topic", "generated")

    result = database.panic_wipe(["entries"])

    assert result == {"entries": 1}
    assert db.list_entries(limit=10) == []
    assert len(database.list_content(limit=10)) == 1
