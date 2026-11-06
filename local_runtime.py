"""
local_runtime.py — supervises Oracle's Streamlit UI and persistent worker on macOS.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from local_config import load_local_environment


ROOT = Path(__file__).resolve().parent
STATE_DIR = Path.home() / ".personal_ai_oracle"
LOG_DIR = STATE_DIR / "logs"
PORT = os.environ.get("ORACLE_LOCAL_PORT", "8765")
STOPPING = False


def _log(message: str) -> None:
    print(f"[Oracle local runtime] {message}", flush=True)


def _on_signal(signum, _frame) -> None:
    global STOPPING
    STOPPING = True
    _log(f"received signal {signum}; stopping child processes")


def _is_on_ac_power() -> bool:
    try:
        result = subprocess.run(
            ["pmset", "-g", "batt"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return "AC Power" in result.stdout
    except Exception:
        return False


def _launch(name: str, args: list[str], log_path: Path) -> tuple[subprocess.Popen, object]:
    stream = log_path.open("a", encoding="utf-8")
    process = subprocess.Popen(
        args,
        cwd=str(ROOT),
        env=os.environ.copy(),
        stdin=subprocess.DEVNULL,
        stdout=stream,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    _log(f"started {name} pid={process.pid}")
    return process, stream


def _stop_process(name: str, process: subprocess.Popen | None, stream) -> None:
    if process is not None and process.poll() is None:
        _log(f"stopping {name} pid={process.pid}")
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    if stream is not None:
        stream.close()


def main() -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    load_local_environment()

    os.environ.setdefault("ORACLE_RUNTIME_MODE", "local")
    os.environ.setdefault("ORACLE_LOCAL_ACCESS", "full")
    os.environ.setdefault("ORACLE_DB_PATH", str(STATE_DIR / "oracle.db"))
    os.environ.setdefault("ORACLE_EXTERNAL_WORKER", "1")
    os.environ.setdefault("ORACLE_DEFAULT_PROVIDER", "openrouter")
    os.environ.setdefault("ORACLE_MAX_AGENT_STEPS", "12")

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    ui_args = [
        sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"),
        f"--server.address=127.0.0.1",
        f"--server.port={PORT}",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]
    worker_args = [sys.executable, str(ROOT / "worker.py")]

    processes: dict[str, tuple[subprocess.Popen, object]] = {}
    commands = {
        "streamlit": (ui_args, LOG_DIR / "streamlit.log"),
        "worker": (worker_args, LOG_DIR / "worker.log"),
    }

    caffeinate = None
    if (
        sys.platform == "darwin"
        and os.environ.get("ORACLE_PREVENT_IDLE_SLEEP", "1").strip().lower() not in {"0", "false", "no"}
        and _is_on_ac_power()
        and Path("/usr/bin/caffeinate").exists()
    ):
        try:
            caffeinate = subprocess.Popen(
                ["/usr/bin/caffeinate", "-s"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _log("AC power detected; preventing idle system sleep while Oracle is running")
        except Exception as exc:
            _log(f"caffeinate could not start: {exc}")

    try:
        for name, (args, log_path) in commands.items():
            processes[name] = _launch(name, args, log_path)

        while not STOPPING:
            for name, (args, log_path) in commands.items():
                current, stream = processes[name]
                exit_code = current.poll()
                if exit_code is not None and not STOPPING:
                    stream.close()
                    _log(f"{name} exited with code {exit_code}; restarting in 3 seconds")
                    time.sleep(3)
                    if not STOPPING:
                        processes[name] = _launch(name, args, log_path)
            time.sleep(2)
    finally:
        for name, (process, stream) in processes.items():
            _stop_process(name, process, stream)
        if caffeinate is not None and caffeinate.poll() is None:
            caffeinate.terminate()
            try:
                caffeinate.wait(timeout=3)
            except subprocess.TimeoutExpired:
                caffeinate.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
