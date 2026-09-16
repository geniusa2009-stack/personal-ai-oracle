"""
model_router.py — Small deterministic model-selection layer.

The router chooses a model configuration only. It does not execute requests,
manage context or memory, call tools, or contain provider-specific HTTP logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ai_request import AIRequest


@dataclass(frozen=True)
class RouteDecision:
    """Inspectable result of a single request-scoped routing decision."""

    provider: str
    model: str
    reason: str


class ModelRouter:
    """Deterministic, provider-agnostic model selection."""

    def __init__(
        self,
        default_provider: str,
        default_model: str,
        category_models: Mapping[str, str] | None = None,
    ) -> None:
        self.default_provider = default_provider
        self.default_model = default_model
        self.category_models = dict(category_models or {})

    def route(self, request: AIRequest | None = None, *, task_type: str | None = None,
              requested_model: str | None = None) -> RouteDecision:
        """Select a model from a request without making a provider/API call."""
        if request is not None:
            task_type = request.task_type
            requested_model = request.requested_model

        if requested_model:
            return RouteDecision(
                provider=self.default_provider,
                model=requested_model,
                reason="explicit_model",
            )

        if task_type:
            selected_model = self.category_models.get(task_type)
            if selected_model:
                return RouteDecision(
                    provider=self.default_provider,
                    model=selected_model,
                    reason=task_type,
                )

        return RouteDecision(
            provider=self.default_provider,
            model=self.default_model,
            reason="default",
        )
