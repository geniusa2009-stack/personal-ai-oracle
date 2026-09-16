import json
from unittest.mock import Mock, patch

import ai_core
from llm_provider import OpenRouterProvider, OracleProviderError


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
