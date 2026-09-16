"""
llm_provider.py — Minimal provider abstraction for Oracle's LLM execution.

This module intentionally implements only the provider currently used by the
project: OpenRouter. It keeps HTTP/provider concerns out of ai_core.py while
leaving the existing ai_core public API unchanged.
"""

from __future__ import annotations

import json
import os
from typing import Iterator, Protocol, Sequence

import requests


class LLMProvider(Protocol):
    """Minimal provider contract shared by normal and streaming chat calls."""

    def chat(
        self,
        messages: Sequence[dict],
        temperature: float = 0.7,
        model: str | None = None,
    ) -> str:
        """Return the completed assistant message as text."""
        ...

    def stream(
        self,
        messages: Sequence[dict],
        temperature: float = 0.8,
        model: str | None = None,
    ) -> Iterator[str]:
        """Yield assistant text chunks from a streaming response."""
        ...


class OracleProviderError(Exception):
    """Provider-level failure used internally by the legacy adapters."""


class OpenRouterProvider:
    """OpenRouter implementation of the minimal LLMProvider contract."""

    DEFAULT_URL = "https://openrouter.ai/api/v1/chat/completions"
    DEFAULT_MODEL = "deepseek/deepseek-chat"
    CHAT_TIMEOUT = 120
    STREAM_TIMEOUT = 180

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        url: str | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY", "")
        self.model = model if model is not None else os.environ.get(
            "OPENROUTER_MODEL", self.DEFAULT_MODEL
        )
        self.url = url or self.DEFAULT_URL

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def chat(
        self,
        messages: Sequence[dict],
        temperature: float = 0.7,
        model: str | None = None,
    ) -> str:
        """Execute a non-streaming OpenRouter chat completion."""
        if not self.api_key:
            raise OracleProviderError("missing OpenRouter API key")

        payload = {
            "model": model or self.model,
            "messages": list(messages),
            "temperature": temperature,
        }
        try:
            response = requests.post(
                self.url,
                headers=self._headers(),
                data=json.dumps(payload),
                timeout=self.CHAT_TIMEOUT,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()
        except OracleProviderError:
            raise
        except Exception as exc:
            raise OracleProviderError(str(exc)) from exc

    def stream(
        self,
        messages: Sequence[dict],
        temperature: float = 0.8,
        model: str | None = None,
    ) -> Iterator[str]:
        """Execute a streaming OpenRouter chat completion and yield text chunks."""
        if not self.api_key:
            raise OracleProviderError("missing OpenRouter API key")

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
                data=json.dumps(payload),
                stream=True,
                timeout=self.STREAM_TIMEOUT,
            ) as response:
                response.raise_for_status()
                for raw in response.iter_lines():
                    if not raw:
                        continue
                    line = raw.decode("utf-8", errors="ignore")
                    if not line.startswith("data: "):
                        continue
                    chunk = line[6:].strip()
                    if chunk == "[DONE]":
                        break
                    try:
                        delta = json.loads(chunk)["choices"][0]["delta"].get("content")
                        if delta:
                            yield delta
                    except Exception:
                        # Preserve the legacy stream behavior: malformed chunks are skipped.
                        continue
        except OracleProviderError:
            raise
        except Exception as exc:
            raise OracleProviderError(str(exc)) from exc
