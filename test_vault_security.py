import base64

import pytest
from cryptography.fernet import Fernet

import database
import db


def _use_test_database(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "oracle-vault-test.db"))
    db.init_db()
    database.init_database()


def test_vault_refuses_to_store_without_external_key(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    monkeypatch.delenv("ORACLE_VAULT_KEY", raising=False)

    with pytest.raises(database.VaultConfigurationError):
        database.add_vault_entry("email", "owner", "do-not-store-plaintext")

    assert database.list_vault(reveal=False) == []


def test_vault_encrypts_with_external_key_not_database_setting(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("ORACLE_VAULT_KEY", key)

    record_id = database.add_vault_entry("email", "owner", "a-unique-secret")
    visible = database.list_vault(reveal=True)

    conn = db.get_conn()
    try:
        stored = conn.execute(
            "SELECT secret_enc FROM password_vault WHERE id = ?", (record_id,)
        ).fetchone()["secret_enc"]
        saved_key = conn.execute(
            "SELECT value FROM settings WHERE key = 'vault_key'"
        ).fetchone()
    finally:
        conn.close()

    assert visible[0]["secret"] == "a-unique-secret"
    assert stored.startswith("f:")
    assert "a-unique-secret" not in stored
    assert saved_key is None


def test_vault_does_not_reveal_encrypted_records_without_external_key(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    key = Fernet.generate_key()
    monkeypatch.setenv("ORACLE_VAULT_KEY", key.decode("ascii"))
    database.add_vault_entry("email", "owner", "secret-value")
    monkeypatch.delenv("ORACLE_VAULT_KEY")

    assert "اضبط ORACLE_VAULT_KEY" in database.list_vault(reveal=True)[0]["secret"]


def test_legacy_database_key_and_base64_rows_are_migrated(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    legacy_key = Fernet.generate_key()
    legacy_cipher = Fernet(legacy_key).encrypt(b"old-fernet-secret").decode("ascii")
    new_key = Fernet.generate_key().decode("ascii")
    legacy_base64 = base64.b64encode(b"old-base64-secret").decode("ascii")

    db.set_setting("vault_key", legacy_key.decode("ascii"))
    conn = db.get_conn()
    try:
        conn.execute(
            "INSERT INTO password_vault(label, username, secret_enc, created_at) "
            "VALUES(?,?,?,?)",
            ("old-fernet", "owner", "f:" + legacy_cipher, "2026-01-01T00:00:00"),
        )
        conn.execute(
            "INSERT INTO password_vault(label, username, secret_enc, created_at) "
            "VALUES(?,?,?,?)",
            ("old-base64", "owner", "b:" + legacy_base64, "2026-01-01T00:00:00"),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("ORACLE_VAULT_KEY", new_key)
    assert database.migrate_legacy_vault_key() == 2
    secrets = {item["label"]: item["secret"] for item in database.list_vault(reveal=True)}

    conn = db.get_conn()
    try:
        removed_legacy_key = conn.execute(
            "SELECT 1 FROM settings WHERE key = 'vault_key'"
        ).fetchone()
        encrypted_rows = conn.execute(
            "SELECT secret_enc FROM password_vault ORDER BY id"
        ).fetchall()
    finally:
        conn.close()

    assert secrets == {
        "old-base64": "old-base64-secret",
        "old-fernet": "old-fernet-secret",
    }
    assert removed_legacy_key is None
    assert all(row["secret_enc"].startswith("f:") for row in encrypted_rows)


def test_corrupt_legacy_vault_row_rolls_back_migration(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    legacy_key = Fernet.generate_key()
    db.set_setting("vault_key", legacy_key.decode("ascii"))
    conn = db.get_conn()
    try:
        conn.execute(
            "INSERT INTO password_vault(label, username, secret_enc, created_at) "
            "VALUES(?,?,?,?)",
            ("corrupt", "owner", "f:not-a-valid-fernet-token", "2026-01-01T00:00:00"),
        )
        conn.commit()
    finally:
        conn.close()

    new_key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("ORACLE_VAULT_KEY", new_key)
    with pytest.raises(database.VaultMigrationError):
        database.migrate_legacy_vault_key()

    conn = db.get_conn()
    try:
        key_row = conn.execute(
            "SELECT value FROM settings WHERE key = 'vault_key'"
        ).fetchone()
        stored = conn.execute("SELECT secret_enc FROM password_vault").fetchone()["secret_enc"]
    finally:
        conn.close()

    assert key_row["value"] == legacy_key.decode("ascii")
    assert stored == "f:not-a-valid-fernet-token"
