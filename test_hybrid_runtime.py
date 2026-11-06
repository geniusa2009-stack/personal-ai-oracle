from __future__ import annotations

import hashlib
import ipaddress
import os

import pytest

import cloud_control
import web_browser


def test_cloud_control_only_accepts_read_only_remote_tools():
    assert "local.read_file" in cloud_control.ALLOWED_REMOTE_TOOLS
    assert "local.list_directory" in cloud_control.ALLOWED_REMOTE_TOOLS
    assert "web.navigate" in cloud_control.ALLOWED_REMOTE_TOOLS
    for tool_id in (
        "local.write_file", "local.move_path", "local.delete_path",
        "local.run_command", "local.open_app",
    ):
        assert tool_id not in cloud_control.ALLOWED_REMOTE_TOOLS
    assert "os.exec" not in cloud_control.ALLOWED_REMOTE_TOOLS
    assert "shell" not in cloud_control.ALLOWED_REMOTE_TOOLS


def test_cloud_tokens_are_hashed():
    raw = "a-long-device-token-that-should-not-be-stored"
    assert cloud_control._hash_token(raw) == hashlib.sha256(raw.encode()).hexdigest()
    assert raw not in cloud_control._hash_token(raw)


def test_cloud_payload_size_is_bounded():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        cloud_control._json_size({"content": "x" * (cloud_control.MAX_JOB_BYTES + 10)}, 100)
    assert error.value.status_code == 413


def test_browser_rejects_non_http_schemes():
    for value in ("file:///etc/passwd", "javascript:alert(1)", "data:text/html,hello"):
        with pytest.raises(ValueError):
            web_browser._validate_url(value)


def test_browser_rejects_embedded_credentials():
    with pytest.raises(ValueError):
        web_browser._validate_url("https://user:password@example.com")


def test_browser_allows_public_http_url(monkeypatch):
    monkeypatch.setattr(web_browser.socket, "getaddrinfo", lambda *args, **kwargs: [
        (None, None, None, None, ("93.184.216.34", 443))
    ])
    monkeypatch.setenv("ORACLE_BROWSER_ALLOW_PRIVATE_NETWORK", "0")
    assert web_browser._validate_url("https://example.com") == "https://example.com"


def test_browser_rejects_loopback_dns(monkeypatch):
    monkeypatch.setattr(web_browser.socket, "getaddrinfo", lambda *args, **kwargs: [
        (None, None, None, None, ("127.0.0.1", 443))
    ])
    monkeypatch.setenv("ORACLE_BROWSER_ALLOW_PRIVATE_NETWORK", "0")
    with pytest.raises(PermissionError):
        web_browser._validate_url("https://internal.example")



def test_cloud_job_round_trip_and_device_pairing(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("ORACLE_CLOUD_DB_PATH", str(tmp_path / "control.db"))
    monkeypatch.setenv("ORACLE_CLOUD_CONTROL_TOKEN", "c" * 48)
    monkeypatch.setenv("ORACLE_CLOUD_ENROLLMENT_TOKEN", "e" * 48)
    cloud_control.init_db()

    with TestClient(cloud_control.app) as client:
        paired = client.post(
            "/v1/devices/pair",
            headers={"X-Enrollment-Token": "e" * 48},
            json={"name": "Test Mac"},
        )
        assert paired.status_code == 200
        device_token = paired.json()["device_token"]
        assert len(device_token) >= 48

        control_headers = {"Authorization": "Bearer " + "c" * 48}
        agent_headers = {"Authorization": "Bearer " + device_token}
        queued = client.post(
            "/v1/jobs",
            headers=control_headers,
            json={
                "tool_id": "local.read_file",
                "input": {"path": "/tmp/example.txt"},
                "task": "Read a test file",
                "idempotency_key": "test-job-001",
            },
        )
        assert queued.status_code == 200
        job_id = queued.json()["job_id"]

        claimed = client.get(
            "/v1/agent/jobs/next",
            headers=agent_headers,
            params={"wait_seconds": 0},
        )
        assert claimed.status_code == 200
        job = claimed.json()
        assert job["job_id"] == job_id
        assert job["input"] == {"path": "/tmp/example.txt"}

        completed = client.post(
            f"/v1/agent/jobs/{job_id}/result",
            headers=agent_headers,
            json={
                "lease_token": job["lease_token"],
                "status": "success",
                "result": {"status": "success", "result": "done"},
            },
        )
        assert completed.status_code == 200

        final = client.get(f"/v1/jobs/{job_id}", headers=control_headers)
        assert final.status_code == 200
        assert final.json()["status"] == "success"
        assert final.json()["result"]["result"] == "done"


def test_cloud_api_rejects_remote_mutation_until_mac_approval_exchange_exists(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("ORACLE_CLOUD_DB_PATH", str(tmp_path / "remote-mutation.db"))
    monkeypatch.setenv("ORACLE_CLOUD_CONTROL_TOKEN", "c" * 48)
    with TestClient(cloud_control.app) as client:
        response = client.post(
            "/v1/jobs",
            headers={"Authorization": "Bearer " + "c" * 48},
            json={
                "tool_id": "local.delete_path",
                "input": {"path": "/tmp/example", "recursive": True},
                "task": "delete one path",
            },
        )
        assert response.status_code == 422


def test_cloud_api_rejects_unknown_remote_tool(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("ORACLE_CLOUD_DB_PATH", str(tmp_path / "control.db"))
    monkeypatch.setenv("ORACLE_CLOUD_CONTROL_TOKEN", "c" * 48)
    with TestClient(cloud_control.app) as client:
        response = client.post(
            "/v1/jobs",
            headers={"Authorization": "Bearer " + "c" * 48},
            json={"tool_id": "shell.execute", "input": {"command": "anything"}},
        )
        assert response.status_code == 422



def test_cloud_result_body_expires_after_retention_window(tmp_path, monkeypatch):
    import time

    monkeypatch.setenv("ORACLE_CLOUD_DB_PATH", str(tmp_path / "retention.db"))
    monkeypatch.setenv("ORACLE_CLOUD_RESULT_RETENTION_HOURS", "24")
    monkeypatch.setenv("ORACLE_CLOUD_JOB_RETENTION_DAYS", "7")
    cloud_control.init_db()
    now = time.time()
    with cloud_control._db_connection() as connection:
        connection.execute(
            """INSERT INTO jobs(
                job_id,tool_id,tool_input,task,status,created_at,updated_at,result_json
            ) VALUES(?,?,?,?,?,?,?,?)""",
            (
                "retention-test",
                "local.read_file",
                "{}",
                "retention test",
                "success",
                now - 3600,
                now - 25 * 3600,
                '{"private":"example"}',
            ),
        )
    cloud_control.init_db()
    with cloud_control._db_connection() as connection:
        row = connection.execute(
            "SELECT result_json FROM jobs WHERE job_id='retention-test'"
        ).fetchone()
    assert row["result_json"] is None


def test_cloud_agent_bounds_oversized_tool_output():
    from cloud_agent import _bound_result

    result = _bound_result({"name": "local.read_file", "status": "success", "result": "x" * 100_000})
    assert result.get("truncated") is True
    assert len(__import__("json").dumps(result).encode("utf-8")) < 65_536
