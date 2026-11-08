"""Deterministic, owner-scoped authorization for local Oracle actions.

Read-only actions need no approval. Non-delete mutations may be auto-allowed only
by the explicit Mac workspace policy; otherwise they require a one-time grant.
Deletion always requires explicit owner approval, including inside trusted workspaces.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import threading
import time
from typing import Any

from database import init_database
from db import get_conn

READ_ONLY_TOOLS = frozenset({
    "local.list_directory", "local.read_file", "local.find_files",
    "local.get_system_info", "local.list_processes", "local.list_applications",
    "local.get_mac_intelligence_status",
    "web.search", "web.navigate", "web.extract", "web.links", "web.open_browser",
})
APPROVAL_TOOLS = frozenset({
    "local.write_file", "local.move_path", "local.delete_path",
    "local.run_command", "local.open_app",
})
MAX_APPROVALS = 100
DEFAULT_TTL_SECONDS = 15 * 60
_EXECUTION_GRANT_TTL_SECONDS = 60
_EXECUTION_GRANTS: dict[str, tuple[str, str, str, float]] = {}
_EXECUTION_GRANTS_LOCK = threading.Lock()


class PolicyError(ValueError):
    """Raised when an approval request or decision is invalid."""


def _scope(value: str) -> str:
    if not isinstance(value, str) or not (value := value.strip()) or len(value) > 255:
        raise PolicyError("A valid owner scope is required.")
    return value


def _payload(value: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError as exc:
            raise PolicyError("Tool input must be valid JSON.") from exc
        if isinstance(parsed, dict):
            return parsed
    raise PolicyError("Tool input must be a JSON object.")


def _canonical(value: str | dict[str, Any]) -> str:
    data = _payload(value)
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def action_digest(value: str | dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _redact(value: Any) -> Any:
    if isinstance(value, str):
        value = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1[REDACTED]", value)
        value = re.sub(
            r"(?i)(api[_-]?key|token|password|secret|authorization)(\s*[=:]\s*)[^\s,;]+",
            r"\1\2[REDACTED]", value,
        )
        if re.search(r"(?i)\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,})\b", value):
            return "[REDACTED: secret-like value]"
        return value[:500]
    if isinstance(value, list):
        result = []
        redact_next = False
        for item in value[:40]:
            if redact_next:
                result.append("[REDACTED]")
                redact_next = False
                continue
            result.append(_redact(item))
            if isinstance(item, str) and re.search(r"(?i)(token|password|secret|api[-_]?key|authorization)", item):
                redact_next = True
        return result
    return value


def _preview(tool_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if tool_id == "local.write_file":
        content = payload.get("content", "")
        return {
            "operation": "write_file",
            "path": _redact(payload.get("path", "")),
            "content_bytes": len(content.encode("utf-8")) if isinstance(content, str) else None,
            "content_included": False,
        }
    if tool_id == "local.move_path":
        return {
            "operation": "move_path",
            "source": _redact(payload.get("source", "")),
            "destination": _redact(payload.get("destination", "")),
        }
    if tool_id == "local.delete_path":
        return {
            "operation": "delete_path",
            "path": _redact(payload.get("path", "")),
            "recursive": payload.get("recursive", False) is True,
        }
    if tool_id == "local.run_command":
        command = payload.get("command", [])
        return {
            "operation": "run_command",
            "argv": _redact(command) if isinstance(command, list) else "[invalid argv]",
            "cwd": _redact(payload.get("cwd", "")),
            "timeout_seconds": payload.get("timeout", 120),
        }
    if tool_id == "local.open_app":
        return {"operation": "open_app", "application": _redact(payload.get("application", ""))}
    return {"operation": "unknown"}


def _new_request(conn, scope: str, tool_id: str, digest: str, preview: dict[str, Any]) -> str:
    now = time.time()
    request_id = secrets.token_hex(16)
    ttl = max(60, min(int(os.environ.get("ORACLE_APPROVAL_TTL_SECONDS", DEFAULT_TTL_SECONDS)), 3600))
    conn.execute(
        """INSERT INTO oracle_execution_approvals
           (approval_id,scope,tool_id,action_digest,preview_json,status,created_at,expires_at)
           VALUES(?,?,?,?,?,'pending',?,?)""",
        (request_id, scope, tool_id, digest,
         json.dumps(preview, ensure_ascii=False, separators=(",", ":")), now, now + ttl),
    )
    return request_id


def _issue_execution_grant(tool_id: str, scope: str, payload: dict[str, Any]) -> str:
    """Create a short-lived, single-use in-process capability for the exact action."""
    token = secrets.token_urlsafe(32)
    digest = action_digest(payload)
    expires = time.monotonic() + _EXECUTION_GRANT_TTL_SECONDS
    with _EXECUTION_GRANTS_LOCK:
        expired = [
            key for key, value in _EXECUTION_GRANTS.items()
            if value[3] <= time.monotonic()
        ]
        for key in expired:
            _EXECUTION_GRANTS.pop(key, None)
        if len(_EXECUTION_GRANTS) >= 1000:
            oldest = next(iter(_EXECUTION_GRANTS), None)
            if oldest is not None:
                _EXECUTION_GRANTS.pop(oldest, None)
        _EXECUTION_GRANTS[token] = (tool_id, scope, digest, expires)
    return token


def consume_execution_grant(
    token: str,
    tool_id: str,
    tool_input: str | dict[str, Any],
    *,
    scope: str,
) -> bool:
    """Consume a single-use grant bound to one tool, owner scope, and exact payload."""
    if not isinstance(token, str) or not token:
        return False
    try:
        expected = (tool_id, _scope(scope), action_digest(tool_input))
    except (PolicyError, TypeError, ValueError):
        return False
    with _EXECUTION_GRANTS_LOCK:
        stored = _EXECUTION_GRANTS.pop(token, None)
    if stored is None:
        return False
    return (
        stored[3] > time.monotonic()
        and stored[:3] == expected
    )


def discard_execution_grant(token: str | None) -> None:
    if not isinstance(token, str) or not token:
        return
    with _EXECUTION_GRANTS_LOCK:
        _EXECUTION_GRANTS.pop(token, None)


def authorize_action(tool_id: str, tool_input: str | dict[str, Any], *, scope: str) -> dict[str, Any]:
    """Allow read-only tools, consume a matching one-time grant, or request approval."""
    scope = _scope(scope)
    if tool_id in READ_ONLY_TOOLS:
        return {"allowed": True, "reason": "read_only"}
    if tool_id not in APPROVAL_TOOLS:
        if isinstance(tool_id, str) and tool_id.startswith("local."):
            return {"allowed": False, "reason": "unknown_local_tool"}
        return {"allowed": True, "reason": "not_a_local_mutation"}

    payload = _payload(tool_input)
    if tool_id != "local.delete_path":
        try:
            import mac_intelligence
            workspace_decision = mac_intelligence.authorize_workspace_action(tool_id, payload)
            if workspace_decision.get("allowed"):
                return {
                    "allowed": True,
                    "reason": workspace_decision.get("reason", "trusted_workspace"),
                    "execution_grant": _issue_execution_grant(tool_id, scope, payload),
                }
        except Exception:
            # An unavailable policy must never widen permissions; fall through to explicit approval.
            pass
    digest = action_digest(payload)
    preview = _preview(tool_id, payload)
    init_database()
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        now = time.time()
        approved = conn.execute(
            """SELECT approval_id FROM oracle_execution_approvals
               WHERE scope=? AND tool_id=? AND action_digest=? AND status='approved'
                 AND expires_at>? ORDER BY created_at DESC LIMIT 1""",
            (scope, tool_id, digest, now),
        ).fetchone()
        if approved:
            changed = conn.execute(
                """UPDATE oracle_execution_approvals SET status='consumed',decided_at=?
                   WHERE approval_id=? AND scope=? AND status='approved'""",
                (now, approved["approval_id"], scope),
            ).rowcount
            if changed == 1:
                conn.commit()
                return {
                    "allowed": True,
                    "reason": "one_time_approval",
                    "approval_id": approved["approval_id"],
                    "execution_grant": _issue_execution_grant(tool_id, scope, payload),
                }
        pending = conn.execute(
            """SELECT approval_id FROM oracle_execution_approvals
               WHERE scope=? AND tool_id=? AND action_digest=? AND status='pending'
                 AND expires_at>? ORDER BY created_at DESC LIMIT 1""",
            (scope, tool_id, digest, now),
        ).fetchone()
        request_id = pending["approval_id"] if pending else _new_request(
            conn, scope, tool_id, digest, preview
        )
        conn.commit()
        return {
            "allowed": False,
            "reason": "human_approval_required",
            "approval_id": request_id,
            "action_digest": digest,
            "preview": preview,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def decide_approval(approval_id: str, *, scope: str, approve: bool) -> bool:
    scope = _scope(scope)
    if not isinstance(approval_id, str) or not re.fullmatch(r"[a-f0-9]{32}", approval_id):
        raise PolicyError("Invalid approval identifier.")
    if not isinstance(approve, bool):
        raise PolicyError("approve must be true or false.")
    init_database()
    conn = get_conn()
    try:
        now = time.time()
        status = "approved" if approve else "denied"
        cur = conn.execute(
            """UPDATE oracle_execution_approvals SET status=?,decided_at=?
               WHERE approval_id=? AND scope=? AND status='pending' AND expires_at>?""",
            (status, now, approval_id, scope, now),
        )
        conn.commit()
        return cur.rowcount == 1
    finally:
        conn.close()


def link_checkpoint(approval_id: str, checkpoint_id: str, *, scope: str) -> bool:
    scope = _scope(scope)
    if not re.fullmatch(r"[a-f0-9]{32}", str(approval_id)) or not re.fullmatch(
        r"[a-f0-9]{32}", str(checkpoint_id)
    ):
        raise PolicyError("Invalid approval or checkpoint identifier.")
    init_database()
    conn = get_conn()
    try:
        cur = conn.execute(
            """UPDATE oracle_execution_approvals SET checkpoint_id=?
               WHERE approval_id=? AND scope=? AND status IN ('pending','approved')""",
            (checkpoint_id, approval_id, scope),
        )
        conn.commit()
        return cur.rowcount == 1
    finally:
        conn.close()


def list_approvals(scope: str, *, include_decided: bool = True, limit: int = 50) -> list[dict[str, Any]]:
    scope = _scope(scope)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_APPROVALS:
        raise PolicyError("limit must be between 1 and 100.")
    statuses = ("pending", "approved") if include_decided else ("pending",)
    placeholders = ",".join("?" for _ in statuses)
    init_database()
    conn = get_conn()
    try:
        rows = conn.execute(
            f"""SELECT approval_id,tool_id,action_digest,preview_json,status,
                       created_at,expires_at,checkpoint_id
                FROM oracle_execution_approvals
                WHERE scope=? AND status IN ({placeholders}) AND expires_at>?
                ORDER BY created_at DESC LIMIT ?""",
            (scope, *statuses, time.time(), limit),
        ).fetchall()
        result = []
        for row in rows:
            try:
                preview = json.loads(row["preview_json"])
            except (TypeError, ValueError):
                preview = {"operation": "preview_unavailable"}
            item = dict(row)
            item["preview"] = preview
            item.pop("preview_json", None)
            result.append(item)
        return result
    finally:
        conn.close()


def cleanup_expired() -> int:
    init_database()
    conn = get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM oracle_execution_approvals WHERE expires_at < ?",
            (time.time() - 86400,),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
