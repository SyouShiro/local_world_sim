from __future__ import annotations

import json
import re
from typing import Any, Mapping, Sequence

_NEGATIVE_HINTS = (
    "war",
    "invasion",
    "battle",
    "conflict",
    "epidemic",
    "pandemic",
    "plague",
    "famine",
    "casualty",
    "death",
    "earthquake",
    "flood",
    "wildfire",
    "hurricane",
    "typhoon",
    "drought",
    "collapse",
    "explosion",
    "meltdown",
    "accident",
    "outbreak",
    "sanction",
    "blockade",
    "战争",
    "冲突",
    "瘟疫",
    "疫情",
    "饥荒",
    "死亡",
    "灾害",
    "事故",
    "地震",
    "洪水",
    "火灾",
    "封锁",
    "制裁",
)

_POSITIVE_HINTS = (
    "recovery",
    "peace",
    "ceasefire",
    "breakthrough",
    "stabilize",
    "growth",
    "cooperation",
    "alliance",
    "prosper",
    "复苏",
    "停火",
    "突破",
    "增长",
    "合作",
    "稳定",
)

_SEVERITY_HIGH_HINTS = (
    "mass",
    "catastrophic",
    "collapse",
    "state-wide",
    "national",
    "全面",
    "大规模",
    "重大",
    "致命",
    "灭亡",
    "全面战争",
)

_SEVERITY_LOW_HINTS = ("minor", "local", "small", "轻微", "局部", "小规模")

_VALID_CATEGORY = {"positive", "negative", "neutral"}
_VALID_SEVERITY = {"low", "medium", "high"}


def parse_report_snapshot(content: str, *, fallback_time_advance: str = "tick") -> dict[str, Any] | None:
    """Parse model content into a normalized report snapshot."""

    normalized = _sanitize_report_text(content)
    if not normalized:
        return None

    candidates = [normalized]
    extracted = _extract_json_object(normalized)
    if extracted and extracted != normalized:
        candidates.append(extracted)

    for candidate in candidates:
        payload = _load_json_mapping(candidate)
        if payload is None:
            continue
        return normalize_report_snapshot(payload, fallback_time_advance=fallback_time_advance)
    return None


def normalize_report_snapshot(
    payload: Mapping[str, Any], *, fallback_time_advance: str = "tick"
) -> dict[str, Any]:
    """Normalize one report snapshot payload and persist deterministic fields."""

    title = _safe_text(payload.get("title")) or "World Report"
    time_advance = _safe_text(payload.get("time_advance")) or _safe_text(fallback_time_advance) or "tick"
    events = _normalize_entries(
        payload.get("events"),
        default_category="neutral",
        default_severity="medium",
    )
    risks = _normalize_entries(
        payload.get("risks"),
        default_category="negative",
        default_severity="high",
    )

    summary = _safe_text(payload.get("summary"))
    if not summary:
        summary = _fallback_summary(events, risks)

    tension_percent = _parse_tension_percent(
        payload.get("tension_percent")
        or payload.get("tension")
        or payload.get("tension_index")
    )
    if tension_percent is None:
        tension_percent = _infer_tension_percent(events, risks)

    crisis_focus = _safe_text(
        payload.get("crisis_focus")
        or payload.get("crisis_focus_event")
        or payload.get("focus_event")
    )
    if not crisis_focus:
        crisis_focus = _fallback_crisis_focus(summary, events, risks)

    return {
        "title": title,
        "time_advance": time_advance,
        "summary": summary,
        "events": events,
        "risks": risks,
        "tension_percent": tension_percent,
        "crisis_focus": crisis_focus,
    }


def snapshot_to_storage_json(snapshot: Mapping[str, Any]) -> str:
    """Serialize normalized snapshot for DB storage."""

    return json.dumps(dict(snapshot), ensure_ascii=False, separators=(",", ":"))


def snapshot_to_content(snapshot: Mapping[str, Any]) -> str:
    """Serialize normalized snapshot back to canonical report content."""

    payload = {
        "title": _safe_text(snapshot.get("title")) or "World Report",
        "time_advance": _safe_text(snapshot.get("time_advance")) or "tick",
        "summary": _safe_text(snapshot.get("summary")),
        "events": _normalize_entries(snapshot.get("events"), default_category="neutral", default_severity="medium"),
        "risks": _normalize_entries(snapshot.get("risks"), default_category="negative", default_severity="high"),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def parse_storage_snapshot(raw_value: str | None) -> dict[str, Any] | None:
    """Parse snapshot JSON from DB text."""

    if not raw_value:
        return None
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, Mapping):
        return None
    return dict(payload)


