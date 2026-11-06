"""One-command local installer for Personal AI Oracle on macOS."""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
STATE = Path.home() / ".personal_ai_oracle"
ENV_FILE = STATE / ".env"


ENV_TEMPLATE = """# Personal AI Oracle — private local settings
# Add provider keys and model names here. Never commit this file.
ORACLE_DEFAULT_PROVIDER=openrouter
OPENROUTER_API_KEY=
OPENROUTER_MODEL=deepseek/deepseek-chat

OPENAI_API_KEY=
OPENAI_MODEL=
GEMINI_API_KEY=
GEMINI_MODEL=

ORACLE_OLLAMA_ENABLED=1
OLLAMA_BASE_URL=http://127.0.0.1:11434/v1
OLLAMA_MODEL=

# Each specialist agent can use a different provider and model.
ORACLE_AGENT_PLANNER_PROVIDER=ollama
ORACLE_AGENT_PLANNER_MODEL=
ORACLE_AGENT_EXECUTOR_PROVIDER=ollama
ORACLE_AGENT_EXECUTOR_MODEL=
ORACLE_AGENT_RESEARCHER_PROVIDER=gemini
ORACLE_AGENT_RESEARCHER_MODEL=
ORACLE_AGENT_CODER_PROVIDER=openai
ORACLE_AGENT_CODER_MODEL=
ORACLE_AGENT_WRITER_PROVIDER=openrouter
ORACLE_AGENT_WRITER_MODEL=
ORACLE_AGENT_REVIEWER_PROVIDER=openrouter
ORACLE_AGENT_REVIEWER_MODEL=

ORACLE_MAX_AGENT_STEPS=12
ORACLE_MEMORY_SCOPE=user:oracle-owner
ORACLE_LOCAL_PORT=8765
ORACLE_PREVENT_IDLE_SLEEP=1
SCAN_INTERVAL_HOURS=12
TAVILY_API_KEY=

# WhatsApp outbound/draft integration (optional).
WA_ACCESS_TOKEN=
WA_PHONE_NUMBER_ID=
WA_AUTO_REPLY=draft
"""


def _run(command: list[str], *, cwd: Path | None = None) -> None:
    print("$ " + " ".join(command), flush=True)
    subprocess.run(command, cwd=str(cwd or ROOT), check=True)


def main() -> int:
    if sys.platform != "darwin":
        print("This installer is for macOS only.", file=sys.stderr)
        return 2

    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / "logs").mkdir(parents=True, exist_ok=True)

    if not VENV.exists():
        _run([sys.executable, "-m", "venv", str(VENV)])
    python = VENV / "bin" / "python"
    pip = VENV / "bin" / "pip"

    _run([str(pip), "install", "--upgrade", "pip"])
    _run([str(pip), "install", "-r", str(ROOT / "requirements.txt")])

    if not ENV_FILE.exists():
        ENV_FILE.write_text(ENV_TEMPLATE, encoding="utf-8")
        os.chmod(ENV_FILE, 0o600)
        print(f"Created private settings file: {ENV_FILE}")
    else:
        os.chmod(ENV_FILE, 0o600)
        print(f"Kept existing settings file: {ENV_FILE}")

    _run([str(python), str(ROOT / "manage_launch_agent.py"), "install"])
    print("")
    print("Oracle is installed locally.")
    print("Dashboard: http://127.0.0.1:8765")
    print(f"Edit provider/model keys in: {ENV_FILE}")
    print("Restart the LaunchAgent after changing the settings file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
