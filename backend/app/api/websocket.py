from __future__ import annotations

import asyncio
from typing import AsyncIterator

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repos.session_repo import SessionRepo

router = APIRouter()


class WebSocketManager:
    """Manage active WebSocket connections per session."""

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.setdefault(session_id, set()).add(websocket)

    async def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            connections = self._connections.get(session_id)
            if not connections:
                return
            connections.discard(websocket)
            if not connections:
                self._connections.pop(session_id, None)

    async def broadcast(self, session_id: str, payload: dict) -> None:
        async with self._lock:
            connections = list(self._connections.get(session_id, set()))
        if not connections:
            return
        stale: list[WebSocket] = []
        for websocket in connections:
            try:
                await websocket.send_json(payload)
            except Exception:  # noqa: BLE001
                stale.append(websocket)
        for websocket in stale:
            await self.disconnect(session_id, websocket)


def get_ws_manager(websocket: WebSocket) -> WebSocketManager:
    """Dependency to access the WebSocket manager from app state."""

    return websocket.app.state.ws_manager


async def get_ws_session(websocket: WebSocket) -> AsyncIterator[AsyncSession]:
    """Provide a database session for WebSocket handlers."""

    sessionmaker: async_sessionmaker[AsyncSession] = websocket.app.state.sessionmaker
    async with sessionmaker() as session:
        yield session


@router.websocket("/ws/{session_id}")
async def ws_session(
    websocket: WebSocket,
    session_id: str,
    db: AsyncSession = Depends(get_ws_session),
    manager: WebSocketManager = Depends(get_ws_manager),
) -> None:
    """WebSocket endpoint for session updates."""

    await manager.connect(session_id, websocket)
    session_repo = SessionRepo(db)
    session = await session_repo.get_session(session_id)
    if session:
        await websocket.send_json({"event": "session_state", "running": session.running})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(session_id, websocket)
