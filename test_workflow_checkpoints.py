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
