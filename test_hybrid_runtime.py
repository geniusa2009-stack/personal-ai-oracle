from __future__ import annotations

import hashlib
import ipaddress
import os

import pytest

import cloud_control
import web_browser


def test_cloud_control_only_accepts_known_remote_tools():
    assert "local.read_file" in cloud_control.ALLOWED_REMOTE_TOOLS
    assert "web.navigate" in cloud_control.ALLOWED_REMOTE_TOOLS
    assert "local.run_command" in cloud_control.ALLOWED_REMOTE_TOOLS
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
