from __future__ import annotations

from typing import Iterable, List

from app.db.models import TimelineMessage, UserIntervention
from app.memory.types import MemorySnippet


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
    ) -> List[dict]:
        """Create the message list for an LLM provider."""

        language_hint = self._language_name(output_language)
        system_prompt = (
            "You are generating a world progress report. "
            "Keep it concise, structured, and continuous. "
            "Output JSON with title, time_advance, summary, events, and risks. "
            f"Keep JSON keys in English. Write all human-readable values in {language_hint}."
        )
        history_lines = []
        for message in list(timeline)[-self._max_history :]:
            history_lines.append(f"#{message.seq} {message.content}")
        intervention_lines = [f"- {item.content}" for item in interventions]
        history_text = "\n".join(history_lines) if history_lines else "(none)"
        intervention_text = "\n".join(intervention_lines) if intervention_lines else "(none)"

        memory_section = self._build_memory_section(memory_snippets)
        if memory_section:
            user_prompt = (
                "World preset:\n"
                f"{world_preset}\n\n"
                "Recent timeline:\n"
                f"{history_text}\n\n"
                "Timeline clock:\n"
                f"Start at: {timeline_start_iso or '(auto)'}\n"
                f"Step: {timeline_step_value} {timeline_step_unit}\n\n"
                "Long-term memory context:\n"
                f"{memory_section}\n\n"
                "Pending interventions:\n"
                f"{intervention_text}\n\n"
                f"Time advance label: {tick_label}\n"
                "Return JSON only."
            )
        else:
            user_prompt = (
                "World preset:\n"
                f"{world_preset}\n\n"
                "Recent timeline:\n"
                f"{history_text}\n\n"
                "Timeline clock:\n"
                f"Start at: {timeline_start_iso or '(auto)'}\n"
                f"Step: {timeline_step_value} {timeline_step_unit}\n\n"
                "Pending interventions:\n"
                f"{intervention_text}\n\n"
                f"Time advance label: {tick_label}\n"
                "Return JSON only."
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
