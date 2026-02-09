from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Optional, Sequence

from app.db.models import TimelineMessage
from app.services.report_snapshot import parse_storage_snapshot

_NEGATIVE_KEYWORDS = (
    "war",
    "invasion",
    "battle",
    "frontline",
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
    "crash",
    "outbreak",
    "战争",
    "瘟疫",
    "疫情",
    "饥荒",
    "死亡",
    "灾害",
    "事故",
    "地震",
    "洪水",
    "火灾",
)

_POSITIVE_KEYWORDS = (
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

_THEME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "war": ("war", "invasion", "battle", "frontline", "战争", "冲突"),
    "epidemic": ("epidemic", "pandemic", "plague", "outbreak", "疫情", "瘟疫"),
    "famine": ("famine", "hunger", "粮食短缺", "饥荒"),
    "natural_disaster": (
        "earthquake",
        "flood",
        "wildfire",
        "hurricane",
        "typhoon",
        "drought",
        "地震",
        "洪水",
        "台风",
        "干旱",
        "山火",
    ),
    "man_made_disaster": (
        "meltdown",
        "chemical leak",
        "industrial",
        "explosion",
        "人为灾害",
        "泄漏",
        "爆炸",
    ),
    "accident": ("accident", "crash", "collision", "事故", "坠毁", "相撞"),
}


@dataclass(frozen=True)
class WorldlineSignal:
    seq: int
    category: str
    severity: str
    description: str
    source_kind: str