def _normalize_entries(
    value: Any, *, default_category: str, default_severity: str
) -> list[dict[str, str]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []

    rows: list[dict[str, str]] = []
    for item in value:
        if isinstance(item, str):
            description = _safe_text(item)
            if not description:
                continue
            category = _infer_category(description, default_category)
            severity = _infer_severity(description, default_severity)
            rows.append(
                {
                    "category": category,
                    "severity": severity,
                    "description": description,
                }
            )
            continue

        if not isinstance(item, Mapping):
            continue
        description = _safe_text(
            item.get("description")
            or item.get("detail")
            or item.get("content")
            or item.get("title")
            or item.get("label")
        )
        if not description:
            continue

        category = _normalize_category(item.get("category"), description, default_category)
        severity = _normalize_severity(item.get("severity"), description, default_severity)
        rows.append(
            {
                "category": category,
                "severity": severity,
                "description": description,
            }
        )
    return rows


def _normalize_category(raw_value: Any, description: str, default_category: str) -> str:
    value = str(raw_value or "").strip().lower()
    if value in {"positive", "good"}:
        return "positive"
    if value in {"negative", "bad"}:
        return "negative"
    if value in {"neutral", "general"}:
        return "neutral"
    return _infer_category(description, default_category)


def _normalize_severity(raw_value: Any, description: str, default_severity: str) -> str:
    value = str(raw_value or "").strip().lower()
    if value in {"low", "minor", "低", "轻微"}:
        return "low"
    if value in {"medium", "moderate", "中"}:
        return "medium"
    if value in {"high", "critical", "severe", "高", "严重"}:
        return "high"
    return _infer_severity(description, default_severity)


def _infer_category(description: str, default_category: str) -> str:
    text = description.casefold()
    if any(token in text for token in _NEGATIVE_HINTS):
        return "negative"
    if any(token in text for token in _POSITIVE_HINTS):
        return "positive"
    if default_category in _VALID_CATEGORY:
        return default_category
    return "neutral"


def _infer_severity(description: str, default_severity: str) -> str:
    text = description.casefold()
    if any(token in text for token in _SEVERITY_HIGH_HINTS):
        return "high"
    if any(token in text for token in _SEVERITY_LOW_HINTS):
        return "low"
    if default_severity in _VALID_SEVERITY:
        return default_severity
    return "medium"


def _parse_tension_percent(raw_value: Any) -> int | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, (int, float)):
        return _clamp_percent(raw_value)

    raw_text = _safe_text(raw_value)
    if not raw_text:
        return None
    raw_text = raw_text.replace("%", "")
    try:
        return _clamp_percent(float(raw_text))
    except ValueError:
        return None


def _clamp_percent(value: int | float) -> int:
    rounded = int(round(float(value)))
    if rounded < 0:
        return 0
    if rounded > 100:
        return 100
    return rounded


def _infer_tension_percent(
    events: Sequence[Mapping[str, str]],
    risks: Sequence[Mapping[str, str]],
) -> int:
    score = 28
    for item in events:
        category = _normalize_category(item.get("category"), item.get("description", ""), "neutral")
        severity = _normalize_severity(item.get("severity"), item.get("description", ""), "medium")
        step = 8 if severity == "low" else 15 if severity == "medium" else 24
        if category == "negative":
            score += step
        elif category == "positive":
            score -= int(round(step * 0.6))
        else:
            score += int(round(step * 0.2))
    score += len(risks) * 8
    return _clamp_percent(score)


def _fallback_summary(
    events: Sequence[Mapping[str, str]],
    risks: Sequence[Mapping[str, str]],
) -> str:
    for row in list(events) + list(risks):
        text = _safe_text(row.get("description"))
        if text:
            return _first_sentence(text)
    return ""


def _fallback_crisis_focus(
    summary: str,
    events: Sequence[Mapping[str, str]],
    risks: Sequence[Mapping[str, str]],
) -> str:
    for row in events:
        category = _normalize_category(row.get("category"), row.get("description", ""), "neutral")
        severity = _normalize_severity(row.get("severity"), row.get("description", ""), "medium")
        if category == "negative" and severity == "high":
            return _first_sentence(row.get("description", ""))
    for row in events:
        category = _normalize_category(row.get("category"), row.get("description", ""), "neutral")
        if category == "negative":
            return _first_sentence(row.get("description", ""))
    for row in risks:
        text = _safe_text(row.get("description"))
        if text:
            return _first_sentence(text)
    return _first_sentence(summary)


def _safe_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def _sanitize_report_text(content: str) -> str:
    raw = str(content or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def _extract_json_object(content: str) -> str:
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return ""
    return content[start : end + 1].strip()


def _load_json_mapping(content: str) -> Mapping[str, Any] | None:
    for candidate in _json_repair_candidates(content):
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, Mapping):
            return payload
    return None


def _json_repair_candidates(content: str) -> list[str]:
    candidates = [content]
    repaired = _repair_json_object(content)
    if repaired != content:
        candidates.append(repaired)
    return candidates


def _repair_json_object(content: str) -> str:
    text = str(content or "")
    text = re.sub(r",\s*([}\]])", r"\1", text)
    text = re.sub(
        r'([,{]\s*)([A-Za-z_][A-Za-z0-9_]*)"\s*:',
        r'\1"\2":',
        text,
    )
    text = re.sub(
        r'([,{]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:',
        r'\1"\2":',
        text,
    )
    return text


def _first_sentence(text: str) -> str:
    value = _safe_text(text)
    if not value:
        return ""
    match = re.match(r"(.+?[。！？!?\.])(?:\s|$)", value)
    sentence = match.group(1).strip() if match else value
    if len(sentence) <= 140:
        return sentence
    return f"{sentence[:137]}..."
