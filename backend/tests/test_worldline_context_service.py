from __future__ import annotations

import json
from types import SimpleNamespace

from app.services.worldline_context_service import WorldlineContextService


def _report(summary: str, events: list[dict], risks: list[dict]) -> str:
    return json.dumps(
        {
            "title": "Tick",
            "time_advance": "1 month",
            "summary": summary,
            "events": events,
            "risks": risks,
        },
        ensure_ascii=False,
    )


def _msg(seq: int, role: str, content: str):
    return SimpleNamespace(seq=seq, role=role, content=content)


def test_worldline_context_extracts_trend_and_anchors():
    timeline = [
        _msg(
            1,
            "system_report",
            _report(
                "Trade resumed but tensions remain.",
                [
                    {
                        "category": "positive",
                        "severity": "medium",
                        "description": "Markets reopen across coastal states. Emergency credit stabilizes prices.",
                    }
                ],
                [],
            ),
        ),
        _msg(
            2,
            "system_report",
            _report(
                "A border war expanded and medical systems are strained.",
                [
                    {
                        "category": "negative",
                        "severity": "high",
                        "description": "A regional war widened overnight. Casualty reports doubled in major cities. Rail supply lines were hit.",
                    }
                ],
                [
                    {
                        "category": "negative",
                        "severity": "high",
                        "description": "Epidemic pressure rises as shelter capacity breaks down.",
                    }
                ],
            ),
        ),
    ]

    service = WorldlineContextService(max_anchors=6)
    context = service.build_context(timeline)  # type: ignore[arg-type]

    assert "Trend:" in context
    assert "Risk outlook:" in context
    assert "Key continuity anchors:" in context
    assert "(negative/high)" in context
    assert "war" in context.lower() or "epidemic" in context.lower()


def test_worldline_context_handles_sparse_history():
    timeline = [_msg(1, "system_report", "not-json")]
    service = WorldlineContextService()
    context = service.build_context(timeline)  # type: ignore[arg-type]
    assert "not enough confirmed key events yet" in context
