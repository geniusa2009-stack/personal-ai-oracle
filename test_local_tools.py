import json
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

import db
import execution_policy
import local_tools


def _allow_workspace(monkeypatch, tmp_path, *, tools, commands=None):
    workspace = tmp_path / "trusted-workspace"
    workspace.mkdir(exist_ok=True)
    policy = {
        "version": 1,
        "trusted_workspaces": [str(workspace)],
        "auto_allow_tools": list(tools),
        "auto_run_commands": list(commands or []),
        "allowed_applications": [],
    }
    policy_path = tmp_path / "mac_intelligence.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    monkeypatch.setenv("ORACLE_MAC_INTELLIGENCE_POLICY_FILE", str(policy_path))
    monkeypatch.setenv("ORACLE_WORKFLOW_SCOPE", "user:oracle-owner")
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "local-tools-approvals.db"))
    return workspace


def test_local_file_write_read_move_and_delete_requires_approval_for_delete(monkeypatch, tmp_path):
    workspace = _allow_workspace(
        monkeypatch,
        tmp_path,
        tools=["local.write_file", "local.move_path", "local.delete_path"],
    )
    first = workspace / "nested" / "note.txt"
    second = workspace / "moved.txt"

    written = local_tools.execute(
        "local.write_file",
        {"path": str(first), "content": "Oracle local memory"},
    )
    assert written["status"] == "success"
    assert first.read_text(encoding="utf-8") == "Oracle local memory"

    read = local_tools.execute("local.read_file", {"path": str(first)})
    assert read["status"] == "success"
    assert read["result"] == "Oracle local memory"

    moved = local_tools.execute(
        "local.move_path",
        {"source": str(first), "destination": str(second)},
    )
    assert moved["status"] == "success"
    assert second.exists()

    delete_payload = {"path": str(second), "recursive": False}
    pending = local_tools.execute("local.delete_path", delete_payload)
    assert pending["status"] == "awaiting_approval"
    assert second.exists()

    assert execution_policy.decide_approval(
        pending["approval_id"], scope="user:oracle-owner", approve=True
    ) is True
    deleted = local_tools.execute("local.delete_path", delete_payload)
    assert deleted["status"] == "success"
    assert not second.exists()


def test_local_directory_listing_and_pattern_search(tmp_path):
    (tmp_path / "one.py").write_text("print(1)", encoding="utf-8")
    (tmp_path / "two.py").write_text("print(2)", encoding="utf-8")
    (tmp_path / "readme.md").write_text("hello", encoding="utf-8")

    listing = local_tools.execute("local.list_directory", {"path": str(tmp_path)})
    assert listing["status"] == "success"
    assert "one.py" in listing["result"]

    found = local_tools.execute(
        "local.find_files",
        {"root": str(tmp_path), "pattern": "*.py", "max_results": 10},
    )
    assert found["status"] == "success"
    assert "one.py" in found["result"]
    assert "two.py" in found["result"]
    assert "readme.md" not in found["result"]


def test_local_command_runs_as_current_user_without_shell(monkeypatch, tmp_path):
    workspace = _allow_workspace(
        monkeypatch,
        tmp_path,
        tools=["local.run_command"],
        commands=[[sys.executable, "-m", "compileall"]],
    )
    sample = workspace / "sample.py"
    sample.write_text("value = 42" + chr(10), encoding="utf-8")
    result = local_tools.execute(
        "local.run_command",
        {
            "command": [sys.executable, "-m", "compileall", str(sample)],
            "cwd": str(workspace),
            "timeout": 10,
        },
    )

    assert result["status"] == "success"
    assert result["exit_code"] == 0
    assert str(sample) in result["result"]


def test_local_command_requires_an_argument_array():
    result = local_tools.execute(
        "local.run_command",
        {"command": "echo should-not-run"},
    )

    assert result["status"] == "error"
    assert "array of strings" in result["result"]


def test_local_command_uses_shell_false(monkeypatch, tmp_path):
    workspace = _allow_workspace(
        monkeypatch,
        tmp_path,
        tools=["local.run_command"],
        commands=[["git", "status"]],
    )
    completed = Mock(returncode=0, stdout="ok", stderr="")
    with patch("local_tools.subprocess.run", return_value=completed) as run:
        result = local_tools.execute(
            "local.run_command",
            {"command": ["git", "status"], "cwd": str(workspace), "timeout": 5},
        )

    assert result["status"] == "success"
    assert run.call_args.kwargs["shell"] is False
    assert run.call_args.kwargs["cwd"] == str(tmp_path.resolve())


def test_local_read_rejects_oversized_file(tmp_path):
    target = tmp_path / "large.bin"
    target.write_bytes(b"x" * (local_tools.MAX_FILE_READ_BYTES + 1))

    result = local_tools.execute("local.read_file", {"path": str(target)})

    assert result["status"] == "error"
    assert "larger than" in result["result"]


def test_local_tools_are_explicit_and_discoverable():
    tools = local_tools.available_tools()
    ids = {item["tool_id"] for item in tools}

    assert "local.run_command" in ids
    assert "local.read_file" in ids
    assert "local.write_file" in ids
    assert "local.open_app" in ids
    assert "local.get_system_info" in ids
    assert "local.list_processes" in ids
    assert "local.list_applications" in ids
    assert "local.get_mac_intelligence_status" in ids


def test_local_agent_refuses_unrestricted_python_and_system_control_commands():
    python_code = local_tools.execute(
        "local.run_command",
        {"command": [sys.executable, "-c", "print('not allowed')"]},
    )
    system_command = local_tools.execute(
        "local.run_command",
        {"command": ["sudo", "example"]},
    )

    assert python_code["status"] == "error"
    assert "Only test, compile" in python_code["result"]
    assert system_command["status"] == "error"
    assert "system or age-safety protections" in system_command["result"]


def test_local_tool_audit_does_not_store_file_contents(monkeypatch, tmp_path):
    monkeypatch.setenv("ORACLE_AUDIT_DIR", str(tmp_path / "audit"))
    secret_text = "local-private-content"
    target = tmp_path / "private.txt"
    target.write_text(secret_text, encoding="utf-8")

    result = local_tools.execute("local.read_file", {"path": str(target)})

    audit = (tmp_path / "audit" / "local-actions.jsonl").read_text(encoding="utf-8")
    assert result["status"] == "success"
    assert "local.read_file" in audit
    assert secret_text not in audit


def test_direct_delete_cannot_bypass_approval_even_when_policy_lists_delete(monkeypatch, tmp_path):
    workspace = _allow_workspace(
        monkeypatch,
        tmp_path,
        tools=["local.delete_path"],
    )
    target = workspace / "important.txt"
    target.write_text("preserve until approved", encoding="utf-8")

    result = local_tools.execute(
        "local.delete_path",
        {"path": str(target), "recursive": False},
    )

    assert result["status"] == "awaiting_approval"
    assert target.read_text(encoding="utf-8") == "preserve until approved"
    approvals = execution_policy.list_approvals("user:oracle-owner", include_decided=False)
    assert len(approvals) == 1
    assert approvals[0]["tool_id"] == "local.delete_path"
