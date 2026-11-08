from __future__ import annotations

import json
from pathlib import Path

import mac_intelligence


def _write_policy(monkeypatch, tmp_path: Path, policy: dict) -> Path:
    path = tmp_path / "mac_intelligence.json"
    path.write_text(json.dumps(policy), encoding="utf-8")
    monkeypatch.setenv("ORACLE_MAC_INTELLIGENCE_POLICY_FILE", str(path))
    return path


def _policy(root: Path, **overrides):
    value = {
        "version": 1,
        "trusted_workspaces": [str(root)],
        "auto_allow_tools": ["local.write_file", "local.run_command", "local.open_app"],
        "auto_run_commands": [["git", "status"], ["npm", "run", "test"]],
        "allowed_applications": ["Visual Studio Code"],
    }
    value.update(overrides)
    return value


def test_no_policy_means_no_automatic_mutations(monkeypatch, tmp_path):
    monkeypatch.setenv("ORACLE_MAC_INTELLIGENCE_POLICY_FILE", str(tmp_path / "missing.json"))
    result = mac_intelligence.authorize_workspace_action(
        "local.write_file", {"path": str(tmp_path / "note.txt",), "content": "x"}
    )
    assert result == {"allowed": False, "reason": "manual_approval_required"}


def test_write_is_auto_allowed_only_inside_explicit_workspace(monkeypatch, tmp_path):
    workspace = tmp_path / "Projects"
    workspace.mkdir()
    _write_policy(monkeypatch, tmp_path, _policy(workspace))
    inside = mac_intelligence.authorize_workspace_action(
        "local.write_file", {"path": str(workspace / "new.txt"), "content": "ok"}
    )
    outside = mac_intelligence.authorize_workspace_action(
        "local.write_file", {"path": str(tmp_path / "outside.txt"), "content": "no"}
    )
    assert inside == {"allowed": True, "reason": "trusted_workspace"}
    assert outside["allowed"] is False
    assert outside["reason"] == "path_outside_trusted_workspace"


def test_symlink_escape_does_not_match_workspace(monkeypatch, tmp_path):
    workspace = tmp_path / "Projects"
    outside = tmp_path / "Private"
    workspace.mkdir()
    outside.mkdir()
    link = workspace / "escape"
    link.symlink_to(outside, target_is_directory=True)
    _write_policy(monkeypatch, tmp_path, _policy(workspace))
    result = mac_intelligence.authorize_workspace_action(
        "local.write_file", {"path": str(link / "note.txt"), "content": "no"}
    )
    assert result["allowed"] is False
    assert result["reason"] == "path_outside_trusted_workspace"


def test_command_requires_exact_configured_argv_prefix_and_trusted_cwd(monkeypatch, tmp_path):
    workspace = tmp_path / "Projects"
    workspace.mkdir()
    _write_policy(monkeypatch, tmp_path, _policy(workspace))
    allowed = mac_intelligence.authorize_workspace_action(
        "local.run_command", {"command": ["npm", "run", "test", "--", "--runInBand"], "cwd": str(workspace)}
    )
    denied_command = mac_intelligence.authorize_workspace_action(
        "local.run_command", {"command": ["npm", "run", "deploy"], "cwd": str(workspace)}
    )
    denied_cwd = mac_intelligence.authorize_workspace_action(
        "local.run_command", {"command": ["git", "status"], "cwd": str(tmp_path)}
    )
    assert allowed["allowed"] is True
    assert denied_command["reason"] == "command_not_in_local_policy"
    assert denied_cwd["reason"] == "path_outside_trusted_workspace"


def test_app_launch_requires_exact_local_allowlist(monkeypatch, tmp_path):
    workspace = tmp_path / "Projects"
    workspace.mkdir()
    _write_policy(monkeypatch, tmp_path, _policy(workspace))
    assert mac_intelligence.authorize_workspace_action(
        "local.open_app", {"application": "Visual Studio Code"}
    ) == {"allowed": True, "reason": "application_allowlist"}
    assert mac_intelligence.authorize_workspace_action(
        "local.open_app", {"application": "Unknown App"}
    )["allowed"] is False


def test_move_is_auto_allowed_only_inside_same_trusted_workspace_and_delete_always_requires_approval(monkeypatch, tmp_path):
    workspace = tmp_path / "Projects"
    outside = tmp_path / "Private"
    workspace.mkdir()
    outside.mkdir()
    policy = _policy(workspace, auto_allow_tools=["local.move_path", "local.delete_path"])
    _write_policy(monkeypatch, tmp_path, policy)

    moved = mac_intelligence.authorize_workspace_action(
        "local.move_path", {"source": str(workspace / "a"), "destination": str(workspace / "b")}
    )
    outside_move = mac_intelligence.authorize_workspace_action(
        "local.move_path", {"source": str(workspace / "a"), "destination": str(outside / "b")}
    )
    deleted = mac_intelligence.authorize_workspace_action(
        "local.delete_path", {"path": str(workspace / "old.txt"), "recursive": False}
    )

    assert moved == {"allowed": True, "reason": "trusted_workspace_move"}
    assert outside_move == {"allowed": False, "reason": "path_outside_trusted_workspace"}
    assert deleted == {"allowed": False, "reason": "explicit_approval_required"}


def test_move_to_existing_destination_requires_explicit_approval(monkeypatch, tmp_path):
    workspace = tmp_path / "Projects"
    workspace.mkdir()
    source = workspace / "source.txt"
    destination = workspace / "destination.txt"
    source.write_text("source", encoding="utf-8")
    destination.write_text("existing", encoding="utf-8")
    _write_policy(
        monkeypatch,
        tmp_path,
        _policy(workspace, auto_allow_tools=["local.move_path"]),
    )

    decision = mac_intelligence.authorize_workspace_action(
        "local.move_path",
        {"source": str(source), "destination": str(destination)},
    )

    assert decision == {"allowed": False, "reason": "destination_exists_requires_approval"}


def test_remote_mutation_requires_local_policy_and_never_exposes_delete(monkeypatch, tmp_path):
    workspace = tmp_path / "Projects"
    workspace.mkdir()
    _write_policy(monkeypatch, tmp_path, _policy(workspace))
    allowed = mac_intelligence.authorize_remote_action(
        "local.write_file", {"path": str(workspace / "remote.txt"), "content": "safe"}
    )
    denied = mac_intelligence.authorize_remote_action(
        "local.delete_path", {"path": str(workspace / "old.txt")}
    )
    assert allowed["allowed"] is True
    assert denied == {"allowed": False, "reason": "remote_tool_not_enabled"}


def test_invalid_policy_fails_closed(monkeypatch, tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"version": 1, "auto_allow_tools": "everything"}', encoding="utf-8")
    monkeypatch.setenv("ORACLE_MAC_INTELLIGENCE_POLICY_FILE", str(path))
    result = mac_intelligence.authorize_workspace_action(
        "local.write_file", {"path": str(tmp_path / "file"), "content": "x"}
    )
    assert result["allowed"] is False
    assert result["reason"] == "invalid_local_policy"


def test_policy_status_does_not_enable_unimplemented_screen_or_admin_features(monkeypatch, tmp_path):
    workspace = tmp_path / "Projects"
    workspace.mkdir()
    _write_policy(monkeypatch, tmp_path, _policy(
        workspace, allow_screen_capture=True, allow_admin_operations=True
    ))
    status = mac_intelligence.get_status()
    assert status["status"] == "ready"
    assert status["screen_capture"] == "opted_in_but_not_integrated"
    assert status["admin_operations"] == "policy_flag_only_not_implemented"
