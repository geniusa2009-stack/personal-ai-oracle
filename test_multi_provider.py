import json
from unittest.mock import Mock, patch

import pytest

import agent_profiles
from ai_executor import AIExecutor
from ai_request import AIRequest, Context
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


def test_model_router_uses_explicit_quality_tiers_after_task_overrides():
    router = ModelRouter(
        default_provider="openrouter",
        default_model="quick-default",
        category_models={"coding": "task-specific-coder"},
        tier_models={"fast": "fast-model", "deep": "deep-model"},
        tier_providers={"fast": "ollama", "deep": "openai"},
    )

    fast = router.route(task_type="fast")
    coding = router.route(task_type="coding")
    research = router.route(task_type="research")

    assert (fast.provider, fast.model, fast.reason) == ("ollama", "fast-model", "tier:fast")
    assert (coding.provider, coding.model, coding.reason) == (
        "openrouter", "task-specific-coder", "coding"
    )
    assert (research.provider, research.model, research.reason) == (
        "openai", "deep-model", "tier:deep"
    )


def test_model_router_does_not_implicitly_fallback_between_providers():
    router = ModelRouter(
        default_provider="ollama",
        default_model="local-default",
        tier_providers={"deep": "openai"},
        tier_models={"deep": "openai-reasoner"},
    )

    decision = router.route(task_type="reasoning")

    assert decision.provider == "openai"
    assert decision.model == "openai-reasoner"
    assert decision.reason == "tier:deep"


def test_opt_in_auto_routing_uses_specialist_task_tier(monkeypatch):
    import ai_core

    monkeypatch.setenv("ORACLE_DEFAULT_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("ORACLE_AUTO_MODEL_ROUTING", "true")
    monkeypatch.setenv("ORACLE_MODEL_TIER_DEEP", "deep-reasoner")
    monkeypatch.setenv("ORACLE_PROVIDER_TIER_DEEP", "ollama")
    monkeypatch.delenv("ORACLE_AGENT_PLANNER_PROVIDER", raising=False)
    monkeypatch.delenv("ORACLE_AGENT_PLANNER_MODEL", raising=False)
    executor = Mock()
    executor.execute.return_value = Mock(content="routed response")

    with patch.object(ai_core, "_multi_executor", return_value=executor) as factory:
        result = ai_core.chat(
            [{"role": "user", "content": "Plan a complex multi-step task"}],
            memory_scope=None,
            agent_role="planner",
        )

    assert result == "routed response"
    factory.assert_called_once_with(provider_name=None, api_key=None)
    request = executor.execute.call_args.args[0]
    assert request.task_type == "reasoning"
    assert request.requested_provider is None
    assert request.requested_model is None


def test_auto_routing_respects_explicit_role_provider_and_model(monkeypatch):
    import ai_core

    monkeypatch.setenv("ORACLE_DEFAULT_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("ORACLE_AUTO_MODEL_ROUTING", "true")
    monkeypatch.setenv("ORACLE_AGENT_CODER_PROVIDER", "gemini")
    monkeypatch.setenv("ORACLE_AGENT_CODER_MODEL", "gemini-explicit-coder")
    executor = Mock()
    executor.execute.return_value = Mock(content="explicit response")

    with patch.object(ai_core, "_multi_executor", return_value=executor) as factory:
        result = ai_core.chat(
            [{"role": "user", "content": "write code"}],
            agent_role="coder",
        )

    assert result == "explicit response"
    factory.assert_called_once_with(provider_name="gemini", api_key=None)
    request = executor.execute.call_args.args[0]
    assert request.requested_provider == "gemini"
    assert request.requested_model == "gemini-explicit-coder"
    assert request.task_type == "coding"


def test_opt_in_auto_routing_applies_to_streaming_specialists(monkeypatch):
    import ai_core

    monkeypatch.setenv("ORACLE_DEFAULT_PROVIDER", "openrouter")
    monkeypatch.setenv("ORACLE_AUTO_MODEL_ROUTING", "true")
    monkeypatch.delenv("ORACLE_AGENT_RESEARCHER_PROVIDER", raising=False)
    monkeypatch.delenv("ORACLE_AGENT_RESEARCHER_MODEL", raising=False)
    executor = Mock()
    executor.execute_stream.return_value = iter(["stream ", "response"])

    with patch.object(ai_core, "_multi_executor", return_value=executor) as factory:
        chunks = list(ai_core.stream(
            [{"role": "user", "content": "Research this topic"}],
            agent_role="researcher",
        ))

    assert chunks == ["stream ", "response"]
    factory.assert_called_once_with(provider_name=None, api_key=None)
    request = executor.execute_stream.call_args.args[0]
    assert request.streaming is True
    assert request.task_type == "research"
    assert request.requested_provider is None
    assert request.requested_model is None


def test_executor_records_privacy_safe_success_metrics(monkeypatch, tmp_path):
    import db
    import model_observability

    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "executor-metrics.db"))
    monkeypatch.setenv("ORACLE_MEMORY_SCOPE", "owner-metrics")
    provider = Mock()
    provider.chat.return_value = "PRIVATE COMPLETION THAT MUST NOT BE STORED"
    executor = AIExecutor(
        router=ModelRouter("openrouter", "test-model"),
        provider=provider,
    )
    result = executor.execute(AIRequest(
        messages=({"role": "user", "content": "PRIVATE PROMPT"},),
        temperature=0.2,
        task_type="reasoning",
    ))
    assert result.content.startswith("PRIVATE COMPLETION")
    events = model_observability.list_events("owner-metrics")
    assert len(events) == 1
    assert events[0]["outcome"] == "success"
    assert events[0]["provider"] == "openrouter"
    assert events[0]["model"] == "test-model"
    assert events[0]["output_chars"] == len(result.content)
    assert "PRIVATE PROMPT" not in json.dumps(events)
    assert "PRIVATE COMPLETION" not in json.dumps(events)


