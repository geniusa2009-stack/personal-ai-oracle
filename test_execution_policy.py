import json

import db
import execution_policy


def _database(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "execution-policy.db"))


def test_read_only_tools_are_allowed_without_approval(monkeypatch, tmp_path):
    _database(monkeypatch, tmp_path)
    result = execution_policy.authorize_action(
        "local.read_file", {"path": "/tmp/readme.txt"}, scope="owner-a"
    )
    assert result == {"allowed": True, "reason": "read_only"}
    assert execution_policy.list_approvals("owner-a") == []


def test_mac_diagnostic_tools_are_read_only_without_approval(monkeypatch, tmp_path):
    _database(monkeypatch, tmp_path)
    for tool_id in (
        "local.get_system_info", "local.list_processes",
        "local.list_applications", "local.get_mac_intelligence_status",
    ):
        result = execution_policy.authorize_action(tool_id, {}, scope="owner-a")
        assert result == {"allowed": True, "reason": "read_only"}
    assert execution_policy.list_approvals("owner-a") == []


def test_mutation_requires_exact_one_time_owner_approval(monkeypatch, tmp_path):
    _database(monkeypatch, tmp_path)
    payload = {"path": "/tmp/note.txt", "content": "private content"}
    pending = execution_policy.authorize_action("local.write_file", payload, scope="owner-a")
    assert pending["allowed"] is False
    assert pending["reason"] == "human_approval_required"
    assert pending["preview"]["content_included"] is False
    assert "private content" not in json.dumps(pending["preview"])

    assert execution_policy.decide_approval(
        pending["approval_id"], scope="owner-a", approve=True
    ) is True
    consumed = execution_policy.authorize_action("local.write_file", payload, scope="owner-a")
    assert consumed["allowed"] is True
    assert consumed["reason"] == "one_time_approval"

    second_use = execution_policy.authorize_action("local.write_file", payload, scope="owner-a")
    assert second_use["allowed"] is False
    assert second_use["approval_id"] != pending["approval_id"]


def test_approval_is_scope_and_payload_bound(monkeypatch, tmp_path):
    _database(monkeypatch, tmp_path)
    payload = {"path": "/tmp/a.txt", "content": "A"}
    pending = execution_policy.authorize_action("local.write_file", payload, scope="owner-a")
    assert execution_policy.decide_approval(
        pending["approval_id"], scope="owner-b", approve=True
    ) is False
    assert execution_policy.decide_approval(
        pending["approval_id"], scope="owner-a", approve=True
    ) is True

    altered = execution_policy.authorize_action(
        "local.write_file", {"path": "/tmp/b.txt", "content": "A"}, scope="owner-a"
    )
    assert altered["allowed"] is False
    assert altered["approval_id"] != pending["approval_id"]
    original = execution_policy.authorize_action("local.write_file", payload, scope="owner-a")
    assert original["allowed"] is True


def test_unknown_local_tool_fails_closed(monkeypatch, tmp_path):
    _database(monkeypatch, tmp_path)
    result = execution_policy.authorize_action(
        "local.unknown_power", {}, scope="owner-a"
    )
    assert result["allowed"] is False
    assert result["reason"] == "unknown_local_tool"
    assert execution_policy.list_approvals("owner-a") == []


def test_command_preview_redacts_authorization_header(monkeypatch, tmp_path):
    _database(monkeypatch, tmp_path)
    payload = {
        "command": ["curl", "-H", "Authorization", "Bearer super-secret-token-value"],
    }
    result = execution_policy.authorize_action(
        "local.run_command", payload, scope="owner-a"
    )
    preview = json.dumps(result["preview"])
    assert "super-secret-token-value" not in preview
    assert "[REDACTED]" in preview


def test_authorized_execution_grant_is_exact_scope_bound_and_single_use(monkeypatch, tmp_path):
    _database(monkeypatch, tmp_path)
    payload = {"path": "/tmp/granted.txt", "content": "one exact write"}
    pending = execution_policy.authorize_action(
        "local.write_file", payload, scope="owner-a"
    )
    assert execution_policy.decide_approval(
        pending["approval_id"], scope="owner-a", approve=True
    ) is True

    authorized = execution_policy.authorize_action(
        "local.write_file", payload, scope="owner-a"
    )
    grant = authorized["execution_grant"]
    assert execution_policy.consume_execution_grant(
        grant, "local.write_file", payload, scope="owner-a"
    ) is True
    assert execution_policy.consume_execution_grant(
        grant, "local.write_file", payload, scope="owner-a"
    ) is False


def test_execution_grant_cannot_be_reused_for_another_payload_or_scope(monkeypatch, tmp_path):
    _database(monkeypatch, tmp_path)
    payload = {"path": "/tmp/granted.txt", "content": "one exact write"}
    pending = execution_policy.authorize_action(
        "local.write_file", payload, scope="owner-a"
    )
    execution_policy.decide_approval(
        pending["approval_id"], scope="owner-a", approve=True
    )
    authorized = execution_policy.authorize_action(
        "local.write_file", payload, scope="owner-a"
    )
    grant = authorized["execution_grant"]

    assert execution_policy.consume_execution_grant(
        grant, "local.write_file",
        {"path": "/tmp/other.txt", "content": "one exact write"},
        scope="owner-a",
    ) is False
    # Failed validation consumes the grant, preventing a later replay.
    assert execution_policy.consume_execution_grant(
        grant, "local.write_file", payload, scope="owner-a"
    ) is False
