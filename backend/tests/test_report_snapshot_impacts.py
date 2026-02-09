from __future__ import annotations

from app.services.report_snapshot import apply_event_impacts


def test_positive_events_reduce_tension_and_can_clear_focus() -> None:
    snapshot = {
        "title": "t",
        "time_advance": "1个月",
        "summary": "s",
        "events": [
            {"category": "positive", "severity": "high", "description": "A peace breakthrough."},
            {"category": "positive", "severity": "medium", "description": "Recovery continues."},
        ],
        "risks": [],
        "tension_percent": 18,
        "crisis_focus": "war",
    }
    adjusted = apply_event_impacts(snapshot, output_language="en")
    assert adjusted["tension_percent"] < 18
    assert adjusted["crisis_focus"] == ""


def test_negative_events_raise_tension_and_can_switch_focus() -> None:
    snapshot = {
        "title": "t",
        "time_advance": "1个月",
        "summary": "s",
        "events": [
            {
                "category": "negative",
                "severity": "high",
                "description": "瘟疫在多座城市扩散，医疗系统超负荷。",
            }
        ],
        "risks": [],
        "tension_percent": 42,
        "crisis_focus": "战争",
    }
    adjusted = apply_event_impacts(snapshot, output_language="zh-cn")
    assert adjusted["tension_percent"] > 42
    assert adjusted["crisis_focus"] == "瘟疫"


def test_low_tension_always_clears_focus() -> None:
    snapshot = {
        "title": "t",
        "time_advance": "1个月",
        "summary": "s",
        "events": [{"category": "neutral", "severity": "low", "description": "Quiet week."}],
        "risks": [],
        "tension_percent": 8,
        "crisis_focus": "financial crisis",
    }
    adjusted = apply_event_impacts(snapshot, output_language="en")
    assert adjusted["tension_percent"] == 8
    assert adjusted["crisis_focus"] == ""

