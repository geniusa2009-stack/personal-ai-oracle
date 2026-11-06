"""
model_router.py — Provider and model selection for local multi-model Oracle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ai_request import AIRequest


@dataclass(frozen=True)
class RouteDecision:
    provider: str
    model: str
    reason: str


class ModelRouter:
    """Deterministic selection of a provider/model pair for each AI request."""

    def __init__(
        self,
        default_provider: str,
        default_model: str,
        category_models: Mapping[str, str] | None = None,
        category_providers: Mapping[str, str] | None = None,
    ) -> None:
        self.default_provider = default_provider
        self.default_model = default_model
        self.category_models = dict(category_models or {})
        self.category_providers = dict(category_providers or {})

    def route(
        self,
        request: AIRequest | None = None,
        *,
        task_type: str | None = None,
        requested_model: str | None = None,
        requested_provider: str | None = None,
    ) -> RouteDecision:
        """Select a route without performing a provider call."""
        if request is not None:
            task_type = request.task_type
            requested_model = request.requested_model
            requested_provider = request.requested_provider

        if requested_provider or requested_model:
            return RouteDecision(
                provider=requested_provider or self.default_provider,
                model=requested_model or self.category_models.get(task_type or "", self.default_model),
                reason="explicit_route",
            )

        if task_type:
            selected_model = self.category_models.get(task_type)
            selected_provider = self.category_providers.get(task_type)
            if selected_model or selected_provider:
                return RouteDecision(
                    provider=selected_provider or self.default_provider,
                    model=selected_model or self.default_model,
                    reason=task_type,
                )

        return RouteDecision(
            provider=self.default_provider,
            model=self.default_model,
            reason="default",
        )
