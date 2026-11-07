"""Policy and capability boundary for Oracle's dedicated Mac execution environment.

Trusted workspaces are explicit owner configuration, not model-selected paths.
This module never elevates privileges or bypasses macOS privacy controls.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

MAX_POLICY_BYTES = 64 * 1024
READ_ONLY_TOOLS = frozenset({
    "local.list_directory", "local.read_file", "local.find_files",
    "local.get_system_info", "local.list_processes", "local.list_applications",
    "local.get_mac_intelligence_status",
    "web.search", "web.navigate", "web.extract", "web.links", "web.open_browser",
})
REMOTE_MUTATION_TOOLS = frozenset({
    "local.write_file", "local.run_command", "local.open_app",
})
ALLOWED_POLICY_KEYS = frozenset({
    "version", "trusted_workspaces", "auto_allow_tools",
    "auto_run_commands", "allowed_applications",
    "allow_screen_capture", "allow_admin_operations",
})


class PolicyConfigurationError(ValueError):
    """Raised when the local Mac Intelligence policy is malformed."""


def policy_file_path() -> Path:
    configured = os.environ.get("ORACLE_MAC_INTELLIGENCE_POLICY_FILE", "").strip()
    return Path(configured).expanduser() if configured else (
        Path.home() / ".personal_ai_oracle" / "mac_intelligence.json"
    )


def _load_policy() -> dict[str, Any]:
    path = policy_file_path()
    if not path.exists():
        return {
            "version": 1,
            "trusted_workspaces": [],
            "auto_allow_tools": [],
            "auto_run_commands": [],
            "allowed_applications": [],
            "allow_screen_capture": False,
            "allow_admin_operations": False,
        }
    try:
        if path.stat().st_size > MAX_POLICY_BYTES:
            raise PolicyConfigurationError("Mac Intelligence policy exceeds the size limit.")
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PolicyConfigurationError("Mac Intelligence policy cannot be read.") from exc
    if not isinstance(data, dict) or data.get("version") != 1:
        raise PolicyConfigurationError("Mac Intelligence policy must be a version 1 JSON object.")
    unknown = set(data) - ALLOWED_POLICY_KEYS
    if unknown:
        raise PolicyConfigurationError("Mac Intelligence policy contains unsupported keys.")
    for key in ("trusted_workspaces", "auto_allow_tools", "auto_run_commands", "allowed_applications"):
        if key not in data:
            data[key] = []
        if not isinstance(data[key], list):
            raise PolicyConfigurationError(f"{key} must be a JSON array.")
    for key in ("allow_screen_capture", "allow_admin_operations"):
        if key not in data:
            data[key] = False
        if not isinstance(data[key], bool):
            raise PolicyConfigurationError(f"{key} must be true or false.")
    if any(not isinstance(item, str) or not item.strip() for item in data["trusted_workspaces"]):
        raise PolicyConfigurationError("trusted_workspaces must contain non-empty path strings.")
    if any(not isinstance(item, str) for item in data["auto_allow_tools"]):
        raise PolicyConfigurationError("auto_allow_tools must contain tool ID strings.")
    if any(
        not isinstance(command, list) or not command
        or any(not isinstance(part, str) or not part for part in command)
        for command in data["auto_run_commands"]
    ):
        raise PolicyConfigurationError("auto_run_commands must contain non-empty argv arrays.")
    if any(not isinstance(item, str) or not item.strip() for item in data["allowed_applications"]):
        raise PolicyConfigurationError("allowed_applications must contain application names.")
    return data


def _configured_roots(policy: dict[str, Any]) -> list[Path]:
    values = list(policy["trusted_workspaces"])
    environment = os.environ.get("ORACLE_TRUSTED_WORKSPACES", "").strip()
    if environment:
        values.extend(item for item in environment.split(os.pathsep) if item)
    roots: list[Path] = []
    for value in values:
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            continue
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            continue
        if resolved.is_dir() and resolved not in roots:
            roots.append(resolved)
    return roots


def trusted_workspace_for(path_value: Any) -> Path | None:
    if not isinstance(path_value, str) or not path_value.strip():
        return None
    candidate = Path(path_value).expanduser()
    if not candidate.is_absolute():
        return None
    try:
        resolved = candidate.resolve(strict=False)
        for root in _configured_roots(_load_policy()):
            if resolved == root or root in resolved.parents:
                return root
    except (OSError, PolicyConfigurationError, RuntimeError):
        return None
    return None


def _matches_command(command: Any, configured: list[list[str]]) -> bool:
    if not isinstance(command, list) or not command or any(not isinstance(part, str) for part in command):
        return False
    return any(
        len(command) >= len(prefix) and command[:len(prefix)] == prefix
        for prefix in configured
    )


def authorize_workspace_action(tool_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Authorize only an explicitly configured action inside a configured workspace."""
    try:
        policy = _load_policy()
        # Move and delete are deliberately never covered by trusted-workspace
        # automation; they continue through the exact one-time approval gate.
        if tool_id in {"local.move_path", "local.delete_path"}:
            return {"allowed": False, "reason": "explicit_approval_required"}
        auto_tools = set(policy["auto_allow_tools"])
        if tool_id not in auto_tools:
            return {"allowed": False, "reason": "manual_approval_required"}

        paths: list[str] = []
        if tool_id == "local.write_file":
            paths = [payload.get("path")]
        elif tool_id == "local.move_path":
            paths = [payload.get("source"), payload.get("destination")]
        elif tool_id == "local.delete_path":
            if payload.get("recursive", False) is not False:
                return {"allowed": False, "reason": "recursive_delete_never_auto_allowed"}
            paths = [payload.get("path")]
        elif tool_id == "local.run_command":
            command = payload.get("command")
            if not _matches_command(command, policy["auto_run_commands"]):
                return {"allowed": False, "reason": "command_not_in_local_policy"}
            cwd = payload.get("cwd") or os.environ.get("ORACLE_WORKSPACE", "")
            paths = [cwd]
        elif tool_id == "local.open_app":
            application = payload.get("application")
            allowed = policy["allowed_applications"]
            if isinstance(application, str) and application in allowed:
                return {"allowed": True, "reason": "application_allowlist"}
            return {"allowed": False, "reason": "application_not_in_local_policy"}
        else:
            return {"allowed": False, "reason": "tool_not_auto_allowlisted"}

        if not paths or any(trusted_workspace_for(path) is None for path in paths):
            return {"allowed": False, "reason": "path_outside_trusted_workspace"}
        return {"allowed": True, "reason": "trusted_workspace"}
    except PolicyConfigurationError:
        return {"allowed": False, "reason": "invalid_local_policy"}


