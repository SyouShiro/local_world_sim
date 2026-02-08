from __future__ import annotations

import asyncio
import time

import pytest


async def wait_for_messages(
    client, session_id: str, branch_id: str, min_count: int, timeout: float = 6
):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = await client.get(
            f"/api/timeline/{session_id}?branch_id={branch_id}&limit=200"
        )
        assert response.status_code == 200
        messages = response.json()["messages"]
        if len(messages) >= min_count:
            return messages
        await asyncio.sleep(0.2)
    raise AssertionError("Timed out waiting for timeline messages")


async def create_session_with_provider(client) -> tuple[str, str]:
    payload = {
        "title": "Branch Test",
        "world_preset": "A continent of city-states.",
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
async def test_branch_fork_switch_and_delete_last(client):
    session_id, main_branch_id = await create_session_with_provider(client)

    response = await client.post(f"/api/session/{session_id}/start")
    assert response.status_code == 200

    main_messages = await wait_for_messages(client, session_id, main_branch_id, min_count=2)

    response = await client.post(f"/api/session/{session_id}/pause")
    assert response.status_code == 200

    response = await client.post(
        f"/api/branch/{session_id}/fork",
        json={"source_branch_id": main_branch_id, "from_message_id": None},
    )
    assert response.status_code == 200
    fork_branch = response.json()["branch"]
    fork_branch_id = fork_branch["id"]
    assert fork_branch_id != main_branch_id

    response = await client.post(
        f"/api/branch/{session_id}/switch", json={"branch_id": fork_branch_id}
    )
    assert response.status_code == 200
    assert response.json()["active_branch_id"] == fork_branch_id

    response = await client.get(f"/api/timeline/{session_id}?branch_id={fork_branch_id}&limit=200")
    assert response.status_code == 200
    fork_messages_before = response.json()["messages"]
    assert len(fork_messages_before) == len(main_messages)

    response = await client.post(f"/api/session/{session_id}/resume")
    assert response.status_code == 200

    await wait_for_messages(
        client,
        session_id,
        fork_branch_id,
        min_count=len(fork_messages_before) + 1,
    )

    response = await client.post(f"/api/session/{session_id}/pause")
    assert response.status_code == 200

    response = await client.get(f"/api/timeline/{session_id}?branch_id={main_branch_id}&limit=200")
    assert response.status_code == 200
    main_messages_after = response.json()["messages"]
    assert len(main_messages_after) == len(main_messages)

    response = await client.delete(
        f"/api/message/{session_id}/last?branch_id={fork_branch_id}"
    )
    assert response.status_code == 200

    response = await client.get(f"/api/timeline/{session_id}?branch_id={fork_branch_id}&limit=200")
    assert response.status_code == 200
    fork_messages_after = response.json()["messages"]
    seqs = [message["seq"] for message in fork_messages_after]
    assert seqs == list(range(1, len(seqs) + 1))


@pytest.mark.anyio
async def test_intervention_is_appended_to_timeline(client):
    session_id, branch_id = await create_session_with_provider(client)

    response = await client.post(
        f"/api/intervention/{session_id}",
        json={"branch_id": branch_id, "content": "A major drought starts in the north."},
    )
    assert response.status_code == 200

    response = await client.get(f"/api/timeline/{session_id}?branch_id={branch_id}&limit=200")
    assert response.status_code == 200
    messages = response.json()["messages"]
    assert messages
    assert messages[-1]["role"] == "user_intervention"
    assert "drought" in messages[-1]["content"].lower()

    response = await client.post(f"/api/session/{session_id}/start")
    assert response.status_code == 200

    await wait_for_messages(client, session_id, branch_id, min_count=2)

    response = await client.post(f"/api/session/{session_id}/pause")
    assert response.status_code == 200
