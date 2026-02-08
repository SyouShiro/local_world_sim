from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import httpx
    from app.providers.base import LLMResult, ProviderRuntimeConfig


@pytest.fixture
def memory_app(tmp_path: Path, monkeypatch):
    from app.core.config import get_settings
    from app.main import create_app

    db_path = tmp_path / "test_memory_worldline.db"
    monkeypatch.setenv("DB_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")
    monkeypatch.setenv("MEMORY_MODE", "vector")
    monkeypatch.setenv("MEMORY_MAX_SNIPPETS", "8")
    monkeypatch.setenv("MEMORY_MAX_CHARS", "4000")
    monkeypatch.setenv("EMBED_PROVIDER", "deterministic")
    monkeypatch.setenv("EMBED_MODEL", "deterministic-v1")
    monkeypatch.setenv("EMBED_DIM", "64")
    get_settings.cache_clear()

    app = create_app()
    app.state.provider_service.set_adapters({"openai": StubAdapter(), "ollama": StubAdapter()})
    return app


@pytest.fixture
async def memory_client(memory_app):
    import httpx

    from app.db.base import init_db

    await init_db(memory_app.state.engine)
    transport = httpx.ASGITransport(app=memory_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield memory_app, client
    await memory_app.state.runner_manager.shutdown()
    await memory_app.state.engine.dispose()


@pytest.fixture
def anyio_backend():
    return "asyncio"


class StubAdapter:
    """Adapter stub used to avoid network calls in memory tests."""

    async def list_models(self, cfg: "ProviderRuntimeConfig") -> list[str]:
        return [cfg.model_name or "stub-model"]

    async def generate(
        self, cfg: "ProviderRuntimeConfig", messages: list[dict], stream: bool = False
    ) -> "LLMResult":
        from app.providers.base import LLMResult

        content = (
            "{"
            "\"title\":\"Stub Report\","
            "\"time_advance\":\"tick\","
            "\"summary\":\"Memory-safe stub content.\","
            "\"events\":[\"Event\"],"
            "\"risks\":[\"Risk\"]"
            "}"
        )
        return LLMResult(
            content=content,
            model_provider=cfg.provider,
            model_name=cfg.model_name,
            token_in=1,
            token_out=1,
        )


class FailingEmbedder:
    """Embedder used to verify graceful fallback on embedding failures."""

    provider = "deterministic"
    model_name = "failing"
    dimension = 64

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        from app.memory.embedder import EmbeddingError

        raise EmbeddingError("forced failure for test")


async def _create_session_with_provider(client: "httpx.AsyncClient") -> tuple[str, str]:
    payload = {
        "title": "Memory Test",
        "world_preset": "A continent with competing guilds.",
        "tick_label": "1 month",
        "post_gen_delay_sec": 1,
    }
    response = await client.post("/api/session/create", json=payload)
    assert response.status_code == 200
    data = response.json()

    provider_payload = {
        "provider": "ollama",
        "api_key": None,
        "base_url": "http://localhost:11434",
        "model_name": "stub-model",
    }
    response = await client.post(
        f"/api/provider/{data['session_id']}/set",
        json=provider_payload,
    )
    assert response.status_code == 200
    return data["session_id"], data["active_branch_id"]


async def _wait_for_messages(
    client: "httpx.AsyncClient",
    session_id: str,
    branch_id: str,
    min_count: int,
    timeout: float = 6,
) -> list[dict]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = await client.get(f"/api/timeline/{session_id}?branch_id={branch_id}&limit=200")
        assert response.status_code == 200
        messages = response.json()["messages"]
        if len(messages) >= min_count:
            return messages
        await asyncio.sleep(0.2)
    raise AssertionError("Timed out waiting for timeline messages")


@pytest.mark.anyio
async def test_memory_retrieval_sorting_and_dedup(memory_client):
    app, client = memory_client
    session_id, branch_id = await _create_session_with_provider(client)

    interventions = [
        "Alpha storm hits northern farms and grain prices surge.",
        "Alpha storm hits northern farms and grain prices surge.",
        "Beta harbor exports triple this season.",
    ]
    for content in interventions:
        response = await client.post(
            f"/api/intervention/{session_id}",
            json={"branch_id": branch_id, "content": content},
        )
        assert response.status_code == 200

    snippets = await app.state.memory_service.retrieve_context(
        session_id=session_id,
        branch_id=branch_id,
        query_text="northern farms grain prices",
    )
    assert snippets
    assert "alpha storm" in snippets[0].content.lower()
    alpha_hits = [item for item in snippets if "alpha storm" in item.content.lower()]
    assert len(alpha_hits) == 1


@pytest.mark.anyio
async def test_memory_delete_last_prevents_recall(memory_client):
    app, client = memory_client
    session_id, branch_id = await _create_session_with_provider(client)
    unique_text = "DELETE_TARGET drought continues in northern basin."

    response = await client.post(
        f"/api/intervention/{session_id}",
        json={"branch_id": branch_id, "content": unique_text},
    )
    assert response.status_code == 200

    before_delete = await app.state.memory_service.retrieve_context(
        session_id=session_id,
        branch_id=branch_id,
        query_text="DELETE_TARGET drought",
    )
    assert any("delete_target" in item.content.lower() for item in before_delete)

    response = await client.delete(f"/api/message/{session_id}/last?branch_id={branch_id}")
    assert response.status_code == 200

    after_delete = await app.state.memory_service.retrieve_context(
        session_id=session_id,
        branch_id=branch_id,
        query_text="DELETE_TARGET drought",
    )
    assert not any("delete_target" in item.content.lower() for item in after_delete)


@pytest.mark.anyio
async def test_memory_branch_isolation_and_fork_inheritance(memory_client):
    app, client = memory_client
    session_id, main_branch_id = await _create_session_with_provider(client)

    main_text = "MAIN_ONLY river treaty stabilizes border trade."
    response = await client.post(
        f"/api/intervention/{session_id}",
        json={"branch_id": main_branch_id, "content": main_text},
    )
    assert response.status_code == 200

    response = await client.post(
        f"/api/branch/{session_id}/fork",
        json={"source_branch_id": main_branch_id, "from_message_id": None},
    )
    assert response.status_code == 200
    fork_branch_id = response.json()["branch"]["id"]

    response = await client.post(
        f"/api/branch/{session_id}/switch",
        json={"branch_id": fork_branch_id},
    )
    assert response.status_code == 200

    fork_text = "FORK_ONLY nomad alliance forms in the eastern desert."
    response = await client.post(
        f"/api/intervention/{session_id}",
        json={"branch_id": fork_branch_id, "content": fork_text},
    )
    assert response.status_code == 200

    main_query = await app.state.memory_service.retrieve_context(
        session_id=session_id,
        branch_id=main_branch_id,
        query_text="FORK_ONLY nomad alliance",
    )
    assert not any("fork_only" in item.content.lower() for item in main_query)

    fork_inherited_query = await app.state.memory_service.retrieve_context(
        session_id=session_id,
        branch_id=fork_branch_id,
        query_text="MAIN_ONLY river treaty",
    )
    assert any("main_only" in item.content.lower() for item in fork_inherited_query)


@pytest.mark.anyio
async def test_embedding_failure_degrades_without_runner_break(memory_client):
    app, client = memory_client
    session_id, branch_id = await _create_session_with_provider(client)

    app.state.memory_service._embedder = FailingEmbedder()  # noqa: SLF001

    response = await client.post(f"/api/session/{session_id}/start")
    assert response.status_code == 200
    assert response.json()["running"] is True

    messages = await _wait_for_messages(client, session_id, branch_id, min_count=1)
    assert messages

    response = await client.post(f"/api/session/{session_id}/pause")
    assert response.status_code == 200
