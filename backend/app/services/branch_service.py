from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.websocket import WebSocketManager
from app.db.models import Branch, TimelineMessage, UserIntervention
from app.repos.branch_repo import BranchRepo
from app.repos.message_repo import MessageRepo
from app.repos.session_repo import SessionRepo
from app.schemas.timeline import TimelineMessageOut
from app.services.memory_service import MemoryService


@dataclass
class BranchOperationError(RuntimeError):
    """Domain error for branch/timeline operations."""

    code: str
    message: str


class BranchService:
    """Handle branch and rollback workflows."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        ws_manager: WebSocketManager,
        memory_service: MemoryService,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._ws_manager = ws_manager
        self._memory_service = memory_service

    def set_memory_service(self, memory_service: MemoryService) -> None:
        """Swap memory service implementation at runtime."""

        self._memory_service = memory_service

    async def list_branches(self, session_id: str) -> tuple[Optional[str], list[Branch]]:
        """Return active branch id and branch list for a session."""

        async with self._sessionmaker() as db:
            session_repo = SessionRepo(db)
            branch_repo = BranchRepo(db)
            session = await session_repo.get_session(session_id)
            if not session:
                raise BranchOperationError("SESSION_NOT_FOUND", "Session not found")
            branches = await branch_repo.list_by_session(session_id)
            return session.active_branch_id, branches

    async def fork_branch(
        self,
        session_id: str,
        source_branch_id: str,
        from_message_id: Optional[str],
    ) -> Branch:
        """Fork a new branch from source history up to a message boundary."""

        async with self._sessionmaker() as db:
            session_repo = SessionRepo(db)
            branch_repo = BranchRepo(db)
            message_repo = MessageRepo(db)

            async with db.begin():
                session = await session_repo.get_session(session_id)
                if not session:
                    raise BranchOperationError("SESSION_NOT_FOUND", "Session not found")

                source_branch = await branch_repo.get_branch_in_session(session_id, source_branch_id)
                if not source_branch:
                    raise BranchOperationError("BRANCH_NOT_FOUND", "Source branch not found")

                fork_point = await self._resolve_fork_point(
                    message_repo=message_repo,
                    source_branch_id=source_branch.id,
                    from_message_id=from_message_id,
                )

                fork_from_message_id = fork_point.id if fork_point else None
                cutoff_seq = fork_point.seq if fork_point else 0
                new_branch_id = uuid.uuid4().hex
                new_branch_name = await self._next_branch_name(branch_repo, session_id, source_branch)

                new_branch = await branch_repo.create_branch(
                    branch_id=new_branch_id,
                    session_id=session_id,
                    name=new_branch_name,
                    parent_branch_id=source_branch.id,
                    fork_from_message_id=fork_from_message_id,
                )

                if cutoff_seq > 0:
                    source_messages = await message_repo.list_messages_up_to_seq(
                        source_branch.id, cutoff_seq
                    )
                    copied_messages = await message_repo.clone_messages_to_branch(
                        source_messages=source_messages,
                        session_id=session_id,
                        target_branch_id=new_branch.id,
                    )
                    await self._memory_service.remember_messages(
                        messages=copied_messages,
                        db=db,
                    )

            return new_branch

    async def switch_branch(self, session_id: str, branch_id: str) -> str:
        """Switch active branch for a session and broadcast change."""

        async with self._sessionmaker() as db:
            session_repo = SessionRepo(db)
            branch_repo = BranchRepo(db)
            async with db.begin():
                branch = await branch_repo.get_branch_in_session(session_id, branch_id)
                if not branch:
                    raise BranchOperationError("BRANCH_NOT_FOUND", "Branch not found")
                session = await session_repo.update_active_branch(session_id, branch_id)
                if not session:
                    raise BranchOperationError("SESSION_NOT_FOUND", "Session not found")

        await self._ws_manager.broadcast(
            session_id,
            {"event": "branch_switched", "active_branch_id": branch_id},
        )
        return branch_id

    async def delete_last_message(
        self, session_id: str, branch_id: Optional[str]
    ) -> TimelineMessage:
        """Delete the latest timeline message from a branch."""

        async with self._sessionmaker() as db:
            session_repo = SessionRepo(db)
            branch_repo = BranchRepo(db)
            message_repo = MessageRepo(db)

            async with db.begin():
                session = await session_repo.get_session(session_id)
                if not session:
                    raise BranchOperationError("SESSION_NOT_FOUND", "Session not found")
                target_branch_id = branch_id or session.active_branch_id
                if not target_branch_id:
                    raise BranchOperationError("BRANCH_NOT_FOUND", "Branch not found")

                branch = await branch_repo.get_branch_in_session(session_id, target_branch_id)
                if not branch:
                    raise BranchOperationError("BRANCH_NOT_FOUND", "Branch not found")

                deleted = await message_repo.delete_last_message(target_branch_id)
                if not deleted:
                    raise BranchOperationError("MESSAGE_NOT_FOUND", "No message to delete")
                await self._memory_service.invalidate_message(
                    session_id=session_id,
                    branch_id=target_branch_id,
                    source_message_id=deleted.id,
                    db=db,
                )

            return deleted

    async def enqueue_intervention(
        self,
        session_id: str,
        branch_id: Optional[str],
        content: str,
    ) -> tuple[UserIntervention, TimelineMessage]:
        """Queue a pending intervention and mirror it to timeline."""

        async with self._sessionmaker() as db:
            session_repo = SessionRepo(db)
            branch_repo = BranchRepo(db)
            message_repo = MessageRepo(db)

            async with db.begin():
                session = await session_repo.get_session(session_id)
                if not session:
                    raise BranchOperationError("SESSION_NOT_FOUND", "Session not found")

                target_branch_id = branch_id or session.active_branch_id
                if not target_branch_id:
                    raise BranchOperationError("BRANCH_NOT_FOUND", "Branch not found")

                branch = await branch_repo.get_branch_in_session(session_id, target_branch_id)
                if not branch:
                    raise BranchOperationError("BRANCH_NOT_FOUND", "Branch not found")

                intervention = await message_repo.add_intervention(
                    intervention_id=uuid.uuid4().hex,
                    session_id=session_id,
                    branch_id=target_branch_id,
                    content=content,
                )
                intervention_message = await message_repo.add_message(
                    message_id=uuid.uuid4().hex,
                    session_id=session_id,
                    branch_id=target_branch_id,
                    role="user_intervention",
                    content=content,
                    time_jump_label=session.tick_label,
                    model_provider=None,
                    model_name=None,
                    token_in=None,
                    token_out=None,
                )
                await self._memory_service.remember_message(message=intervention_message, db=db)

            payload = TimelineMessageOut.model_validate(intervention_message).model_dump(mode="json")
            await self._ws_manager.broadcast(
                session_id,
                {
                    "event": "message_created",
                    "branch_id": intervention_message.branch_id,
                    "message": payload,
                },
            )
            return intervention, intervention_message

    async def _resolve_fork_point(
        self,
        message_repo: MessageRepo,
        source_branch_id: str,
        from_message_id: Optional[str],
    ) -> Optional[TimelineMessage]:
        """Resolve the message used as fork boundary."""

        if from_message_id:
            message = await message_repo.get_message(source_branch_id, from_message_id)
            if not message:
                raise BranchOperationError(
                    "MESSAGE_NOT_FOUND",
                    "Fork point message does not exist in source branch",
                )
            return message
        return await message_repo.get_last_message(source_branch_id)

    async def _next_branch_name(
        self, branch_repo: BranchRepo, session_id: str, source_branch: Branch
    ) -> str:
        """Generate a deterministic branch name per session."""

        branches = await branch_repo.list_by_session(session_id)
        return f"{source_branch.name}-fork-{len(branches) + 1}"


def get_branch_service(request: Request) -> BranchService:
    """Dependency to access branch service from app state."""

    return request.app.state.branch_service
