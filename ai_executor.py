"""Small request-scoped execution layer for the internal AI pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from ai_request import AIRequest
from llm_provider import LLMProvider
from model_router import ModelRouter, RouteDecision


class AIExecutionError(Exception):
    """Raised when an internal request cannot be executed safely."""


@dataclass(frozen=True)
class AIResult:
    """Normalized result of one non-streaming internal AI execution."""

    content: str
    model: str
    provider: str
    route_reason: str


class AIExecutor:
    """Route and execute one request without provider-specific HTTP logic."""

    def __init__(
        self,
        router: ModelRouter,
        provider: LLMProvider,
        provider_name: str = "openrouter",
    ) -> None:
        self.router = router
        self.provider = provider
        self.provider_name = provider_name

    def execute(self, request: AIRequest) -> AIResult:
        """Execute a normal chat request and normalize its internal result."""
        decision = self._decision_for(request)
        content = self.provider.chat(
            list(request.messages),
            temperature=request.temperature,
            model=decision.model,
        )
        return AIResult(
            content=content,
            model=decision.model,
            provider=decision.provider,
            route_reason=decision.reason,
        )

    def execute_stream(self, request: AIRequest) -> Iterator[str]:
        """Yield provider chunks incrementally for one streaming request."""
        decision = self._decision_for(request)
        yield from self.provider.stream(
            list(request.messages),
            temperature=request.temperature,
            model=decision.model,
        )

    def _decision_for(self, request: AIRequest) -> RouteDecision:
        if not isinstance(request, AIRequest):
            raise AIExecutionError("expected AIRequest")
        if not request.messages:
            raise AIExecutionError("request requires messages")

        decision = self.router.route(request)
        if not isinstance(decision, RouteDecision):
            raise AIExecutionError("router returned an invalid route")
        if not decision.provider or not decision.model:
            raise AIExecutionError("route requires provider and model")
        if decision.provider != self.provider_name:
            raise AIExecutionError("no provider is configured for this route")
        return decision
