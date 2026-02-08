from __future__ import annotations

import uuid

import pytest


async def create_session_with_provider(client) -> tuple[str, str]:
    payload = {
        "title": "Edge Case Test",
        "world_preset": "An isolated island federation.",
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
        f"/api/provider/{data['session_id']}/set", json=provider_payload
    )
    assert response.status_code == 200

    return data["session_id"], data["active_branch_id"]


@pytest.mark.anyio
async def test_switch_unknown_branch_returns_404(client):
    session_id, _ = await create_session_with_provider(client)

    response = await client.post(
        f"/api/branch/{session_id}/switch",
        json={"branch_id": uuid.uuid4().hex},
    )
    assert response.status_code == 404


@pytest.mark.anyio
async def test_delete_last_while_generating_returns_409(app, client, monkeypatch):
    session_id, branch_id = await create_session_with_provider(client)

    async def always_generating(_: str) -> bool:
        return True

    monkeypatch.setattr(app.state.runner_manager, "is_generating", always_generating)
    response = await client.delete(f"/api/message/{session_id}/last?branch_id={branch_id}")
    assert response.status_code == 409


@pytest.mark.anyio
async def test_delete_last_without_messages_returns_404(client):
    session_id, branch_id = await create_session_with_provider(client)

    response = await client.delete(f"/api/message/{session_id}/last?branch_id={branch_id}")
    assert response.status_code == 404


@pytest.mark.anyio
async def test_intervention_empty_content_returns_400(client):
    session_id, branch_id = await create_session_with_provider(client)

    response = await client.post(
        f"/api/intervention/{session_id}",
        json={"branch_id": branch_id, "content": "   "},
    )
    assert response.status_code == 400


@pytest.mark.anyio
async def test_select_model_empty_string_returns_400(client):
    session_id, _ = await create_session_with_provider(client)

    response = await client.post(
        f"/api/provider/{session_id}/select-model",
        json={"model_name": "   "},
    )
    assert response.status_code == 400
