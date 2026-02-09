from __future__ import annotations

from fastapi import FastAPI

from app.core.config import Settings
from app.services.runtime_settings_service import RuntimeSettingsService


def test_runtime_settings_persist_env_file(tmp_path):
    env_path = tmp_path / "runtime.env"
    app = FastAPI()
    settings = Settings()
    service = RuntimeSettingsService(
        app=app,
        settings=settings,
        env_file_candidates=(str(env_path),),
    )

    service.update_settings({"APP_HOST": "127.0.0.9"}, persist=True)
    service.update_settings({"DEFAULT_TICK_LABEL": "1 个月"}, persist=True)

    content = env_path.read_text(encoding="utf-8")
    assert "APP_HOST=127.0.0.9" in content
    assert 'DEFAULT_TICK_LABEL="1 个月"' in content
