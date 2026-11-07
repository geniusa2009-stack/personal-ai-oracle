"""Outbound-polling Mac agent that connects the private cloud to local tools."""

from __future__ import annotations

import json
import os
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any

import requests

from local_config import load_local_environment

REMOTE_TOOLS = {
    "local.list_directory",
    "local.read_file",
    "local.write_file",
    "local.find_files",
    "local.run_command",
    "local.open_app",
    "local.get_system_info",
    "local.list_processes",
    "local.list_applications",
    "local.get_mac_intelligence_status",
    "web.search",
    "web.navigate",
    "web.extract",
    "web.links",
    "web.open_browser",
}
STOPPING = False


def _on_signal(_signum, _frame) -> None:
    global STOPPING
    STOPPING = True


def _base_url() -> str:
    value = os.environ.get("ORACLE_CLOUD_API_URL", "").strip().rstrip("/")
    if not value:
        raise RuntimeError("ORACLE_CLOUD_API_URL is required to run the cloud-connected Mac agent.")
    if not value.startswith("https://") and not value.startswith(
        ("http://127.0.0.1", "http://localhost")
    ):
        raise RuntimeError("The Mac agent requires HTTPS for non-local cloud endpoints.")
    return value


def _device_token_path() -> Path:
    return Path(
        os.environ.get(
            "ORACLE_DEVICE_TOKEN_FILE",
            str(Path.home() / ".personal_ai_oracle" / "device-token.json"),
        )
    ).expanduser()


