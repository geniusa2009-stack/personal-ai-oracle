import json
from unittest.mock import Mock, patch

import pytest

import agent_profiles
from ai_executor import AIExecutor
from ai_request import AIRequest
from llm_provider import (
    OpenAICompatibleProvider,
    OpenRouterProvider,
    build_provider,
)
from model_router import ModelRouter


def test_openai_provider_uses_configured_key_and_endpoint(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("OPENAI_MODEL", "openai-model")
    provider = build_provider("openai")

    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.api_key == "test-openai-key"
    assert provider.model == "openai-model"
    assert provider.url == "https://api.openai.com/v1/chat/completions"


def test_gemini_provider_uses_openai_compatible_endpoint(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-model")
    provider = build_provider("gemini")

    assert provider.api_key == "test-gemini-key"
    assert provider.model == "gemini-model"
    assert provider.url == (
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    )


def test_ollama_provider_defaults_to_localhost_without_cloud_key(monkeypatch):
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    monkeypatch.setenv("OLLAMA_MODEL", "local-model")
    provider = build_provider("ollama")

    assert provider.api_key == "ollama"
    assert provider.model == "local-model"
    assert provider.url == "http://127.0.0.1:11434/v1/chat/completions"


def test_openrouter_provider_keeps_legacy_contract(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "legacy-key")
    provider = build_provider("openrouter")

    assert isinstance(provider, OpenRouterProvider)
    assert provider.api_key == "legacy-key"
    assert provider.url == OpenRouterProvider.DEFAULT_URL


def test_provider_factory_rejects_unknown_provider():
    with pytest.raises(Exception):
        build_provider("unsupported-provider")


def test_router_selects_a_different_provider_for_a_task():
    router = ModelRouter(
        default_provider="openrouter",
        default_model="cloud-default",
        category_models={"coding": "local-coder"},
        category_providers={"coding": "ollama"},
    )

    decision = router.route(task_type="coding")

    assert decision.provider == "ollama"
    assert decision.model == "local-coder"
    assert decision.reason == "coding"


def test_executor_invokes_the_selected_provider_only():
    cloud = Mock()
    local = Mock()
    cloud.chat.return_value = "cloud response"
    local.chat.return_value = "local response"
    router = ModelRouter(
        default_provider="openrouter",
        default_model="cloud-model",
        category_models={"coding": "qwen-coder"},
        category_providers={"coding": "ollama"},
    )
    executor = AIExecutor(
        router=router,
        provider=cloud,
        provider_name="openrouter",
        providers={"openrouter": cloud, "ollama": local},
    )
    request = AIRequest(
        messages=({"role": "user", "content": "write code"},),
        temperature=0.2,
        task_type="coding",
    )

    result = executor.execute(request)

    assert result.content == "local response"
    assert result.provider == "ollama"
    assert result.model == "qwen-coder"
    cloud.chat.assert_not_called()
    local.chat.assert_called_once()


def test_explicit_provider_and_model_override_task_route():
    router = ModelRouter(
        default_provider="openrouter",
        default_model="default",
        category_models={"reasoning": "reasoning-model"},
        category_providers={"reasoning": "gemini"},
    )
    request = AIRequest(
        messages=({"role": "user", "content": "hello"},),
        temperature=0.2,
        task_type="reasoning",
        requested_provider="ollama",
        requested_model="qwen-reasoner",
    )

    decision = router.route(request)

    assert decision.provider == "ollama"
    assert decision.model == "qwen-reasoner"
    assert decision.reason == "explicit_route"


def test_agent_roles_can_use_different_provider_and_model_profiles(monkeypatch):
    monkeypatch.setenv("ORACLE_DEFAULT_PROVIDER", "openrouter")
    monkeypatch.setenv("ORACLE_AGENT_PLANNER_PROVIDER", "ollama")
    monkeypatch.setenv("ORACLE_AGENT_PLANNER_MODEL", "qwen-planner")
    monkeypatch.setenv("ORACLE_AGENT_RESEARCHER_PROVIDER", "gemini")
    monkeypatch.setenv("ORACLE_AGENT_RESEARCHER_MODEL", "gemini-researcher")
    monkeypatch.setenv("ORACLE_AGENT_CODER_PROVIDER", "openai")
    monkeypatch.setenv("ORACLE_AGENT_CODER_MODEL", "openai-coder")

    planner = agent_profiles.resolve_profile("planner")
    researcher = agent_profiles.resolve_profile("researcher")
    coder = agent_profiles.resolve_profile("coder")

    assert (planner["provider"], planner["model"]) == ("ollama", "qwen-planner")
    assert (researcher["provider"], researcher["model"]) == ("gemini", "gemini-researcher")
    assert (coder["provider"], coder["model"]) == ("openai", "openai-coder")


def test_specialist_profile_overrides_sidebar_provider_and_discards_wrong_key(monkeypatch):
    import ai_core

    monkeypatch.setenv("ORACLE_DEFAULT_PROVIDER", "openrouter")
    monkeypatch.setenv("ORACLE_AGENT_RESEARCHER_PROVIDER", "gemini")
    monkeypatch.setenv("ORACLE_AGENT_RESEARCHER_MODEL", "gemini-research-model")
    executor = Mock()
    executor.execute.return_value = Mock(content="research result")

    with patch.object(ai_core, "_multi_executor", return_value=executor) as factory:
        result = ai_core.chat(
            [{"role": "user", "content": "research this"}],
            provider_name="openrouter",
            api_key="openrouter-session-key",
            agent_role="researcher",
        )

    assert result == "research result"
    factory.assert_called_once_with(provider_name="gemini", api_key=None)
    request = executor.execute.call_args.args[0]
    assert request.requested_provider == "gemini"
    assert request.requested_model == "gemini-research-model"


def test_specialist_profile_applies_to_streaming_provider_selection(monkeypatch):
    import ai_core

    monkeypatch.setenv("ORACLE_DEFAULT_PROVIDER", "openrouter")
    monkeypatch.setenv("ORACLE_AGENT_CODER_PROVIDER", "ollama")
    monkeypatch.setenv("ORACLE_AGENT_CODER_MODEL", "qwen-coder")
    executor = Mock()
    executor.execute_stream.return_value = iter(["chunk"])

    with patch.object(ai_core, "_multi_executor", return_value=executor) as factory:
        chunks = list(ai_core.stream(
            [{"role": "user", "content": "write code"}],
            provider_name="openrouter",
            api_key="openrouter-session-key",
            agent_role="coder",
        ))

    assert chunks == ["chunk"]
    factory.assert_called_once_with(provider_name="ollama", api_key=None)
    request = executor.execute_stream.call_args.args[0]
    assert request.requested_provider == "ollama"
    assert request.requested_model == "qwen-coder"
