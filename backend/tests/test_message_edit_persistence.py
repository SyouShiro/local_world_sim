from __future__ import annotations

import asyncio
import json
import time

import pytest

from app.repos.message_repo import MessageRepo


async def create_session_with_provider(client) -> tuple[str, str]:
    payload = {
        "title": "Persistence Test",
        "world_preset": "A world with long historical continuity.",
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


async def wait_for_system_report(client, session_id: str, branch_id: str) -> dict:
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        response = await client.get(
            f"/api/timeline/{session_id}?branch_id={branch_id}&limit=200"
        )
        assert response.status_code == 200
        messages = response.json()["messages"]
        report = next(
            (item for item in reversed(messages) if item["role"] == "system_report"),
            None,
        )
        if report:
            return report
        await asyncio.sleep(0.2)
    raise AssertionError("Timed out waiting for system_report message")


@pytest.mark.anyio
async def test_timeline_get_backfills_report_snapshot(app, client):
    session_id, branch_id = await create_session_with_provider(client)
    raw_report_content = (
        "{"
        "\"title\":\"Old Report\","
        "\"time_advance\":\"1 month\","
        "\"summary\":\"Legacy structured text.\","
        "\"events\":[\"Supply lines remain stable\"],"
        "\"risks\":[\"External bloc adds tariff pressure\"]"
        "}"
    )

    async with app.state.sessionmaker() as db:
        repo = MessageRepo(db)
        async with db.begin():
            message = await repo.add_message(
                message_id="legacy-report-1",
                session_id=session_id,
                branch_id=branch_id,
                role="system_report",
                content=raw_report_content,
                time_jump_label="1 month",
                model_provider="ollama",
                model_name="stub-model",
                token_in=1,
                token_out=1,
            )

    response = await client.get(f"/api/timeline/{session_id}?branch_id={branch_id}&limit=200")
    assert response.status_code == 200
    messages = response.json()["messages"]
    row = next(item for item in messages if item["id"] == message.id)
    snapshot = row["report_snapshot"]
    assert snapshot is not None
    assert snapshot["summary"] == "Legacy structured text."
    assert snapshot["events"][0]["severity"] in {"low", "medium", "high"}

    async with app.state.sessionmaker() as db:
        fetched = await MessageRepo(db).get_message(branch_id, message.id)
        assert fetched is not None
        assert fetched.report_snapshot_json is not None
        parsed = json.loads(fetched.report_snapshot_json)
        assert parsed["summary"] == "Legacy structured text."


@pytest.mark.anyio
async def test_edit_message_persists_snapshot_and_flags(client):
    session_id, branch_id = await create_session_with_provider(client)

    response = await client.post(f"/api/session/{session_id}/start")
    assert response.status_code == 200

    report = await wait_for_system_report(client, session_id, branch_id)

    response = await client.post(f"/api/session/{session_id}/pause")
    assert response.status_code == 200

    payload = {
        "branch_id": branch_id,
        "report_snapshot": {
            "title": "修订后的世界报告",
            "time_advance": "1 month",
            "summary": "局势出现意外回暖，各方开始试探性接触。",
            "events": [
                {
                    "category": "positive",
                    "severity": "medium",
                    "description": "多个地区宣布有限停火，贸易走廊短暂恢复。"
                }
            ],
            "risks": [
                {
                    "category": "negative",
                    "severity": "high",
                    "description": "边境仍存在误判风险，军事部署并未完全撤离。"
                }
            ],
            "tension_percent": 64,
            "crisis_focus": "边境误判风险持续升高。",
        },
    }
    response = await client.patch(
        f"/api/message/{session_id}/{report['id']}",
        json=payload,
    )
    assert response.status_code == 200
    updated = response.json()["message"]
    assert updated["id"] == report["id"]
    assert updated["is_user_edited"] is True
    assert updated["edited_at"] is not None
    assert (
        updated["report_snapshot"]["summary"]
        == "局势出现意外回暖，各方开始试探性接触。"
    )
    assert updated["report_snapshot"]["events"][0]["severity"] == "medium"

    timeline = await client.get(f"/api/timeline/{session_id}?branch_id={branch_id}&limit=200")
    assert timeline.status_code == 200
    row = next(
        item for item in timeline.json()["messages"] if item["id"] == report["id"]
    )
    assert row["report_snapshot"]["tension_percent"] == 64
    assert row["report_snapshot"]["crisis_focus"] == "边境误判风险持续升高。"
    assert "局势出现意外回暖" in row["content"]
