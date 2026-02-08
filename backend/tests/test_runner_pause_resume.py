import asyncio
import time

import pytest


async def wait_for_messages(client, session_id, branch_id, min_count, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = await client.get(
            f"/api/timeline/{session_id}?branch_id={branch_id}&limit=200"
        )
        assert response.status_code == 200
        data = response.json()
        if len(data["messages"]) >= min_count:
            return data["messages"]
        await asyncio.sleep(0.2)
    raise AssertionError("Timed out waiting for timeline messages")


@pytest.mark.anyio
async def test_runner_pause_resume(client):
    payload = {
        "title": "Run Test",
        "world_preset": "A drifting ocean colony.",
        "tick_label": "1 month",
        "post_gen_delay_sec": 1,
    }
    response = await client.post("/api/session/create", json=payload)
    data = response.json()
    session_id = data["session_id"]
    branch_id = data["active_branch_id"]

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

    messages = await wait_for_messages(client, session_id, branch_id, min_count=1)
    assert messages

    response = await client.post(f"/api/session/{session_id}/pause")
    assert response.status_code == 200

    count_before = len(messages)
    await asyncio.sleep(2.2)

    response = await client.get(
        f"/api/timeline/{session_id}?branch_id={branch_id}&limit=200"
    )
    data_after = response.json()
    assert len(data_after["messages"]) == count_before