def authorize_remote_action(tool_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Enforce the Mac's local policy again, even for authenticated cloud jobs."""
    if tool_id in READ_ONLY_TOOLS:
        return {"allowed": True, "reason": "read_only"}
    if tool_id not in REMOTE_MUTATION_TOOLS:
        return {"allowed": False, "reason": "remote_tool_not_enabled"}
    decision = authorize_workspace_action(tool_id, payload)
    if not decision.get("allowed"):
        return decision
    return {"allowed": True, "reason": decision["reason"]}


def get_status() -> dict[str, Any]:
    try:
        policy = _load_policy()
        roots = _configured_roots(policy)
        return {
            "status": "ready",
            "policy_version": 1,
            "trusted_workspaces": [str(root) for root in roots],
            "auto_allow_tools": list(policy["auto_allow_tools"]),
            "auto_run_commands": policy["auto_run_commands"],
            "allowed_applications": list(policy["allowed_applications"]),
            "screen_capture": "opted_in_but_not_integrated" if policy["allow_screen_capture"] else "disabled",
            "admin_operations": "policy_flag_only_not_implemented" if policy["allow_admin_operations"] else "disabled",
        }
    except PolicyConfigurationError:
        return {
            "status": "invalid_policy",
            "trusted_workspaces": [],
            "auto_allow_tools": [],
            "screen_capture": "disabled",
            "admin_operations": "disabled",
        }
