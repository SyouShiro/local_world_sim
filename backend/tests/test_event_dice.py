from __future__ import annotations

from types import SimpleNamespace

from app.services.event_dice import EventDiceService, _compute_simulated_time


def _make_settings(**overrides):
    values = {
        "event_dice_enabled": True,
        "event_good_event_prob": 0.25,
        "event_bad_event_prob": 0.15,
        "event_min_events": 1,
        "event_max_events": 5,
        "event_default_hemisphere": "north",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_compute_simulated_time_with_pre_epoch_start() -> None:
    simulated = _compute_simulated_time(
        timeline_start_iso="1900-01-01T00:00:00+00:00",
        timeline_step_value=1,
        timeline_step_unit="day",
        next_seq=2,
    )

    assert simulated.year == 1900
    assert simulated.month == 1
    assert simulated.day == 2


def test_compute_simulated_time_clamps_year_overflow() -> None:
    simulated = _compute_simulated_time(
        timeline_start_iso="9999-12-15T00:00:00+00:00",
        timeline_step_value=12,
        timeline_step_unit="month",
        next_seq=20,
    )

    assert simulated.year == 9999


def test_build_plan_handles_pre_epoch_start_without_errno() -> None:
    service = EventDiceService(_make_settings())

    plan = service.build_plan(
        timeline=[],
        timeline_start_iso="1900-05-01T00:00:00+00:00",
        timeline_step_value=1,
        timeline_step_unit="week",
        next_seq=3,
    )

    assert plan.enabled is True
    assert 1 <= plan.target_event_count <= 5
