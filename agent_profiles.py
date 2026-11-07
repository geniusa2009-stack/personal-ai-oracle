"""Named model profiles for Oracle's specialist agents.

Each role can choose a different provider and model. Settings are supplied by
the user's private local environment file; no model key is committed to Git.
"""

from __future__ import annotations

import os
from typing import Any


ROLE_DEFAULTS = {
    "assistant": ("ORACLE_ASSISTANT", "fast", 0.55),
    "planner": ("ORACLE_AGENT_PLANNER", "reasoning", 0.15),
    "executor": ("ORACLE_AGENT_EXECUTOR", "fast", 0.25),
    "researcher": ("ORACLE_AGENT_RESEARCHER", "research", 0.2),
    "coder": ("ORACLE_AGENT_CODER", "coding", 0.15),
    "writer": ("ORACLE_AGENT_WRITER", "writing", 0.75),
    "reviewer": ("ORACLE_AGENT_REVIEWER", "reasoning", 0.1),
}


def _env_first(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None


def resolve_profile(role: str) -> dict[str, Any]:
    """Resolve a named agent role to a provider/model/temperature profile."""
    normalized = (role or "").strip().lower()
    if normalized not in ROLE_DEFAULTS:
        raise ValueError(f"unknown Oracle agent role: {normalized}")

    prefix, task_type, default_temperature = ROLE_DEFAULTS[normalized]
    provider = _env_first(
        f"{prefix}_PROVIDER",
        f"ORACLE_PROVIDER_{task_type.upper()}",
        "ORACLE_DEFAULT_PROVIDER",
    ) or "openrouter"
    provider_model_env = {
        "openrouter": "OPENROUTER_MODEL",
        "openai": "OPENAI_MODEL",
        "gemini": "GEMINI_MODEL",
        "ollama": "OLLAMA_MODEL",
    }.get(provider, "")
    default_model_env = (
        "ORACLE_DEFAULT_MODEL"
        if provider == (os.environ.get("ORACLE_DEFAULT_PROVIDER", "openrouter").strip().lower())
        else ""
    )
    model = _env_first(
        f"{prefix}_MODEL",
        f"ORACLE_MODEL_{task_type.upper()}",
        provider_model_env,
        default_model_env,
    )
    temperature_value = _env_first(f"{prefix}_TEMPERATURE")
    try:
        temperature = float(temperature_value) if temperature_value else default_temperature
    except ValueError:
        temperature = default_temperature
    temperature = max(0.0, min(2.0, temperature))

    return {
        "role": normalized,
        "task_type": task_type,
        "provider": provider,
        "model": model,
        "temperature": temperature,
    }


def profile_catalog() -> list[dict[str, Any]]:
    """Return the locally configured role map, suitable for the settings UI."""
    return [resolve_profile(role) for role in ROLE_DEFAULTS]