def test_executor_records_stream_failure_without_prompt_or_completion(monkeypatch, tmp_path):
    import db
    import model_observability

    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "executor-stream-metrics.db"))
    monkeypatch.setenv("ORACLE_MEMORY_SCOPE", "owner-stream")
    provider = Mock()

    def broken_stream(*_args, **_kwargs):
        yield "partial"
        raise RuntimeError("secret-bearing exception detail")

    provider.stream.side_effect = broken_stream
    executor = AIExecutor(
        router=ModelRouter("ollama", "local-model"),
        provider=provider,
        provider_name="ollama",
    )
    request = AIRequest(
        messages=({"role": "user", "content": "NEVER STORE THIS PROMPT"},),
        temperature=0.2,
        task_type="research",
        streaming=True,
    )
    with pytest.raises(RuntimeError):
        list(executor.execute_stream(request))
    events = model_observability.list_events("owner-stream")
    assert len(events) == 1
    assert events[0]["outcome"] == "error"
    serialized = json.dumps(events)
    assert "NEVER STORE THIS PROMPT" not in serialized
    assert "secret-bearing exception detail" not in serialized



def test_executor_metrics_use_explicit_request_owner_scope(monkeypatch, tmp_path):
    import db
    import model_observability

    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "request-scoped-benchmark-metrics.db"))
    monkeypatch.setenv("ORACLE_MEMORY_SCOPE", "owner-from-environment")
    provider = Mock()
    provider.chat.return_value = "measured answer"
    executor = AIExecutor(
        router=ModelRouter("ollama", "local-model"),
        provider=provider,
        provider_name="ollama",
    )
    request = AIRequest(
        messages=({"role": "user", "content": "Synthetic benchmark prompt"},),
        temperature=0.0,
        context=Context(metadata={"owner_scope": "owner-benchmark", "benchmark": True}),
    )

    executor.execute(request)

    assert len(model_observability.list_events("owner-benchmark")) == 1
    assert model_observability.list_events("owner-from-environment") == []
