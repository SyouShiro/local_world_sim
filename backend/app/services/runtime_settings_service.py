from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from fastapi import FastAPI
from pydantic import TypeAdapter

from app.core.config import Settings
from app.core.logging import setup_logging
from app.services.memory_service import create_memory_service


class RuntimeSettingsService:
    """Manage runtime overrides for settings-backed components."""

    _ENV_ASSIGN_PATTERN = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=.*$")
    _SIMPLE_ENV_VALUE_PATTERN = re.compile(r"^[A-Za-z0-9_./:,@+-]+$")
    _PROJECT_ROOT = Path(__file__).resolve().parents[3]

    def __init__(
        self,
        app: FastAPI,
        settings: Settings,
        env_file_candidates: tuple[str, ...] = ("backend/.env", ".env"),
    ) -> None:
        self._app = app
        self._settings = settings
        self._env_file_path = self._resolve_env_file_path(env_file_candidates)
        self._alias_to_field: dict[str, str] = {}
        self._adapters: dict[str, TypeAdapter] = {}
        for name, field in Settings.model_fields.items():
            alias = field.alias or name
            self._alias_to_field[alias] = name
            self._adapters[alias] = TypeAdapter(field.annotation)

    def get_settings(self) -> dict[str, Any]:
        """Return current runtime settings with env aliases."""

        return self._settings.model_dump(by_alias=True)

    def update_settings(self, updates: dict[str, Any], *, persist: bool = True) -> dict[str, Any]:
        """Apply partial runtime updates and refresh dependent services."""

        changed_aliases: set[str] = set()
        for alias, raw_value in updates.items():
            field_name = self._alias_to_field.get(alias)
            if not field_name:
                raise ValueError(f"Unsupported setting key: {alias}")
            adapter = self._adapters[alias]
            parsed_value = adapter.validate_python(raw_value)
            setattr(self._settings, field_name, parsed_value)
            changed_aliases.add(alias)

        if changed_aliases:
            self._apply_runtime_side_effects(changed_aliases)
            if persist:
                self._persist_changed_aliases(changed_aliases)
        return self.get_settings()

    def _apply_runtime_side_effects(self, changed_aliases: set[str]) -> None:
        if "LOG_LEVEL" in changed_aliases:
            setup_logging(self._settings.log_level)

        # Prompt memory budget can be adjusted independently.
        if {
            "MEMORY_MAX_SNIPPETS",
            "MEMORY_MAX_CHARS",
        } & changed_aliases:
            self._app.state.prompt_builder.update_memory_limits(
                self._settings.memory_max_snippets,
                self._settings.memory_max_chars,
            )

        if {
            "EVENT_DICE_ENABLED",
            "EVENT_GOOD_EVENT_PROB",
            "EVENT_BAD_EVENT_PROB",
            "EVENT_MIN_EVENTS",
            "EVENT_MAX_EVENTS",
            "EVENT_DEFAULT_HEMISPHERE",
        } & changed_aliases:
            self._app.state.event_dice_service.reload(self._settings)

        if {
            "MEMORY_MODE",
            "MEMORY_MAX_SNIPPETS",
            "MEMORY_MAX_CHARS",
            "EMBED_PROVIDER",
            "EMBED_MODEL",
            "EMBED_DIM",
            "EMBED_OPENAI_API_KEY",
            "OPENAI_BASE_URL",
        } & changed_aliases:
            rebuilt_memory = create_memory_service(
                sessionmaker=self._app.state.sessionmaker,
                settings=self._settings,
            )
            self._app.state.memory_service = rebuilt_memory
            self._app.state.simulation_service.set_memory_service(rebuilt_memory)
            self._app.state.branch_service.set_memory_service(rebuilt_memory)

    def _resolve_env_file_path(self, env_file_candidates: tuple[str, ...]) -> Path:
        for candidate in env_file_candidates:
            resolved = self._resolve_candidate_path(candidate)
            if resolved.exists():
                return resolved
        return self._resolve_candidate_path(env_file_candidates[0])

    def _resolve_candidate_path(self, candidate: str) -> Path:
        path = Path(candidate)
        if path.is_absolute():
            return path
        return self._PROJECT_ROOT / path

    def _persist_changed_aliases(self, changed_aliases: set[str]) -> None:
        target = self._env_file_path
        target.parent.mkdir(parents=True, exist_ok=True)
        existing_lines = target.read_text(encoding="utf-8").splitlines() if target.exists() else []
        serialized = self._build_serialized_settings(changed_aliases)
        updated_lines: list[str] = []
        seen: set[str] = set()

        for line in existing_lines:
            match = self._ENV_ASSIGN_PATTERN.match(line)
            if not match:
                updated_lines.append(line)
                continue
            key = match.group(1)
            if key in serialized:
                updated_lines.append(f"{key}={serialized[key]}")
                seen.add(key)
            else:
                updated_lines.append(line)

        missing_keys = [key for key in serialized if key not in seen]
        if missing_keys:
            if updated_lines and updated_lines[-1].strip():
                updated_lines.append("")
            for key in missing_keys:
                updated_lines.append(f"{key}={serialized[key]}")

        target.write_text("\n".join(updated_lines).rstrip() + "\n", encoding="utf-8")

    def _build_serialized_settings(self, changed_aliases: set[str]) -> dict[str, str]:
        settings_map = self.get_settings()
        ordered_aliases = [
            alias
            for alias in self._alias_to_field
            if alias in changed_aliases and alias in settings_map
        ]
        return {
            alias: self._serialize_env_value(settings_map[alias])
            for alias in ordered_aliases
        }

    def _serialize_env_value(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float):
            return str(value)
        if isinstance(value, str):
            if value == "":
                return '""'
            if self._SIMPLE_ENV_VALUE_PATTERN.fullmatch(value):
                return value
            return json.dumps(value, ensure_ascii=False)
        return json.dumps(value, ensure_ascii=False)
