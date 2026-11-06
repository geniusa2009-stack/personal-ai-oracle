"""
ai_request.py — Immutable internal request/context contracts for Oracle.
"""

from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping


def _freeze(value):
    """Recursively copy and freeze JSON-like request data."""
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    return deepcopy(value)


def _thaw(value):
    """Return provider-friendly mutable copies of frozen request data."""
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    if isinstance(value, frozenset):
        return [_thaw(item) for item in value]
    return deepcopy(value)


@dataclass(frozen=True)
class Context:
    """Immutable request context supplied to the internal pipeline."""

    metadata: Mapping[str, object] = field(default_factory=dict)
    constraints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.metadata, Mapping):
            raise ValueError("context metadata must be a mapping")
        constraints = tuple(self.constraints)
        if any(not isinstance(item, str) for item in constraints):
            raise ValueError("context constraints must contain only strings")
        object.__setattr__(self, "metadata", _freeze(self.metadata))
        object.__setattr__(self, "constraints", constraints)


@dataclass(frozen=True)
class AIRequest:
    """Immutable, request-scoped internal representation of an AI call."""

    messages: tuple[Mapping[str, object], ...]
    temperature: float
    requested_model: str | None = None
    task_type: str | None = None
    streaming: bool = False
    context: Context = field(default_factory=Context)

    def __post_init__(self) -> None:
        if not isinstance(self.messages, (list, tuple)):
            raise ValueError("messages must be a list or tuple")
        if (
            isinstance(self.temperature, bool)
            or not isinstance(self.temperature, (int, float))
            or not math.isfinite(float(self.temperature))
            or not 0.0 <= float(self.temperature) <= 2.0
        ):
            raise ValueError("temperature must be a finite number from 0 to 2")

        normalized_messages = []
        for message in self.messages:
            if not isinstance(message, Mapping):
                raise ValueError("each message must be a mapping")
            frozen_message = _freeze(message)
            role = frozen_message.get("role")
            if not isinstance(role, str) or not role.strip():
                raise ValueError("each message requires a non-empty role")
            normalized_messages.append(frozen_message)

        object.__setattr__(self, "messages", tuple(normalized_messages))
        if not isinstance(self.context, Context):
            raise ValueError("context must be a Context instance")

    def to_messages(self) -> list[dict]:
        """Create fresh provider-compatible message dictionaries."""
        return [_thaw(message) for message in self.messages]
