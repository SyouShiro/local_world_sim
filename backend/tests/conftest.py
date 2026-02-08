import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx
import pytest

from app.core.config import get_settings
from app.db.base import init_db
from app.main import create_app
from app.providers.base import LLMResult, ProviderRuntimeConfig


@pytest.fixture
def app(tmp_path, monkeypatch):
    db_path = tmp_path / "test_worldline.db"
    monkeypatch.setenv("DB_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")
    get_settings.cache_clear()
    app = create_app()
    app.state.provider_service.set_adapters(
        {"openai": StubAdapter(), "ollama": StubAdapter()}
    )
    return app


@pytest.fixture
async def client(app):
    await init_db(app.state.engine)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await app.state.runner_manager.shutdown()
    await app.state.engine.dispose()


@pytest.fixture
def anyio_backend():
    return "asyncio"


class StubAdapter:
    """Adapter stub used to avoid external API calls in tests."""

    async def list_models(self, cfg: ProviderRuntimeConfig) -> list[str]:
        return [cfg.model_name or "stub-model"]

    async def generate(
        self, cfg: ProviderRuntimeConfig, messages: list[dict], stream: bool = False
    ) -> LLMResult:
        content = (
            "{"
            "\"title\":\"Stub Report\","
            "\"time_advance\":\"tick\","
            "\"summary\":\"Stub content.\","
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
