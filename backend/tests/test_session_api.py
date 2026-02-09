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


@pytest.mark.anyio
async def test_session_history(client):
    payload_a = {
        "title": "World A",
        "world_preset": "Archive A",
    }
    response = await client.post("/api/session/create", json=payload_a)
    assert response.status_code == 200
    session_a = response.json()["session_id"]

    payload_b = {
        "title": "World B",
        "world_preset": "Archive B",
    }
    response = await client.post("/api/session/create", json=payload_b)
    assert response.status_code == 200
    session_b = response.json()["session_id"]

    response = await client.get("/api/session/history?limit=1")
    assert response.status_code == 200
    rows = response.json()["sessions"]
    assert len(rows) == 1
    assert rows[0]["session_id"] == session_b
    assert rows[0]["title"] == "World B"

    response = await client.get(f"/api/session/{session_a}")
    assert response.status_code == 200
    assert response.json()["session_id"] == session_a
