"""Request-scoped multi-provider execution for the Oracle AI pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Mapping

from ai_request import AIRequest
from llm_provider import LLMProvider
from model_router import ModelRouter, RouteDecision


class AIExecutionError(Exception):
    """Raised when an internal request cannot be executed."""


@dataclass(frozen=True)
class AIResult:
    content: str
    model: str
    provider: str
    route_reason: str


class AIExecutor:
    """Resolve each request to its matching provider adapter and model."""

    def __init__(
        self,
        router: ModelRouter,
        provider: LLMProvider,
        provider_name: str = "openrouter",
        providers: Mapping[str, LLMProvider] | None = None,
    ) -> None:
        self.router = router
        self.provider = provider
        self.provider_name = provider_name
        self.providers = dict(providers or {provider_name: provider})
        self.providers.setdefault(provider_name, provider)

    def execute(self, request: AIRequest) -> AIResult:
        decision = self._decision_for(request)
        if request.streaming:
            raise AIExecutionError("streaming request must use execute_stream")
        selected = self._provider_for(decision)
        chat_options = {
            "temperature": request.temperature,
            "model": decision.model,
        }
        if request.response_format is not None:
            chat_options["response_format"] = request.to_response_format()
        content = selected.chat(request.to_messages(), **chat_options)
        return AIResult(
            content=content,
            model=decision.model,
            provider=decision.provider,
            route_reason=decision.reason,
        )

    def execute_stream(self, request: AIRequest) -> Iterator[str]:
        decision = self._decision_for(request)
        if not request.streaming:
            raise AIExecutionError("execute_stream requires a streaming request")
        selected = self._provider_for(decision)
        yield from selected.stream(
            request.to_messages(),
            temperature=request.temperature,
            model=decision.model,
        )

    def _provider_for(self, decision: RouteDecision) -> LLMProvider:
        selected = self.providers.get(decision.provider)
        if selected is None:
            raise AIExecutionError(
                f"provider '{decision.provider}' is not configured; check its local API key/settings"
            )
        return selected

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
        return decision
