"""
llm_provider.py — Provider adapters for local and hosted OpenAI-compatible APIs.

Supported:
- OpenRouter
- OpenAI
- Google Gemini (OpenAI-compatible endpoint)
- Ollama (local loopback server)

The common contract is deliberately small so more provider-specific adapters can
be added without changing the AI request, router, executor, or agent layers.
"""

from __future__ import annotations

import json
import os
from typing import Iterator, Mapping, Protocol, Sequence
from urllib.parse import urljoin

import requests


class LLMProvider(Protocol):
    def chat(
        self,
        messages: Sequence[dict],
        temperature: float = 0.7,
        model: str | None = None,
        response_format: Mapping[str, object] | None = None,
    ) -> str: ...

    def stream(
        self,
        messages: Sequence[dict],
        temperature: float = 0.8,
        model: str | None = None,
    ) -> Iterator[str]: ...


class OracleProviderError(Exception):
    """Provider-level failure used by the shared AI execution pipeline."""


class OpenAICompatibleProvider:
    """Adapter for providers exposing the OpenAI Chat Completions protocol."""

    CHAT_TIMEOUT = 120
    STREAM_TIMEOUT = 180

    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str = "",
        model: str = "",
        require_api_key: bool = True,
        extra_headers: Mapping[str, str] | None = None,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.url = self.base_url if self.base_url.endswith("/chat/completions") else f"{self.base_url}/chat/completions"
        self.api_key = api_key
        self.model = model
        self.require_api_key = require_api_key
        self.extra_headers = dict(extra_headers or {})

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        headers.update(self.extra_headers)
        return headers

    def _ensure_configured(self) -> None:
        if self.require_api_key and not self.api_key:
            raise OracleProviderError(f"missing API key for provider: {self.name}")

    def chat(
        self,
        messages: Sequence[dict],
        temperature: float = 0.7,
        model: str | None = None,
        response_format: Mapping[str, object] | None = None,
    ) -> str:
        self._ensure_configured()
        payload = {
            "model": model or self.model,
            "messages": list(messages),
            "temperature": temperature,
        }
        if response_format is not None:
            payload["response_format"] = dict(response_format)
        try:
            response = requests.post(
                self.url,
                headers=self._headers(),
                data=json.dumps(payload, ensure_ascii=False),
                timeout=self.CHAT_TIMEOUT,
            )
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(
                    item.get("text", "") for item in content if isinstance(item, dict)
                )
            if not isinstance(content, str):
                raise OracleProviderError(f"provider {self.name} returned non-text content")
            return content.strip()
        except OracleProviderError:
            raise
        except requests.RequestException as exc:
            raise OracleProviderError(f"{self.name} request failed: {exc}") from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise OracleProviderError(f"{self.name} returned an invalid chat response") from exc

    def stream(
        self,
        messages: Sequence[dict],
        temperature: float = 0.8,
        model: str | None = None,
    ) -> Iterator[str]:
        self._ensure_configured()
        payload = {
            "model": model or self.model,
            "messages": list(messages),
            "stream": True,
            "temperature": temperature,
        }
        try:
            with requests.post(
                self.url,
                headers=self._headers(),
                data=json.dumps(payload, ensure_ascii=False),
                stream=True,
                timeout=self.STREAM_TIMEOUT,
            ) as response:
                response.raise_for_status()
                for raw in response.iter_lines():
                    if not raw:
                        continue
                    line = raw.decode("utf-8", errors="ignore") if isinstance(raw, bytes) else str(raw)
                    if not line.startswith("data: "):
                        continue
                    chunk = line[6:].strip()
                    if chunk == "[DONE]":
                        break
                    try:
                        delta = json.loads(chunk)["choices"][0]["delta"].get("content")
                        if isinstance(delta, str) and delta:
                            yield delta
                        elif isinstance(delta, list):
                            for item in delta:
                                if isinstance(item, dict) and isinstance(item.get("text"), str):
                                    yield item["text"]
                    except (ValueError, KeyError, IndexError, TypeError):
                        continue
        except OracleProviderError:
            raise
        except requests.RequestException as exc:
            raise OracleProviderError(f"{self.name} stream failed: {exc}") from exc


class OpenRouterProvider(OpenAICompatibleProvider):
    """Backward-compatible OpenRouter adapter."""

    DEFAULT_URL = "https://openrouter.ai/api/v1/chat/completions"
    DEFAULT_MODEL = "deepseek/deepseek-chat"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        url: str | None = None,
    ) -> None:
        api_key = api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY", "")
        model = model if model is not None else os.environ.get("OPENROUTER_MODEL", self.DEFAULT_MODEL)
        endpoint = url or self.DEFAULT_URL
        base_url = endpoint.removesuffix("/chat/completions")
        super().__init__(
            name="openrouter",
            base_url=base_url,
            api_key=api_key,
            model=model,
            require_api_key=True,
        )


def build_provider(name: str, *, api_key: str | None = None) -> LLMProvider:
    """Build one configured provider by stable registry name."""
    provider_name = (name or "").strip().lower()

    if provider_name == "openrouter":
        return OpenRouterProvider(api_key=api_key)

    if provider_name == "openai":
        key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")
        return OpenAICompatibleProvider(
            name="openai",
            base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            api_key=key,
            model=os.environ.get("OPENAI_MODEL", ""),
            require_api_key=True,
        )

    if provider_name == "gemini":
        key = api_key if api_key is not None else (
            os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
        )
        return OpenAICompatibleProvider(
            name="gemini",
            base_url=os.environ.get(
                "GEMINI_OPENAI_BASE_URL",
                "https://generativelanguage.googleapis.com/v1beta/openai",
            ),
            api_key=key,
            model=os.environ.get("GEMINI_MODEL", ""),
            require_api_key=True,
        )

    if provider_name == "ollama":
        return OpenAICompatibleProvider(
            name="ollama",
            base_url=os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1"),
            api_key=os.environ.get("OLLAMA_API_KEY", "ollama"),
            model=os.environ.get("OLLAMA_MODEL", ""),
            require_api_key=False,
        )

    raise OracleProviderError(f"unknown AI provider: {provider_name}")


def configured_provider_names() -> list[str]:
    """Return available providers without making outbound requests."""
    names = []
    if os.environ.get("OPENROUTER_API_KEY"):
        names.append("openrouter")
    if os.environ.get("OPENAI_API_KEY"):
        names.append("openai")
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        names.append("gemini")
    if os.environ.get("ORACLE_OLLAMA_ENABLED", "1").strip().lower() not in {"0", "false", "no"}:
        names.append("ollama")
    return names
