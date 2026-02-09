from __future__ import annotations

from typing import Iterable, List

from app.db.models import TimelineMessage, UserIntervention
from app.memory.types import MemorySnippet
from app.services.event_dice import EventDicePlan


class PromptBuilder:
    """Compose prompts for LLM generation."""

    def __init__(
        self,
        max_history: int = 12,
        memory_max_snippets: int = 8,
        memory_max_chars: int = 4000,
    ) -> None:
        self._max_history = max_history
        self._memory_max_snippets = max(1, memory_max_snippets)
        self._memory_max_chars = max(200, memory_max_chars)
        self._memory_max_tokens = max(50, memory_max_chars // 4)

    def update_memory_limits(self, memory_max_snippets: int, memory_max_chars: int) -> None:
        """Apply runtime memory prompt limits."""

        self._memory_max_snippets = max(1, memory_max_snippets)
        self._memory_max_chars = max(200, memory_max_chars)
        self._memory_max_tokens = max(50, memory_max_chars // 4)

    def build_messages(
        self,
        world_preset: str,
        timeline: Iterable[TimelineMessage],
        interventions: Iterable[UserIntervention],
        tick_label: str,
        memory_snippets: Iterable[MemorySnippet] | None = None,
        output_language: str = "en",
        timeline_start_iso: str | None = None,
        timeline_step_value: int = 1,
        timeline_step_unit: str = "month",
        event_dice_plan: EventDicePlan | None = None,
        worldline_context: str | None = None,
    ) -> List[dict]:
        """Create the message list for an LLM provider."""

        language_hint = self._language_name(output_language)
        system_prompt = (
            "You are generating a world progress report. "
            "Keep it concise, structured, and continuous. "
            "Output JSON with title, time_advance, summary, events, and risks. "
            "Keep JSON keys in English. "
            "Use this JSON schema for events: "
            "events: [{\"category\":\"positive|negative|neutral\","
            "\"severity\":\"low|medium|high\",\"description\":\"...\"}]. "
            "Each event.description must be a news-style brief of 2-3 sentences, never more than 3 sentences. "
            f"Keep human-readable values in {language_hint}."
        )
        history_lines = []
        for message in list(timeline)[-self._max_history :]:
            history_lines.append(f"#{message.seq} {message.content}")
        intervention_lines = [f"- {item.content}" for item in interventions]
        history_text = "\n".join(history_lines) if history_lines else "(none)"
        intervention_text = "\n".join(intervention_lines) if intervention_lines else "(none)"

        memory_section = self._build_memory_section(memory_snippets)
        worldline_section = self._build_worldline_section(worldline_context)
        dice_guidance = self._build_dice_guidance(event_dice_plan)
        memory_block = ""
        if memory_section:
            memory_block = (
                "Long-term memory context:\n"
                f"{memory_section}\n\n"
            )
        user_prompt = (
            "World preset:\n"
            f"{world_preset}\n\n"
            "Worldline continuity record:\n"
            f"{worldline_section}\n\n"
            "Recent timeline:\n"
            f"{history_text}\n\n"
            "Timeline clock:\n"
            f"Start at: {timeline_start_iso or '(auto)'}\n"
            f"Step: {timeline_step_value} {timeline_step_unit}\n\n"
            "Event dice guidance:\n"
            f"{dice_guidance}\n\n"
            f"{memory_block}"
            "Pending interventions:\n"
            f"{intervention_text}\n\n"
            f"Time advance label: {tick_label}\n"
            "Return JSON only. "
            "The events array must contain between 1 and 5 items and follow dice guidance. "
            "Each event description should read like a short news dispatch with at most 3 sentences."
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _build_memory_section(self, memory_snippets: Iterable[MemorySnippet] | None) -> str:
        if not memory_snippets:
            return ""

        lines: list[str] = []
        seen: set[str] = set()
        total_chars = 0
        total_tokens = 0
        for snippet in memory_snippets:
            text = " ".join(snippet.content.split())
            if not text:
                continue
            dedupe_key = text.casefold()
            if dedupe_key in seen:
                continue

            estimated_tokens = self._estimate_tokens(text)
            projected_chars = total_chars + len(text)
            projected_tokens = total_tokens + estimated_tokens
            if projected_chars > self._memory_max_chars:
                break
            if projected_tokens > self._memory_max_tokens:
                break

            lines.append(f"- #{snippet.source_message_seq} {text}")
            seen.add(dedupe_key)
            total_chars = projected_chars
            total_tokens = projected_tokens
            if len(lines) >= self._memory_max_snippets:
                break

        return "\n".join(lines)

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        compact = text.strip()
        if not compact:
            return 0
        return max(1, len(compact) // 4)

    @staticmethod
    def _build_dice_guidance(plan: EventDicePlan | None) -> str:
        if not plan or not plan.enabled:
            return (
                "No dice override. Produce logically varied events with balanced tones. "
                "Keep event count between 1 and 5."
            )
        negative_intensity_hint = (
            "Negative intensity guidance: include consequential crises when warranted, "
            "such as war escalation, epidemic spread, mass casualty events, famine, "
            "severe natural disasters, man-made disasters, and major accidents. "
            "Keep causality realistic and proportional to the timeline interval."
            if plan.negative_min_count > 0
            else "Negative intensity guidance: keep adverse events plausible but proportionate."
        )
        return (
            f"Target event count: {plan.target_event_count} (1-5).\n"
            f"Minimum positive events: {plan.positive_min_count}.\n"
            f"Minimum negative events: {plan.negative_min_count}.\n"
            f"Minimum neutral events: {plan.neutral_min_count}.\n"
            f"Season hint: {plan.season_hint}\n"
            f"Geopolitical hint: {plan.geopolitical_hint}\n"
            f"Scale hint: {plan.scale_hint}\n"
            f"Interval hint: {plan.interval_hint}\n"
            f"{negative_intensity_hint}\n"
            "Avoid over-specific deterministic causes; keep surprises plausible and coherent."
        )

    @staticmethod
    def _build_worldline_section(worldline_context: str | None) -> str:
        text = (worldline_context or "").strip()
        if not text:
            return "Trend: not enough confirmed key events yet.\nRisk outlook: uncertain.\nKey continuity anchors:\n- none"
        return text

    @staticmethod
    def _language_name(code: str) -> str:
        normalized = code.strip().lower().replace("_", "-")
        mapping = {
            "en": "English",
            "zh": "Chinese",
            "zh-cn": "Simplified Chinese",
            "zh-tw": "Traditional Chinese",
            "ja": "Japanese",
            "ko": "Korean",
            "es": "Spanish",
            "fr": "French",
            "de": "German",
        }
        return mapping.get(normalized, normalized or "English")