def _pair_if_needed(base_url: str, session: requests.Session) -> str:
    token = os.environ.get("ORACLE_DEVICE_TOKEN", "").strip()
    if token:
        return token
    path = _device_token_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            token = data.get("device_token", "")
            if isinstance(token, str) and len(token) > 30:
                return token
        except (OSError, ValueError):
            pass

    enrollment = os.environ.get("ORACLE_CLOUD_ENROLLMENT_TOKEN", "")
    if len(enrollment) < 32:
        raise RuntimeError(
            "Pair this Mac once by setting ORACLE_CLOUD_ENROLLMENT_TOKEN, or provide "
            "ORACLE_DEVICE_TOKEN from the private cloud pairing response."
        )
    response = session.post(
        f"{base_url}/v1/devices/pair",
        headers={"X-Enrollment-Token": enrollment},
        json={"name": os.environ.get("ORACLE_DEVICE_NAME", "Personal MacBook")},
        timeout=(10, 30),
    )
    response.raise_for_status()
    data = response.json()
    token = data.get("device_token")
    if not isinstance(token, str) or len(token) < 30:
        raise RuntimeError("Cloud API returned an invalid device token.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"device_token": token}), encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)
    return token


def _execute(job: dict[str, Any]) -> dict[str, Any]:
    tool_id = job.get("tool_id")
    if tool_id not in REMOTE_TOOLS:
        return {"name": str(tool_id), "status": "blocked", "result": "Tool is not in the Mac agent allowlist."}
    payload = job.get("input")
    if not isinstance(payload, dict):
        return {"name": tool_id, "status": "error", "result": "Invalid remote tool payload."}

    if tool_id.startswith("local."):
        import mac_intelligence
        decision = mac_intelligence.authorize_remote_action(tool_id, payload)
        if not decision.get("allowed"):
            return {
                "name": tool_id,
                "status": "blocked",
                "result": "Mac-local policy blocked this remote action: " + str(decision.get("reason", "not_allowed")),
            }
        import local_tools
        return local_tools.execute(tool_id, payload)

    import web_browser
    return web_browser.execute(tool_id, payload)


def _heartbeat_loop(base_url: str, token: str, stop_event: threading.Event) -> None:
    """Keep the device presence fresh while a long local tool is executing."""
    with requests.Session() as heartbeat_session:
        heartbeat_session.headers.update({
            "Authorization": f"Bearer {token}",
            "User-Agent": "PersonalAIOracle-MacAgent/1.0",
        })
        while not stop_event.wait(20):
            try:
                heartbeat_session.post(
                    f"{base_url}/v1/agent/heartbeat",
                    timeout=(5, 10),
                ).raise_for_status()
            except requests.RequestException:
                # The main worker loop owns reconnect/backoff and reports connection failures.
                continue


def _bound_result(result: dict[str, Any], maximum_bytes: int = 50_000) -> dict[str, Any]:
    """Keep cloud result uploads below the API limit and avoid giant page/file payloads."""
    try:
        encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError):
        return {"name": str(result.get("name", "remote-tool")), "status": "error", "result": "Tool returned a non-serializable result."}
    if len(encoded) <= maximum_bytes:
        return result
    bounded = dict(result)
    value = bounded.get("result")
    if isinstance(value, str):
        bounded["result"] = value[:40_000] + "\\n[Output truncated before cloud upload.]"
    elif isinstance(value, dict):
        reduced = dict(value)
        if isinstance(reduced.get("text"), str):
            reduced["text"] = reduced["text"][:40_000] + "\\n[Output truncated before cloud upload.]"
        else:
            reduced = {"summary": str(value)[:40_000], "truncated": True}
        bounded["result"] = reduced
    else:
        bounded["result"] = "Output was too large and has been truncated."
    bounded["truncated"] = True
    try:
        bounded_size = len(json.dumps(bounded, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    except (TypeError, ValueError):
        bounded_size = maximum_bytes + 1
    if bounded_size > maximum_bytes:
        return {
            "name": str(result.get("name", "remote-tool")),
            "status": str(result.get("status", "error")),
            "result": "Output exceeded the safe cloud-upload limit and was truncated.",
            "truncated": True,
        }
    return bounded


def run_forever() -> int:
    global STOPPING
    load_local_environment()
    base_url = _base_url()
    session = requests.Session()
    session.headers.update({"User-Agent": "PersonalAIOracle-MacAgent/1.0"})
    session.verify = True
    token = _pair_if_needed(base_url, session)
    session.headers.update({"Authorization": f"Bearer {token}"})
    heartbeat_stop = threading.Event()
    heartbeat_thread = threading.Thread(
        target=_heartbeat_loop,
        args=(base_url, token, heartbeat_stop),
        name="oracle-cloud-heartbeat",
        daemon=True,
    )
    heartbeat_thread.start()
    print("[Oracle Mac Agent] Connected to private cloud control plane.", flush=True)

    while not STOPPING:
        try:
            session.post(f"{base_url}/v1/agent/heartbeat", timeout=(10, 20)).raise_for_status()
            response = session.get(
                f"{base_url}/v1/agent/jobs/next",
                params={"wait_seconds": 20},
                timeout=(10, 35),
            )
            response.raise_for_status()
            job = response.json()
            if not job.get("job_id"):
                continue
            lease_token = job.get("lease_token")
            result = _bound_result(_execute(job))
            status = result.get("status", "error")
            if status not in {"success", "error", "blocked"}:
                status = "error"
            session.post(
                f"{base_url}/v1/agent/jobs/{job['job_id']}/result",
                json={
                    "lease_token": lease_token,
                    "status": status,
                    "result": result,
                },
                timeout=(10, 30),
            ).raise_for_status()
        except requests.RequestException as exc:
            print(f"[Oracle Mac Agent] Cloud connection error: {type(exc).__name__}", file=sys.stderr, flush=True)
            time.sleep(5)
        except Exception as exc:
            print(f"[Oracle Mac Agent] Agent loop error: {type(exc).__name__}: {str(exc)[:300]}", file=sys.stderr, flush=True)
            time.sleep(3)
    heartbeat_stop.set()
    heartbeat_thread.join(timeout=2)
    session.close()
    return 0


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    raise SystemExit(run_forever())
