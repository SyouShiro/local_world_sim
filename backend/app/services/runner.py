from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.providers.base import ProviderError
from app.repos.session_repo import SessionRepo
from app.schemas.timeline import TimelineMessageOut
from app.services.simulation_service import SimulationService
from app.api.websocket import WebSocketManager


@dataclass
class RunnerHandle:
    """Track a runner task and its generation lock."""

    task: asyncio.Task
    generation_lock: asyncio.Lock


class RunnerManager:
    """Manage per-session runner tasks."""

    _BACKOFF_DELAYS = (1, 2, 4)

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        simulation_service: SimulationService,
        ws_manager: WebSocketManager,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._simulation_service = simulation_service
        self._ws_manager = ws_manager
        self._handles: dict[str, RunnerHandle] = {}
        self._handles_lock = asyncio.Lock()

    async def start(self, session_id: str) -> Optional[bool]:
        """Start a runner for the session if not already running."""

        running = await self._set_running(session_id, True)
        if running is None:
            return None
        await self._ensure_task(session_id)
        await self._ws_manager.broadcast(session_id, {"event": "session_state", "running": True})
        return running

    async def pause(self, session_id: str) -> Optional[bool]:
        """Pause the runner for the session."""

        running = await self._set_running(session_id, False)
        if running is None:
            return None
        await self._ws_manager.broadcast(session_id, {"event": "session_state", "running": False})
        return running

    async def resume(self, session_id: str) -> Optional[bool]:
        """Resume a paused runner."""

        return await self.start(session_id)

    async def shutdown(self) -> None:
        """Cancel all active runner tasks."""

        async with self._handles_lock:
            handles = list(self._handles.values())
            self._handles.clear()
        for handle in handles:
            handle.task.cancel()
        await asyncio.gather(*(handle.task for handle in handles), return_exceptions=True)

    async def is_generating(self, session_id: str) -> bool:
        """Return True when the runner is currently inside generation section."""

        async with self._handles_lock:
            handle = self._handles.get(session_id)
            if not handle or handle.task.done():
                return False
            return handle.generation_lock.locked()

    async def _set_running(self, session_id: str, running: bool) -> Optional[bool]:
        async with self._sessionmaker() as db:
            async with db.begin():
                repo = SessionRepo(db)
                session = await repo.update_running(session_id, running)
                if not session:
                    return None
                return session.running

    async def _ensure_task(self, session_id: str) -> None:
        async with self._handles_lock:
            existing = self._handles.get(session_id)
            if existing and not existing.task.done():
                return
            generation_lock = asyncio.Lock()
            task = asyncio.create_task(self._run_loop(session_id, generation_lock))
            self._handles[session_id] = RunnerHandle(task=task, generation_lock=generation_lock)

    async def _run_loop(self, session_id: str, generation_lock: asyncio.Lock) -> None:
        backoff_attempt = 0
        while True:
            try:
                delay = await self._get_post_delay(session_id)
                if delay is None:
                    break

                try:
                    async with generation_lock:
                        message = await self._simulation_service.generate_next(session_id)
                    backoff_attempt = 0
                except ProviderError as exc:
                    retry_delay = await self._handle_provider_error(
                        session_id, exc, backoff_attempt
                    )
                    if retry_delay is None:
                        break
                    backoff_attempt += 1
                    await asyncio.sleep(retry_delay)
                    continue
                except Exception as exc:  # noqa: BLE001
                    await self._stop_with_error(session_id, "RUNNER_FAILED", str(exc))
                    break

                message_payload = TimelineMessageOut.model_validate(message).model_dump(mode="json")
                await self._ws_manager.broadcast(
                    session_id,
                    {
                        "event": "message_created",
                        "branch_id": message.branch_id,
                        "message": message_payload,
                    },
                )
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                break

    async def _get_post_delay(self, session_id: str) -> Optional[int]:
        async with self._sessionmaker() as db:
            repo = SessionRepo(db)
            session = await repo.get_session(session_id)
            if not session or not session.running:
                return None
            return session.post_gen_delay_sec

    async def _handle_provider_error(
        self, session_id: str, exc: ProviderError, backoff_attempt: int
    ) -> Optional[int]:
        if not exc.retryable:
            await self._stop_with_error(session_id, exc.code, exc.message)
            return None

        retry_delay = self._next_backoff(backoff_attempt)
        if retry_delay is None:
            await self._stop_with_error(
                session_id,
                "ERROR_BACKOFF",
                "Provider failed repeatedly. Runner paused; resume to retry.",
            )
            return None

        await self._ws_manager.broadcast(
            session_id,
            {
                "event": "error",
                "code": exc.code,
                "message": f"{exc.message} Retrying in {retry_delay}s.",
            },
        )
        return retry_delay

    @classmethod
    def _next_backoff(cls, attempt: int) -> Optional[int]:
        if attempt >= len(cls._BACKOFF_DELAYS):
            return None
        return cls._BACKOFF_DELAYS[attempt]

    async def _stop_with_error(self, session_id: str, code: str, message: str) -> None:
        await self._set_running(session_id, False)
        await self._ws_manager.broadcast(
            session_id,
            {
                "event": "error",
                "code": code,
                "message": message,
            },
        )
        await self._ws_manager.broadcast(session_id, {"event": "session_state", "running": False})


def get_runner_manager(request: Request) -> RunnerManager:
    """Dependency to access the app runner manager."""

    return request.app.state.runner_manager
