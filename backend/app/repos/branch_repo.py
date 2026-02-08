from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Branch
from app.utils.time_utils import utc_now


class BranchRepo:
    """Repository for branch persistence."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_branch(
        self,
        branch_id: str,
        session_id: str,
        name: str,
        parent_branch_id: Optional[str] = None,
        fork_from_message_id: Optional[str] = None,
    ) -> Branch:
        """Create and persist a new branch."""

        branch = Branch(
            id=branch_id,
            session_id=session_id,
            name=name,
            parent_branch_id=parent_branch_id,
            fork_from_message_id=fork_from_message_id,
            is_archived=False,
            created_at=utc_now(),
        )
        self._db.add(branch)
        await self._db.flush()
        return branch

    async def get_branch(self, branch_id: str) -> Optional[Branch]:
        """Fetch a branch by ID."""

        result = await self._db.execute(select(Branch).where(Branch.id == branch_id))
        return result.scalar_one_or_none()
