"""Encrypted, TTL-bounded workflow checkpoints for safe resume after approval."""

from __future__ import annotations

import json
import os
import re
import secrets
import time
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from database import init_database
from db import get_conn

MAX_CHECKPOINT_BYTES = 256_000
DEFAULT_TTL_HOURS = 24


class CheckpointError(ValueError):
    """Raised when an encrypted workflow checkpoint is invalid or unavailable."""


def _key_file() -> Path:
    configured = os.environ.get("ORACLE_CHECKPOINT_KEY_FILE", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".personal_ai_oracle" / "checkpoint.key"


def _fernet() -> Fernet:
    configured = os.environ.get("ORACLE_CHECKPOINT_ENCRYPTION_KEY", "").strip()
    if configured:
        try:
            return Fernet(configured.encode("ascii"))
        except (ValueError, TypeError) as exc:
            raise CheckpointError("ORACLE_CHECKPOINT_ENCRYPTION_KEY is invalid.") from exc

    path = _key_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path.parent, 0o700)
        try:
            descriptor = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            descriptor = None
        if descriptor is not None:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(Fernet.generate_key())
                stream.flush()
                os.fsync(stream.fileno())
        if path.is_symlink():
            raise CheckpointError("Checkpoint key file must not be a symbolic link.")
        os.chmod(path, 0o600)
        key = path.read_bytes().strip()
        return Fernet(key)
    except (OSError, ValueError) as exc:
        if isinstance(exc, CheckpointError):
            raise
        raise CheckpointError("Could not securely load the checkpoint encryption key.") from exc


def _scope(value: str) -> str:
    if not isinstance(value, str) or not (value := value.strip()) or len(value) > 255:
        raise CheckpointError("A valid owner scope is required.")
    return value


def _checkpoint_id(value: str | None) -> str:
    if value is None:
        return secrets.token_hex(16)
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}", value):
        raise CheckpointError("Invalid checkpoint identifier.")
    return value


def encrypt_scoped_payload(scope: str, payload: Any) -> str:
    """Encrypt a JSON-safe payload and bind it to one owner scope."""
    scope = _scope(scope)
    try:
        raw = json.dumps(
            {"_owner_scope": scope, "payload": payload},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CheckpointError("Encrypted payload must contain JSON-safe values.") from exc
    if len(raw) > MAX_CHECKPOINT_BYTES:
        raise CheckpointError("Encrypted payload is larger than the configured limit.")
    return _fernet().encrypt(raw).decode("ascii")


def decrypt_scoped_payload(scope: str, ciphertext: str) -> Any:
    """Decrypt a payload only when its embedded owner scope matches the caller."""
    scope = _scope(scope)
    if not isinstance(ciphertext, str) or not ciphertext or len(ciphertext) > MAX_CHECKPOINT_BYTES * 4:
        raise CheckpointError("Encrypted payload is invalid or oversized.")
    try:
        decoded = _fernet().decrypt(ciphertext.encode("ascii"))
        value = json.loads(decoded.decode("utf-8"))
    except (InvalidToken, UnicodeError, ValueError, TypeError) as exc:
        raise CheckpointError("Encrypted payload authentication failed.") from exc
    if not isinstance(value, dict) or value.get("_owner_scope") != scope or "payload" not in value:
        raise CheckpointError("Encrypted payload ownership validation failed.")
    return value["payload"]


def save_checkpoint(
    scope: str,
    payload: dict[str, Any],
    *,
    checkpoint_id: str | None = None,
    ttl_hours: int = DEFAULT_TTL_HOURS,
) -> str:
    scope = _scope(scope)
    checkpoint_id = _checkpoint_id(checkpoint_id)
    if not isinstance(payload, dict):
        raise CheckpointError("Checkpoint payload must be a JSON object.")
    if isinstance(ttl_hours, bool) or not isinstance(ttl_hours, int) or not 1 <= ttl_hours <= 168:
        raise CheckpointError("ttl_hours must be between 1 and 168.")
    value = dict(payload)
    value["_owner_scope"] = scope
    value["_saved_at"] = time.time()
    try:
        raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CheckpointError("Checkpoint payload must contain JSON-safe values.") from exc
    if len(raw) > MAX_CHECKPOINT_BYTES:
        raise CheckpointError("Checkpoint payload is larger than the configured limit.")
    token = _fernet().encrypt(raw).decode("ascii")
    now = time.time()
    expires = now + ttl_hours * 3600
    init_database()
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO oracle_workflow_checkpoints
               (checkpoint_id,scope,ciphertext,created_at,updated_at,expires_at)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(checkpoint_id) DO UPDATE SET
                 scope=excluded.scope,ciphertext=excluded.ciphertext,
                 updated_at=excluded.updated_at,expires_at=excluded.expires_at""",
            (checkpoint_id, scope, token, now, now, expires),
        )
        conn.commit()
        return checkpoint_id
    finally:
        conn.close()


def load_checkpoint(scope: str, checkpoint_id: str) -> dict[str, Any]:
    scope = _scope(scope)
    checkpoint_id = _checkpoint_id(checkpoint_id)
    init_database()
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT ciphertext,expires_at FROM oracle_workflow_checkpoints
               WHERE checkpoint_id=? AND scope=?""",
            (checkpoint_id, scope),
        ).fetchone()
        if row is None:
            raise CheckpointError("Checkpoint was not found in this owner scope.")
        if float(row["expires_at"]) <= time.time():
            conn.execute(
                "DELETE FROM oracle_workflow_checkpoints WHERE checkpoint_id=? AND scope=?",
                (checkpoint_id, scope),
            )
            conn.commit()
            raise CheckpointError("Checkpoint has expired.")
        try:
            decoded = _fernet().decrypt(row["ciphertext"].encode("ascii"))
            payload = json.loads(decoded.decode("utf-8"))
        except (InvalidToken, UnicodeError, ValueError, TypeError) as exc:
            raise CheckpointError("Checkpoint authentication failed; refusing to resume it.") from exc
        if not isinstance(payload, dict) or payload.get("_owner_scope") != scope:
            raise CheckpointError("Checkpoint ownership validation failed.")
        payload.pop("_owner_scope", None)
        payload.pop("_saved_at", None)
        return payload
    finally:
        conn.close()


def delete_checkpoint(scope: str, checkpoint_id: str) -> bool:
    scope = _scope(scope)
    checkpoint_id = _checkpoint_id(checkpoint_id)
    init_database()
    conn = get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM oracle_workflow_checkpoints WHERE checkpoint_id=? AND scope=?",
            (checkpoint_id, scope),
        )
        conn.commit()
        return cur.rowcount == 1
    finally:
        conn.close()


def cleanup_expired() -> int:
    init_database()
    conn = get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM oracle_workflow_checkpoints WHERE expires_at < ?",
            (time.time(),),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
