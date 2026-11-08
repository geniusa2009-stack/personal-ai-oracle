import time

import pytest
from cryptography.fernet import Fernet

import db
import workflow_checkpoints


def _database(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "checkpoints.db"))
    monkeypatch.setenv(
        "ORACLE_CHECKPOINT_ENCRYPTION_KEY",
        Fernet.generate_key().decode("ascii"),
    )


def test_checkpoint_is_encrypted_scope_bound_and_round_trips(monkeypatch, tmp_path):
    _database(monkeypatch, tmp_path)
    payload = {"task": "highly-private-task-text", "results": [{"result": "sensitive-output"}]}
    checkpoint_id = workflow_checkpoints.save_checkpoint("owner-a", payload)
    restored = workflow_checkpoints.load_checkpoint("owner-a", checkpoint_id)
    assert restored == payload

    connection = db.get_conn()
    try:
        row = connection.execute(
            "SELECT ciphertext FROM oracle_workflow_checkpoints WHERE checkpoint_id=?",
            (checkpoint_id,),
        ).fetchone()
    finally:
        connection.close()
    assert "highly-private-task-text" not in row["ciphertext"]
    assert "sensitive-output" not in row["ciphertext"]
    with pytest.raises(workflow_checkpoints.CheckpointError):
        workflow_checkpoints.load_checkpoint("owner-b", checkpoint_id)


def test_checkpoint_rejects_tampering_and_expired_data(monkeypatch, tmp_path):
    _database(monkeypatch, tmp_path)
    tampered_id = workflow_checkpoints.save_checkpoint("owner-a", {"task": "private"})
    connection = db.get_conn()
    try:
        connection.execute(
            "UPDATE oracle_workflow_checkpoints SET ciphertext='invalid-token' WHERE checkpoint_id=?",
            (tampered_id,),
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(workflow_checkpoints.CheckpointError):
        workflow_checkpoints.load_checkpoint("owner-a", tampered_id)

    expired_id = workflow_checkpoints.save_checkpoint("owner-a", {"task": "expired"})
    connection = db.get_conn()
    try:
        connection.execute(
            "UPDATE oracle_workflow_checkpoints SET expires_at=? WHERE checkpoint_id=?",
            (time.time() - 1, expired_id),
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(workflow_checkpoints.CheckpointError, match="expired"):
        workflow_checkpoints.load_checkpoint("owner-a", expired_id)


def test_checkpoint_size_and_ttl_are_bounded(monkeypatch, tmp_path):
    _database(monkeypatch, tmp_path)
    with pytest.raises(workflow_checkpoints.CheckpointError):
        workflow_checkpoints.save_checkpoint("owner-a", {"value": "x" * 300_000})
    with pytest.raises(workflow_checkpoints.CheckpointError):
        workflow_checkpoints.save_checkpoint("owner-a", {"task": "x"}, ttl_hours=0)



def test_scoped_payload_encryption_is_authenticated_and_scope_bound(monkeypatch, tmp_path):
    _database(monkeypatch, tmp_path)
    payload = {"task": "private durable task", "nested": [{"value": "secret-result"}]}

    ciphertext = workflow_checkpoints.encrypt_scoped_payload("owner-a", payload)

    assert "private durable task" not in ciphertext
    assert "secret-result" not in ciphertext
    assert workflow_checkpoints.decrypt_scoped_payload("owner-a", ciphertext) == payload
    with pytest.raises(workflow_checkpoints.CheckpointError, match="ownership"):
        workflow_checkpoints.decrypt_scoped_payload("owner-b", ciphertext)


def test_scoped_payload_encryption_rejects_tampered_and_oversized_values(monkeypatch, tmp_path):
    _database(monkeypatch, tmp_path)
    ciphertext = workflow_checkpoints.encrypt_scoped_payload("owner-a", {"value": "private"})
    with pytest.raises(workflow_checkpoints.CheckpointError, match="authentication"):
        workflow_checkpoints.decrypt_scoped_payload("owner-a", ciphertext[:-4] + "xxxx")
    with pytest.raises(workflow_checkpoints.CheckpointError, match="larger"):
        workflow_checkpoints.encrypt_scoped_payload(
            "owner-a", {"value": "x" * workflow_checkpoints.MAX_CHECKPOINT_BYTES}
        )
