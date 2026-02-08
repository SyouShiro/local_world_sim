from __future__ import annotations

from typing import Iterable, List

from app.db.models import TimelineMessage, UserIntervention


class PromptBuilder:
    """Compose prompts for LLM generation."""

    def __init__(self, max_history: int = 12) -> None:
        self._max_history = max_history

    def build_messages(
        self,
        world_preset: str,
        timeline: Iterable[TimelineMessage],
        interventions: Iterable[UserIntervention],
        tick_label: str,
    ) -> List[dict]:
        """Create the message list for an LLM provider."""

        system_prompt = (
            "You are generating a world progress report. "
            "Keep it concise, structured, and continuous. "
            "Output JSON with title, time_advance, summary, events, and risks."
        )
        history_lines = []
        for message in list(timeline)[-self._max_history :]:
            history_lines.append(f"#{message.seq} {message.content}")
        intervention_lines = [f"- {item.content}" for item in interventions]
        history_text = "\n".join(history_lines) if history_lines else "(none)"
        intervention_text = "\n".join(intervention_lines) if intervention_lines else "(none)"
        user_prompt = (
            "World preset:\n"
            f"{world_preset}\n\n"
            "Recent timeline:\n"
            f"{history_text}\n\n"
            "Pending interventions:\n"
            f"{intervention_text}\n\n"
            f"Time advance label: {tick_label}\n"
            "Return JSON only."
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
