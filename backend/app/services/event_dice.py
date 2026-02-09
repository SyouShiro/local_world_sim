from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from app.core.config import Settings
from app.db.models import TimelineMessage


@dataclass(frozen=True)
class EventDicePlan:
    """Guidance payload for stochastic event generation."""

    enabled: bool
    target_event_count: int
    positive_min_count: int
    negative_min_count: int
    neutral_min_count: int
    season_hint: str
    geopolitical_hint: str
    scale_hint: str
    interval_hint: str


class EventDiceService:
    """Create lightweight stochastic guidance for each simulation tick."""

    def __init__(self, settings: Settings) -> None:
        self.reload(settings)

    def reload(self, settings: Settings) -> None:
        """Reload dice configuration from runtime settings."""

        self._enabled = settings.event_dice_enabled
        self._good_prob = _clamp_probability(settings.event_good_event_prob)
        self._bad_prob = _clamp_probability(settings.event_bad_event_prob)
        minimum = max(1, settings.event_min_events)
        maximum = max(minimum, settings.event_max_events)
        self._min_events = minimum
        self._max_events = maximum
        self._default_hemisphere = (settings.event_default_hemisphere or "north").strip().lower()

    def build_plan(
        self,
        *,
        timeline: Sequence[TimelineMessage],
        timeline_start_iso: str | None,
        timeline_step_value: int,
        timeline_step_unit: str,
        next_seq: int,
    ) -> EventDicePlan:
        """Plan stochastic event distribution for one tick."""

        if not self._enabled:
            return EventDicePlan(
                enabled=False,
                target_event_count=1,
                positive_min_count=0,
                negative_min_count=0,
                neutral_min_count=1,
                season_hint="No season hint.",
                geopolitical_hint="No geopolitical pressure hint.",
                scale_hint="No scale hint.",
                interval_hint=f"{timeline_step_value} {timeline_step_unit}",
            )

        target_event_count = random.randint(self._min_events, self._max_events)
        positive_hit = random.random() < self._good_prob
        negative_hit = random.random() < self._bad_prob

        positive_min = 1 if positive_hit else 0
        negative_min = 1 if negative_hit else 0

        while positive_min + negative_min > target_event_count:
            if negative_min > 0:
                negative_min -= 1
            elif positive_min > 0:
                positive_min -= 1

        neutral_min = max(0, target_event_count - positive_min - negative_min)

        if positive_min == 0 and negative_min == 0 and neutral_min == 0:
            neutral_min = 1

        simulated_time = _compute_simulated_time(
            timeline_start_iso=timeline_start_iso,
            timeline_step_value=timeline_step_value,
            timeline_step_unit=timeline_step_unit,
            next_seq=next_seq,
        )

        season_hint = _season_hint(simulated_time, self._default_hemisphere)
        geopolitical_hint = _infer_geopolitical_hint(timeline)
        scale_hint = _build_scale_hint(timeline_step_value, timeline_step_unit)

        return EventDicePlan(
            enabled=True,
            target_event_count=target_event_count,
            positive_min_count=positive_min,
            negative_min_count=negative_min,
            neutral_min_count=neutral_min,
            season_hint=season_hint,
            geopolitical_hint=geopolitical_hint,
            scale_hint=scale_hint,
            interval_hint=f"{timeline_step_value} {timeline_step_unit}",
        )


def _clamp_probability(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _compute_simulated_time(
    *,
    timeline_start_iso: str | None,
    timeline_step_value: int,
    timeline_step_unit: str,
    next_seq: int,
) -> datetime:
    baseline = _parse_iso_or_now(timeline_start_iso)
    offset = max(0, next_seq - 1) * max(1, timeline_step_value)
    simulated = baseline
    unit = (timeline_step_unit or "month").strip().lower()

    if unit == "day":
        return simulated + _delta_days(offset)
    if unit == "week":
        return simulated + _delta_days(offset * 7)
    if unit == "year":
        return _add_years(simulated, offset)
    return _add_months(simulated, offset)


def _parse_iso_or_now(value: str | None) -> datetime:
    raw = (value or "").strip()
    if not raw:
        return datetime.now(timezone.utc)
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _delta_days(days: int):
    from datetime import timedelta

    return timedelta(days=days)


def _add_months(source: datetime, months: int) -> datetime:
    year = source.year + (source.month - 1 + months) // 12
    year = _clamp_year(year)
    month = (source.month - 1 + months) % 12 + 1
    day = min(source.day, _days_in_month(year, month))
    return source.replace(year=year, month=month, day=day)


def _add_years(source: datetime, years: int) -> datetime:
    year = _clamp_year(source.year + years)
    day = min(source.day, _days_in_month(year, source.month))
    return source.replace(year=year, day=day)


def _clamp_year(year: int) -> int:
    if year < 1:
        return 1
    if year > 9999:
        return 9999
    return year


def _days_in_month(year: int, month: int) -> int:
    if month in {1, 3, 5, 7, 8, 10, 12}:
        return 31
    if month in {4, 6, 9, 11}:
        return 30
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    return 29 if leap else 28


def _season_hint(simulated_time: datetime, hemisphere: str) -> str:
    month = simulated_time.month
    north = {
        12: "winter",
        1: "winter",
        2: "winter",
        3: "spring",
        4: "spring",
        5: "spring",
        6: "summer",
        7: "summer",
        8: "summer",
        9: "autumn",
        10: "autumn",
        11: "autumn",
    }
    south = {
        12: "summer",
        1: "summer",
        2: "summer",
        3: "autumn",
        4: "autumn",
        5: "autumn",
        6: "winter",
        7: "winter",
        8: "winter",
        9: "spring",
        10: "spring",
        11: "spring",
    }
    season = south[month] if hemisphere == "south" else north[month]
    return (
        f"Current season is {season} in the "
        f"{'southern' if hemisphere == 'south' else 'northern'} hemisphere."
    )


def _infer_geopolitical_hint(timeline: Sequence[TimelineMessage]) -> str:
    if not timeline:
        return "Global conditions are uncertain but not yet escalated."

    joined = " ".join(item.content.lower() for item in timeline[-8:])
    tension_keywords = ("war", "sanction", "conflict", "riot", "blockade", "crisis")
    cooperation_keywords = ("treaty", "alliance", "ceasefire", "trade", "cooperation", "summit")

    tension_score = sum(joined.count(word) for word in tension_keywords)
    cooperation_score = sum(joined.count(word) for word in cooperation_keywords)

    if tension_score >= cooperation_score + 2:
        return "International conditions are tense with rising confrontation signals."
    if cooperation_score >= tension_score + 2:
        return "International conditions lean toward temporary coordination and diplomacy."
    return "International conditions are mixed, with both friction and cooperation."


def _build_scale_hint(step_value: int, step_unit: str) -> str:
    value = max(1, step_value)
    unit = (step_unit or "month").strip().lower()
    days = _interval_to_days(value, unit)
    if days <= 2:
        return "Very short interval: avoid civilizational shocks; focus on local and incremental changes."
    if days <= 14:
        return "Short interval: major strategic shifts are rare; focus on emerging signals and limited incidents."
    if days <= 90:
        return "Medium interval: regional escalations or reforms can happen if well justified."
    if days <= 370:
        return "Long interval: large policy turns, regime changes, or state fragmentation become plausible."
    return "Very long interval: transformative geopolitical and civilizational shifts are plausible."


def _interval_to_days(step_value: int, step_unit: str) -> int:
    if step_unit == "day":
        return step_value
    if step_unit == "week":
        return step_value * 7
    if step_unit == "year":
        return step_value * 365
    return step_value * 30
