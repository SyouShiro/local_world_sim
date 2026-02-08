from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import TimelineMessage, UserIntervention
from app.repos.message_repo import MessageRepo
from app.repos.session_pref_repo import SessionPreferenceRepo
from app.repos.session_repo import SessionRepo
from app.services.memory_service import MemoryService
from app.services.provider_service import ProviderService
from app.services.prompt_builder import PromptBuilder


class SimulationService:
    """Orchestrates one simulation tick and persists the result."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        prompt_builder: PromptBuilder,
        provider_service: ProviderService,
        memory_service: MemoryService,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._prompt_builder = prompt_builder
        self._provider_service = provider_service
        self._memory_service = memory_service

    async def generate_next(self, session_id: str) -> TimelineMessage:
        """Generate the next timeline report for the active branch."""

        async with self._sessionmaker() as db:
            session_repo = SessionRepo(db)
            preference_repo = SessionPreferenceRepo(db)
            message_repo = MessageRepo(db)

            session = await session_repo.get_session(session_id)
            if not session:
                raise ValueError("Session not found")
            if not session.active_branch_id:
                raise ValueError("Session has no active branch")

            timeline = await message_repo.list_messages(session.active_branch_id, limit=12)
            interventions = await message_repo.list_pending_interventions(
                session.id, session.active_branch_id, limit=20
            )
            preference = await preference_repo.get_by_session(session.id)
            snapshot = {
                "session_id": session.id,
                "branch_id": session.active_branch_id,
                "world_preset": session.world_preset,
                "tick_label": session.tick_label,
                "output_language": preference.output_language if preference else "en",
                "intervention_ids": [item.id for item in interventions],
            }

        memory_query = self._build_memory_query(
            world_preset=snapshot["world_preset"],
            timeline=timeline,
            interventions=interventions,
            tick_label=snapshot["tick_label"],
        )
        memory_snippets = await self._memory_service.retrieve_context(
            session_id=snapshot["session_id"],
            branch_id=snapshot["branch_id"],
            query_text=memory_query,
        )
        prompt_messages = self._prompt_builder.build_messages(
            world_preset=snapshot["world_preset"],
            timeline=timeline,
            interventions=interventions,
            tick_label=snapshot["tick_label"],
            memory_snippets=memory_snippets,
            output_language=snapshot["output_language"],
        )
        adapter, runtime_cfg = await self._provider_service.get_generation_config(session_id)
        result = await adapter.generate(runtime_cfg, prompt_messages, stream=False)

        async with self._sessionmaker() as db:
            message_repo = MessageRepo(db)
            async with db.begin():
                message = await message_repo.add_message(
                    message_id=self._new_id(),
                    session_id=snapshot["session_id"],
                    branch_id=snapshot["branch_id"],
                    role="system_report",
                    content=result.content,
                    time_jump_label=snapshot["tick_label"],
                    model_provider=result.model_provider,
                    model_name=result.model_name,
                    token_in=result.token_in,
                    token_out=result.token_out,
                )
                await message_repo.mark_interventions_consumed(snapshot["intervention_ids"])
                await self._memory_service.remember_message(message=message, db=db)
            return message

    @staticmethod
    def _new_id() -> str:
        """Create a new identifier for persisted entities."""

        import uuid

        return uuid.uuid4().hex

    @staticmethod
    def _build_memory_query(
        *,
        world_preset: str,
        timeline: list[TimelineMessage],
        interventions: list[UserIntervention],
        tick_label: str,
    ) -> str:
        recent_history = " ".join(item.content for item in timeline[-3:])
        pending = " ".join(item.content for item in interventions[-3:])
        return (
            "World preset: "
            f"{world_preset}\n"
            "Recent timeline focus: "
            f"{recent_history}\n"
            "Pending interventions: "
            f"{pending}\n"
            "Time advance label: "
            f"{tick_label}"
        )
