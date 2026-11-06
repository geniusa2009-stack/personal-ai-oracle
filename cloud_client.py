"""Synchronous client used by the hosted dashboard to dispatch Mac-local work."""

from __future__ import annotations

import os
import time
import uuid
from typing import Any

import requests


class CloudAgentUnavailable(RuntimeError):
    pass


def execute_remote_tool(
    tool_id: str,
    tool_input: dict[str, Any] | str,
    *,
    task: str = "",
    timeout_seconds: int = 360,
) -> dict[str, Any]:
    base_url = os.environ.get("ORACLE_CLOUD_API_URL", "").rstrip("/")
    token = os.environ.get("ORACLE_CLOUD_CONTROL_TOKEN", "")
    if not base_url or len(token) < 32:
        raise CloudAgentUnavailable(
            "Cloud-to-Mac bridge is not configured. Set ORACLE_CLOUD_API_URL and "
            "ORACLE_CLOUD_CONTROL_TOKEN on the cloud web service."
        )
    if not base_url.startswith("https://") and not base_url.startswith(
        ("http://127.0.0.1", "http://localhost")
    ):
        raise CloudAgentUnavailable("Cloud API must use HTTPS outside local development.")
    if isinstance(tool_input, str):
        import json
        try:
            tool_input = json.loads(tool_input)
        except ValueError as exc:
            raise ValueError("Remote tool input must be valid JSON") from exc
    if not isinstance(tool_input, dict):
        raise ValueError("Remote tool input must be a JSON object")

    headers = {"Authorization": f"Bearer {token}"}
    response = requests.post(
        f"{base_url}/v1/jobs",
        headers=headers,
        json={
            "tool_id": tool_id,
            "input": tool_input,
            "task": task[:12000],
            "idempotency_key": str(uuid.uuid4()),
        },
        timeout=(10, 30),
    )
    response.raise_for_status()
    job_id = response.json().get("job_id")
    if not isinstance(job_id, str):
        raise CloudAgentUnavailable("Cloud API did not return a job identifier.")

    deadline = time.monotonic() + max(5, min(timeout_seconds, 600))
    while time.monotonic() < deadline:
        status_response = requests.get(
            f"{base_url}/v1/jobs/{job_id}",
            headers=headers,
            timeout=(10, 20),
        )
        status_response.raise_for_status()
        job = status_response.json()
        status = job.get("status")
        if status in {"success", "error", "blocked"}:
            result = job.get("result")
            if isinstance(result, dict):
                result.setdefault("status", status)
                result.setdefault("tool_id", tool_id)
                return result
            return {"name": tool_id, "status": status, "result": result}
        if status == "queued" and time.monotonic() + 5 >= deadline:
            break
        time.sleep(1.5)
    raise CloudAgentUnavailable(
        f"Mac agent did not complete {tool_id} within {timeout_seconds} seconds. "
        "Check that the Mac is awake and the Oracle agent is connected."
    )



def list_devices() -> list[dict[str, Any]]:
    base_url = os.environ.get("ORACLE_CLOUD_API_URL", "").rstrip("/")
    token = os.environ.get("ORACLE_CLOUD_CONTROL_TOKEN", "")
    if not base_url or len(token) < 32:
        raise CloudAgentUnavailable("Cloud control API is not configured.")
    response = requests.get(
        f"{base_url}/v1/devices",
        headers={"Authorization": f"Bearer {token}"},
        timeout=(10, 20),
    )
    response.raise_for_status()
    payload = response.json()
    devices = payload.get("devices", [])
    return devices if isinstance(devices, list) else []
