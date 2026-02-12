from __future__ import annotations

import re

SECRET_PATTERN = re.compile(r"(sk-[A-Za-z0-9]{6,})")


def redact_secrets(text: str) -> str:
    """Redact API keys or similar secrets from a string."""

    return SECRET_PATTERN.sub("sk-***", text)


def sanitize_text(text: str, max_length: int) -> str:
    """Trim and clamp user-provided text to a safe length."""

    cleaned = text.strip()
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length]
    return cleaned
