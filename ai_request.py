"""
ai_request.py — Minimal internal request/context contracts for Oracle.

These immutable structures carry request data between internal layers. They do
not retrieve memory, call services, execute tools, or contain provider details.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping, Sequence


@dataclass(frozen=True)
class Context:
    """Immutable request context supplied to the internal pipeline."""

    metadata: Mapping[str, object] = field(default_factory=dict)
    constraints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
        object.__setattr__(self, "constraints", tuple(self.constraints))


@dataclass(frozen=True)
class AIRequest:
    """Immutable, request-scoped internal representation of an AI call."""

    messages: tuple[dict, ...]
    temperature: float
    requested_model: str | None = None
    task_type: str | None = None
    streaming: bool = False
    context: Context = field(default_factory=Context)

    def __post_init__(self) -> None:
        normalized_messages = tuple(dict(message) for message in self.messages)
        object.__setattr__(self, "messages", normalized_messages)
