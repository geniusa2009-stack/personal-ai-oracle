"""Load Oracle's private local environment file without adding a runtime dependency."""

from __future__ import annotations

import os
from pathlib import Path


def load_local_environment(path: str | None = None) -> Path:
    """Load KEY=VALUE entries from the user's private Oracle .env file."""
    target = Path(path or os.environ.get(
        "ORACLE_ENV_FILE",
        str(Path.home() / ".personal_ai_oracle" / ".env"),
    )).expanduser()
    if not target.exists():
        return target

    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not key.replace("_", "").isalnum():
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)
    return target
