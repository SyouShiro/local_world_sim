import pytest


@pytest.mark.anyio
async def test_session_lifecycle(client):
    payload = {
        "title": "Test World",
        "world_preset": "A quiet archipelago.",
        "tick_label": "1 month",
        "post_gen_delay_sec": 1,
    }
    response = await client.post("/api/session/create", json=payload)
    assert response.status_code == 200
    data = response.json()
    session_id = data["session_id"]

    provider_payload = {
        "provider": "ollama",
        "api_key": None,
        "base_url": "http://localhost:11434",
        "model_name": "stub-model",
    }
    response = await client.post(f"/api/provider/{session_id}/set", json=provider_payload)
    assert response.status_code == 200

    response = await client.post(f"/api/session/{session_id}/start")
    assert response.status_code == 200
    assert response.json()["running"] is True

    response = await client.post(f"/api/session/{session_id}/start")
    assert response.status_code == 200
    assert response.json()["running"] is True

    response = await client.post(f"/api/session/{session_id}/pause")
    assert response.status_code == 200
    assert response.json()["running"] is False

    response = await client.post(f"/api/session/{session_id}/pause")
    assert response.status_code == 200
    assert response.json()["running"] is False

    response = await client.post(f"/api/session/{session_id}/resume")
    assert response.status_code == 200
    assert response.json()["running"] is True
