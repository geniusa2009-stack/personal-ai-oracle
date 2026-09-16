import json
from unittest.mock import Mock, patch

import ai_core
from llm_provider import OpenRouterProvider, OracleProviderError
from model_router import ModelRouter, RouteDecision


class FakeStreamResponse:
    def __init__(self, lines):
        self.lines = lines

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        return None

    def iter_lines(self):
        return self.lines


def test_provider_reads_existing_configuration(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "test/model")
    provider = OpenRouterProvider()
    assert provider.api_key == "test-key"
    assert provider.model == "test/model"
    assert provider.url == OpenRouterProvider.DEFAULT_URL


def test_provider_uses_default_model(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    assert OpenRouterProvider().model == "deepseek/deepseek-chat"


def test_provider_chat_builds_request_and_parses_response(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    provider = OpenRouterProvider()
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"choices": [{"message": {"content": " hello "}}]}

    with patch("llm_provider.requests.post", return_value=response) as post:
        result = provider.chat([{"role": "user", "content": "hi"}], temperature=0.4)

    assert result == "hello"
    kwargs = post.call_args.kwargs
    assert kwargs["timeout"] == 120
    assert kwargs["headers"]["Authorization"] == "Bearer test-key"
    payload = json.loads(kwargs["data"])
    assert payload["model"] == "deepseek/deepseek-chat"
    assert payload["temperature"] == 0.4
    assert payload["messages"] == [{"role": "user", "content": "hi"}]


def test_provider_request_scoped_model_override_does_not_mutate_configuration(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "default/model")
    provider = OpenRouterProvider()
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"choices": [{"message": {"content": "answer"}}]}

    with patch("llm_provider.requests.post", return_value=response) as post:
        assert provider.chat([], model="request/model") == "answer"

    payload = json.loads(post.call_args.kwargs["data"])
    assert payload["model"] == "request/model"
    assert provider.model == "default/model"
    assert __import__("os").environ["OPENROUTER_MODEL"] == "default/model"


def test_provider_stream_parses_sse_and_uses_timeout(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    provider = OpenRouterProvider()
    lines = [
        b'data: {"choices":[{"delta":{"content":"Hello"}}]}',
        b'data: {"choices":[{"delta":{"content":" world"}}]}',
        b'data: [DONE]',
    ]

    with patch(
        "llm_provider.requests.post",
        return_value=FakeStreamResponse(lines),
    ) as post:
        result = list(provider.stream([{"role": "user", "content": "hi"}], temperature=0.8))

    assert result == ["Hello", " world"]
    kwargs = post.call_args.kwargs
    assert kwargs["stream"] is True
    assert kwargs["timeout"] == 180
    payload = json.loads(kwargs["data"])
    assert payload["stream"] is True
    assert payload["temperature"] == 0.8


def test_provider_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    provider = OpenRouterProvider()
    try:
        provider.chat([])
    except OracleProviderError as exc:
        assert "missing OpenRouter API key" in str(exc)
    else:
        raise AssertionError("Expected OracleProviderError")


def test_model_router_default_route(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL", "deepseek/deepseek-chat")
    router = ModelRouter(default_provider="openrouter", default_model="deepseek/deepseek-chat")
    decision = router.route()
    assert decision == RouteDecision(
        provider="openrouter",
        model="deepseek/deepseek-chat",
        reason="default",
    )


def test_model_router_is_deterministic():
    router = ModelRouter(
        default_provider="openrouter",
        default_model="default/model",
        category_models={"reasoning": "reasoning/model"},
    )
    first = router.route(task_type="reasoning")
    second = router.route(task_type="reasoning")
    assert first == second


def test_model_router_explicit_model_selection():
    router = ModelRouter(default_provider="openrouter", default_model="default/model")
    decision = router.route(requested_model="requested/model")
    assert decision == RouteDecision(
        provider="openrouter",
        model="requested/model",
        reason="explicit_model",
    )


def test_model_router_rule_based_category():
    router = ModelRouter(
        default_provider="openrouter",
        default_model="default/model",
        category_models={"reasoning": "reasoning/model"},
    )
    decision = router.route(task_type="reasoning")
    assert decision.model == "reasoning/model"
    assert decision.reason == "reasoning"


def test_model_router_unknown_category_uses_default():
    router = ModelRouter(
        default_provider="openrouter",
        default_model="default/model",
        category_models={"reasoning": "reasoning/model"},
    )
    decision = router.route(task_type="unknown")
    assert decision.model == "default/model"
    assert decision.reason == "default"


def test_model_router_has_no_http_dependency():
    router = ModelRouter(default_provider="openrouter", default_model="default/model")
    with patch("llm_provider.requests.post") as post:
        router.route()
        post.assert_not_called()


def test_legacy_has_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert ai_core.has_key() is False
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    assert ai_core.has_key() is True


def test_legacy_system_prompt_behavior():
    assert ai_core.system_prompt("friendly", "do this") == (
        ai_core.BASE + ai_core.PERSONAS["friendly"] + "\nمهمتك تحديداً: do this"
    )
    assert ai_core.system_prompt("unknown") == ai_core.BASE + ai_core.PERSONAS["friendly"]


def test_legacy_openrouter_url_symbol():
    assert ai_core.OPENROUTER_URL == OpenRouterProvider.DEFAULT_URL
    assert ai_core.OPENROUTER_URL == "https://openrouter.ai/api/v1/chat/completions"


def test_legacy_llm_forwards_arguments(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    with patch.object(ai_core.OpenRouterProvider, "chat", return_value="answer") as chat:
        result = ai_core.llm("do this", "  user input  ", "coach", 0.5)

    assert result == "answer"
    chat.assert_called_once_with(
        [
            {"role": "system", "content": ai_core.system_prompt("coach", "do this")},
            {"role": "user", "content": "user input"},
        ],
        temperature=0.5,
        model="deepseek/deepseek-chat",
    )


def test_legacy_llm_missing_key_behavior(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    result = ai_core.llm("instruction", "input", "friendly", 0.7)
    assert result == "⚠️ أضف مفتاح OpenRouter في القائمة الجانبية لتشغيل هذه الميزة."


def test_legacy_llm_returns_string(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    with patch.object(ai_core.OpenRouterProvider, "chat", return_value="answer") as chat:
        result = ai_core.llm("instruction", "input", "coach", 0.5)
    assert isinstance(result, str)
    assert result == "answer"
    chat.assert_called_once()


def test_legacy_stream_remains_iterable(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    with patch.object(ai_core.OpenRouterProvider, "stream", return_value=iter(["a", "b"])):
        result = ai_core.stream([{"role": "user", "content": "hi"}])
        assert hasattr(result, "__iter__")
        assert list(result) == ["a", "b"]


def test_legacy_stream_provider_error_behavior(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    def raise_provider_error(*args, **kwargs):
        raise OracleProviderError("provider failed")

    with patch.object(ai_core.OpenRouterProvider, "stream", side_effect=raise_provider_error):
        result = ai_core.stream([{"role": "user", "content": "hi"}])
        assert hasattr(result, "__iter__")
        assert list(result) == ["\n\n(تعذّر البثّ: provider failed)"]
