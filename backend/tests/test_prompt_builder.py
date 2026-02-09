from __future__ import annotations

from app.services.prompt_builder import PromptBuilder


def test_prompt_builder_includes_crisis_focus_broad_label_rule() -> None:
    builder = PromptBuilder()
    messages = builder.build_messages(
        world_preset="Test world",
        timeline=[],
        interventions=[],
        tick_label="1个月",
        output_language="zh-cn",
    )
    assert len(messages) == 2
    system_prompt = messages[0]["content"]
    user_prompt = messages[1]["content"]

    assert "crisis_focus must be a broad crisis noun label" in system_prompt
    assert "Do not put sentences, locations, numbers" in system_prompt
    assert "For crisis_focus, return only a short broad category noun" in user_prompt
