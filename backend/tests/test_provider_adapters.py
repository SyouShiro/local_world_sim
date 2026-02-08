from __future__ import annotations

import httpx
import pytest

from app.providers.base import ProviderError, ProviderRuntimeConfig
from app.providers.deepseek_adapter import DeepSeekAdapter
from app.providers.gemini_adapter import GeminiAdapter
from app.providers.ollama_adapter import OllamaAdapter
from app.providers.openai_adapter import OpenAIAdapter


@pytest.mark.anyio
async def test_openai_adapter_list_and_generate():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "gpt-test"}]})
        if request.url.path == "/v1/responses":
            return httpx.Response(
                200,
                json={
                    "output": [
                        {"content": [{"type": "output_text", "text": "hello from responses"}]}
                    ],
                    "usage": {"input_tokens": 5, "output_tokens": 7},
                },
            )
        return httpx.Response(404, json={"error": "not found"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.openai.com") as client:
        adapter = OpenAIAdapter(http_client=client)
        cfg = ProviderRuntimeConfig(
            provider="openai",
            model_name="gpt-test",
            base_url="https://api.openai.com",
            api_key="sk-test",
        )
        models = await adapter.list_models(cfg)
        assert models == ["gpt-test"]

        result = await adapter.generate(cfg, [{"role": "user", "content": "hi"}])
        assert "hello from responses" in result.content
        assert result.token_in == 5
        assert result.token_out == 7


@pytest.mark.anyio
async def test_ollama_adapter_list_and_generate():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "llama3"}]})
        if request.url.path == "/api/chat":
            return httpx.Response(
                200,
                json={
                    "message": {"content": "hello from ollama"},
                    "prompt_eval_count": 3,
                    "eval_count": 4,
                },
            )
        return httpx.Response(404, json={"error": "not found"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost:11434") as client:
        adapter = OllamaAdapter(http_client=client)
        cfg = ProviderRuntimeConfig(
            provider="ollama",
            model_name="llama3",
            base_url="http://localhost:11434",
        )
        models = await adapter.list_models(cfg)
        assert models == ["llama3"]

        result = await adapter.generate(cfg, [{"role": "user", "content": "hi"}])
        assert "hello from ollama" in result.content
        assert result.token_in == 3
        assert result.token_out == 4


@pytest.mark.anyio
async def test_deepseek_adapter_list_and_generate():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/models":
            return httpx.Response(200, json={"data": [{"id": "deepseek-chat"}]})
        if request.url.path == "/chat/completions":
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "hello from deepseek"}}],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 9},
                },
            )
        return httpx.Response(404, json={"error": "not found"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.deepseek.com") as client:
        adapter = DeepSeekAdapter(http_client=client)
        cfg = ProviderRuntimeConfig(
            provider="deepseek",
            model_name="deepseek-chat",
            base_url="https://api.deepseek.com",
            api_key="sk-deepseek",
        )
        models = await adapter.list_models(cfg)
        assert models == ["deepseek-chat"]

        result = await adapter.generate(cfg, [{"role": "user", "content": "hi"}])
        assert "hello from deepseek" in result.content
        assert result.token_in == 4
        assert result.token_out == 9


@pytest.mark.anyio
async def test_gemini_adapter_list_and_generate():
    def handler(request: httpx.Request) -> httpx.Response:
        assert not request.url.query
        assert request.headers.get("x-goog-api-key") == "sk-gemini"
        if request.url.path == "/v1beta/models":
            return httpx.Response(200, json={"models": [{"name": "models/gemini-test"}]})
        if request.url.path == "/v1beta/models/gemini-test:generateContent":
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {"content": {"parts": [{"text": "hello from gemini"}]}}
                    ],
                    "usageMetadata": {"promptTokenCount": 6, "candidatesTokenCount": 8},
                },
            )
        return httpx.Response(404, json={"error": "not found"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://generativelanguage.googleapis.com"
    ) as client:
        adapter = GeminiAdapter(http_client=client)
        cfg = ProviderRuntimeConfig(
            provider="gemini",
            model_name="gemini-test",
            base_url="https://generativelanguage.googleapis.com",
            api_key="sk-gemini",
        )
        models = await adapter.list_models(cfg)
        assert models == ["models/gemini-test"]

        result = await adapter.generate(cfg, [{"role": "user", "content": "hi"}])
        assert "hello from gemini" in result.content
        assert result.token_in == 6
        assert result.token_out == 8


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("provider", "base_url", "api_key", "expected_path"),
    [
        ("openai", "https://api.openai.com", "sk-openai", "/v1/models"),
        ("ollama", "http://localhost:11434", None, "/api/tags"),
        ("deepseek", "https://api.deepseek.com", "sk-deepseek", "/models"),
        ("gemini", "https://generativelanguage.googleapis.com", "sk-gemini", "/v1beta/models"),
    ],
)
async def test_adapter_list_models_rate_limit_is_retryable(
    provider: str, base_url: str, api_key: str | None, expected_path: str
):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == expected_path
        return httpx.Response(429, json={"error": {"message": "rate limited"}})

    adapter_map = {
        "openai": OpenAIAdapter,
        "ollama": OllamaAdapter,
        "deepseek": DeepSeekAdapter,
        "gemini": GeminiAdapter,
    }
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
        adapter = adapter_map[provider](http_client=client)
        cfg = ProviderRuntimeConfig(
            provider=provider,
            model_name="test-model",
            base_url=base_url,
            api_key=api_key,
        )
        with pytest.raises(ProviderError) as exc_info:
            await adapter.list_models(cfg)

    assert exc_info.value.code == "PROVIDER_RATE_LIMIT"
    assert exc_info.value.retryable is True
