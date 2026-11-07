"""
model_router.py — Provider and model selection for local multi-model Oracle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ai_request import AIRequest


TASK_TIERS = {
    "fast": "fast",
    "writing": "balanced",
    "creative": "balanced",
    "reasoning": "deep",
    "coding": "deep",
    "research": "deep",
}


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
        tier_models: Mapping[str, str] | None = None,
        tier_providers: Mapping[str, str] | None = None,
    ) -> None:
        self.default_provider = default_provider
        self.default_model = default_model
        self.category_models = dict(category_models or {})
        self.category_providers = dict(category_providers or {})
        self.tier_models = dict(tier_models or {})
        self.tier_providers = dict(tier_providers or {})

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
            if requested_provider and requested_model:
                reason = "explicit_route"
            elif requested_provider:
                reason = "explicit_provider"
            else:
                reason = "explicit_model"
            return RouteDecision(
                provider=requested_provider or self.default_provider,
                model=requested_model or self.category_models.get(task_type or "", self.default_model),
                reason=reason,
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

        # Tier policies are an explicit configuration layer. They never trigger
        # implicit provider fallback, which could silently change privacy or cost.
        tier = TASK_TIERS.get(task_type or "", "balanced")
        tier_model = self.tier_models.get(tier)
        tier_provider = self.tier_providers.get(tier)
        if tier_model or tier_provider:
            return RouteDecision(
                provider=tier_provider or self.default_provider,
                model=tier_model or self.default_model,
                reason=f"tier:{tier}",
            )

        return RouteDecision(
            provider=self.default_provider,
            model=self.default_model,
            reason="default",
        )
