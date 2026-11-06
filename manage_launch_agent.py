"""Install or remove Oracle's per-user macOS LaunchAgent."""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

from local_config import load_local_environment


LABEL = "com.personal-ai-oracle.local"
ROOT = Path(__file__).resolve().parent
STATE = Path.home() / ".personal_ai_oracle"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["/bin/launchctl", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def install() -> int:
    if sys.platform != "darwin":
        print("Oracle LaunchAgent installer runs on macOS only.", file=sys.stderr)
        return 2
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / "logs").mkdir(parents=True, exist_ok=True)
    PLIST.parent.mkdir(parents=True, exist_ok=True)

    load_local_environment()
    env = {
        "HOME": str(Path.home()),
        "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        "PYTHONPATH": str(ROOT),
        "ORACLE_RUNTIME_MODE": "local",
        "ORACLE_LOCAL_ACCESS": "full",
        "ORACLE_ENV_FILE": str(STATE / ".env"),
        "ORACLE_DB_PATH": str(STATE / "oracle.db"),
        "ORACLE_EXTERNAL_WORKER": "1",
        "ORACLE_DEFAULT_PROVIDER": os.environ.get("ORACLE_DEFAULT_PROVIDER", "openrouter"),
        "ORACLE_MAX_AGENT_STEPS": os.environ.get("ORACLE_MAX_AGENT_STEPS", "12"),
        "ORACLE_LOCAL_PORT": os.environ.get("ORACLE_LOCAL_PORT", "8765"),
        "ORACLE_WORKSPACE": os.environ.get("ORACLE_WORKSPACE", str(ROOT)),
        "ORACLE_PREVENT_IDLE_SLEEP": os.environ.get("ORACLE_PREVENT_IDLE_SLEEP", "1"),
    }
    venv_python = ROOT / ".venv" / "bin" / "python"
    runtime_python = str(venv_python if venv_python.exists() else Path(sys.executable))
    payload = {
        "Label": LABEL,
        "ProgramArguments": [runtime_python, str(ROOT / "local_runtime.py")],
        "WorkingDirectory": str(ROOT),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Background",
        "EnvironmentVariables": env,
        "StandardOutPath": str(STATE / "logs" / "launchd.log"),
        "StandardErrorPath": str(STATE / "logs" / "launchd-error.log"),
    }
    with PLIST.open("wb") as stream:
        plistlib.dump(payload, stream, sort_keys=False)
    os.chmod(PLIST, 0o600)

    uid = str(os.getuid())
    _launchctl("bootout", f"gui/{uid}", str(PLIST))
    bootstrap = _launchctl("bootstrap", f"gui/{uid}", str(PLIST))
    if bootstrap.returncode != 0:
        sys.stderr.write(bootstrap.stderr or bootstrap.stdout)
        return bootstrap.returncode
    _launchctl("enable", f"gui/{uid}/{LABEL}")
    print(f"Oracle LaunchAgent installed: {PLIST}")
    print("Local dashboard: http://127.0.0.1:8765")
    print(f"Logs: {STATE / 'logs'}")
    return 0


def uninstall() -> int:
    if sys.platform != "darwin":
        print("Oracle LaunchAgent installer runs on macOS only.", file=sys.stderr)
        return 2
    uid = str(os.getuid())
    result = _launchctl("bootout", f"gui/{uid}/{LABEL}")
    PLIST.unlink(missing_ok=True)
    if result.returncode != 0 and "Could not find specified service" not in result.stderr:
        sys.stderr.write(result.stderr or result.stdout)
        return result.returncode
    print("Oracle LaunchAgent stopped and removed.")
    return 0


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "install"
    raise SystemExit(uninstall() if action == "uninstall" else install())
