from __future__ import annotations

import logging

from app.core.security import redact_secrets


class RedactionFilter(logging.Filter):
    """Log filter that redacts sensitive data before output."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_secrets(str(record.msg))
        if record.args:
            record.args = tuple(redact_secrets(str(arg)) for arg in record.args)
        return True


def setup_logging(level: str) -> None:
    """Configure application logging with secret redaction."""

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger().addFilter(RedactionFilter())