class WorldlineContextService:
    """Build continuity anchors and trend summary from branch timeline."""

    def __init__(self, max_anchors: int = 8) -> None:
        self._max_anchors = max(3, max_anchors)

    def build_context(self, timeline: Sequence[TimelineMessage]) -> str:
        """Return a compact worldline trajectory context for prompt injection."""

        signals = self._extract_signals(timeline)
        if not signals:
            return (
                "Trend: not enough confirmed key events yet.\n"
                "Risk outlook: uncertain due to sparse history.\n"
                "Key continuity anchors:\n"
                "- none"
            )

        trend = self._build_trend_summary(signals)
        risk = self._build_risk_summary(signals)
        anchors = self._build_anchors(signals, self._max_anchors)

        lines = [
            f"Trend: {trend}",
            f"Risk outlook: {risk}",
            "Key continuity anchors:",
        ]
        lines.extend(f"- {anchor}" for anchor in anchors)
        return "\n".join(lines)

    def _extract_signals(self, timeline: Sequence[TimelineMessage]) -> list[WorldlineSignal]:
        signals: list[WorldlineSignal] = []
        for message in timeline:
            if message.role != "system_report":
                continue
            snapshot_raw = getattr(message, "report_snapshot_json", None)
            payload = parse_storage_snapshot(snapshot_raw) or self._parse_report(message.content)
            if not payload:
                continue

            summary = self._safe_text(payload.get("summary"))
            if summary:
                signals.append(
                    WorldlineSignal(
                        seq=message.seq,
                        category="neutral",
                        severity="medium",
                        description=summary,
                        source_kind="summary",
                    )
                )

            events = self._normalize_entries(
                seq=message.seq,
                value=payload.get("events"),
                default_category="neutral",
                default_severity="medium",
                source_kind="event",
            )
            risks = self._normalize_entries(
                seq=message.seq,
                value=payload.get("risks"),
                default_category="negative",
                default_severity="high",
                source_kind="risk",
            )
            signals.extend(events)
            signals.extend(risks)
        return signals

    def _build_trend_summary(self, signals: Sequence[WorldlineSignal]) -> str:
        negative_count = sum(1 for item in signals if item.category == "negative")
        positive_count = sum(1 for item in signals if item.category == "positive")
        neutral_count = sum(1 for item in signals if item.category == "neutral")
        high_negative_count = sum(
            1 for item in signals if item.category == "negative" and item.severity == "high"
        )

        recent = list(signals)[-6:]
        recent_negative = sum(1 for item in recent if item.category == "negative")
        recent_positive = sum(1 for item in recent if item.category == "positive")

        if recent_negative >= 4 or high_negative_count >= 4:
            direction = "escalating instability with repeated high-impact shocks"
        elif recent_positive >= recent_negative + 2:
            direction = "partial stabilization with recovery momentum"
        elif negative_count >= positive_count + 3:
            direction = "fragile trajectory with sustained downside pressure"
        else:
            direction = "mixed trajectory with volatile shifts"

        return (
            f"{direction}; negative={negative_count}, positive={positive_count}, "
            f"neutral={neutral_count}, high_negative={high_negative_count}"
        )

    def _build_risk_summary(self, signals: Sequence[WorldlineSignal]) -> str:
        text = " ".join(item.description.lower() for item in signals)
        theme_hits: list[tuple[str, int]] = []
        for theme, keywords in _THEME_KEYWORDS.items():
            count = 0
            for keyword in keywords:
                count += text.count(keyword.lower())
            if count > 0:
                theme_hits.append((theme, count))
        theme_hits.sort(key=lambda row: row[1], reverse=True)

        major_themes = ", ".join(theme for theme, _ in theme_hits[:3]) if theme_hits else "none"
        severe_negative = sum(
            1 for item in signals if item.category == "negative" and item.severity == "high"
        )

        if severe_negative >= 4:
            severity_note = "critical crisis density"
        elif severe_negative >= 2:
            severity_note = "elevated crisis pressure"
        else:
            severity_note = "managed but fragile pressure"

        return f"{severity_note}; dominant themes: {major_themes}"

    def _build_anchors(
        self, signals: Sequence[WorldlineSignal], limit: int
    ) -> list[str]:
        if not signals:
            return []

        max_seq = max(item.seq for item in signals)
        ranked = sorted(
            signals,
            key=lambda item: (
                self._rank(item=item, max_seq=max_seq),
                item.seq,
            ),
            reverse=True,
        )
        anchors: list[str] = []
        seen: set[str] = set()
        for item in ranked:
            headline = self._first_sentence(item.description)
            if not headline:
                continue
            dedupe_key = headline.casefold()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            anchors.append(
                f"#{item.seq} ({item.category}/{item.severity}) {headline}"
            )
            if len(anchors) >= limit:
                break
        return anchors or ["none"]

    def _rank(self, *, item: WorldlineSignal, max_seq: int) -> float:
        category_score = {"negative": 3.0, "positive": 2.0, "neutral": 1.0}[item.category]
        severity_score = {"high": 3.0, "medium": 2.0, "low": 1.0}[item.severity]
        source_score = {"risk": 1.2, "event": 1.0, "summary": 0.6}[item.source_kind]
        recency = item.seq / max(1, max_seq)
        return category_score + severity_score + source_score + recency

    def _normalize_entries(
        self,
        *,
        seq: int,
        value: Any,
        default_category: str,
        default_severity: str,
        source_kind: str,
    ) -> list[WorldlineSignal]:
        if not isinstance(value, list):
            return []
        rows: list[WorldlineSignal] = []
        for item in value:
            if isinstance(item, str):
                description = self._safe_text(item)
                if not description:
                    continue
                category = self._infer_category(description, default_category)
                severity = self._infer_severity(description, default_severity)
                rows.append(
                    WorldlineSignal(
                        seq=seq,
                        category=category,
                        severity=severity,
                        description=description,
                        source_kind=source_kind,
                    )
                )
                continue

            if isinstance(item, dict):
                description = self._safe_text(
                    item.get("description")
                    or item.get("detail")
                    or item.get("content")
                    or item.get("title")
                    or item.get("label")
                )
                if not description:
                    continue
                category = self._normalize_category(item.get("category"), description, default_category)
                severity = self._normalize_severity(item.get("severity"), description, default_severity)
                rows.append(
                    WorldlineSignal(
                        seq=seq,
                        category=category,
                        severity=severity,
                        description=description,
                        source_kind=source_kind,
                    )
                )
        return rows

    def _parse_report(self, content: str) -> Optional[dict[str, Any]]:
        normalized = self._sanitize_report_text(content)
        candidates = [normalized]
        extracted = self._extract_json_object(normalized)
        if extracted and extracted != normalized:
            candidates.append(extracted)

        for candidate in candidates:
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
        return None

    @staticmethod
    def _sanitize_report_text(content: str) -> str:
        raw = str(content or "").strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
            raw = re.sub(r"\s*```$", "", raw)
        return raw.strip()

    @staticmethod
    def _extract_json_object(content: str) -> str:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return ""
        return content[start : end + 1].strip()

    @staticmethod
    def _safe_text(value: Any) -> str:
        if not isinstance(value, str):
            return ""
        return " ".join(value.split())

    @staticmethod
    def _normalize_category(raw: Any, description: str, default: str) -> str:
        value = str(raw or "").strip().lower()
        if value in {"positive", "good"}:
            return "positive"
        if value in {"negative", "bad"}:
            return "negative"
        if value in {"neutral", "general"}:
            return "neutral"
        return WorldlineContextService._infer_category(description, default)

    @staticmethod
    def _normalize_severity(raw: Any, description: str, default: str) -> str:
        value = str(raw or "").strip().lower()
        if value in {"low", "minor", "轻微", "低"}:
            return "low"
        if value in {"high", "critical", "severe", "高", "严重"}:
            return "high"
        if value in {"medium", "moderate", "中"}:
            return "medium"
        return WorldlineContextService._infer_severity(description, default)

    @staticmethod
    def _infer_category(description: str, default: str) -> str:
        text = description.casefold()
        if any(keyword in text for keyword in _NEGATIVE_KEYWORDS):
            return "negative"
        if any(keyword in text for keyword in _POSITIVE_KEYWORDS):
            return "positive"
        return default

    @staticmethod
    def _infer_severity(description: str, default: str) -> str:
        text = description.casefold()
        severe_hints = (
            "mass",
            "collapse",
            "catastrophic",
            "全面",
            "大规模",
            "重大",
            "致命",
            "全面战争",
        )
        if any(token in text for token in severe_hints):
            return "high"
        return default if default in {"low", "medium", "high"} else "medium"

    @staticmethod
    def _first_sentence(text: str) -> str:
        value = " ".join(str(text or "").split())
        if not value:
            return ""
        match = re.match(r"(.+?[。！？!?\.])(?:\s|$)", value)
        sentence = match.group(1).strip() if match else value
        if len(sentence) <= 140:
            return sentence
        return f"{sentence[:137]}..."
