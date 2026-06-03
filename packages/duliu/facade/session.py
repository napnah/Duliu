import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from duliu.db.models import ContestSet, Problem, Session, SessionMessage, Workspace
from duliu.facade.events import emit_event
from duliu.facade.secrets import apply_workspace_secrets
from duliu.session.agent import SessionAgent


class SessionFacade:
    @staticmethod
    async def create_session(
        session: AsyncSession,
        workspace: Workspace,
        *,
        problem_id: uuid.UUID | None = None,
        title: str = "Session",
    ) -> Session:
        chat = Session(workspace_id=workspace.id, problem_id=problem_id, title=title)
        session.add(chat)
        await session.flush()
        await emit_event(
            session,
            problem_id=problem_id,
            type="session.created",
            message=f"Session {chat.id} created",
            source="session",
        )
        return chat

    @staticmethod
    async def get_session(session: AsyncSession, session_id: uuid.UUID) -> Session | None:
        return await session.get(Session, session_id)

    @staticmethod
    async def list_messages(
        session: AsyncSession, session_id: uuid.UUID, limit: int = 50
    ) -> list[SessionMessage]:
        q = (
            select(SessionMessage)
            .where(SessionMessage.session_id == session_id)
            .order_by(SessionMessage.created_at.asc())
            .limit(limit)
        )
        return list((await session.execute(q)).scalars().all())

    @staticmethod
    async def chat(
        session: AsyncSession,
        chat: Session,
        message: str,
        *,
        problem: Problem | None = None,
        contest_set: ContestSet | None = None,
    ) -> tuple[SessionMessage, SessionMessage, list[dict]]:
        if problem is None and chat.problem_id:
            problem = await session.get(Problem, chat.problem_id)

        await apply_workspace_secrets(session, chat.workspace_id)

        user_msg = SessionMessage(session_id=chat.id, role="user", content=message)
        session.add(user_msg)
        await session.flush()

        agent = SessionAgent()
        reply_text, tools = await agent.reply(
            session, chat, problem, message, contest_set=contest_set
        )

        asst = SessionMessage(
            session_id=chat.id,
            role="assistant",
            content=reply_text,
            tool_calls_json={"tools": tools} if tools else None,
        )
        session.add(asst)

        if problem or contest_set:
            await emit_event(
                session,
                problem_id=problem.id if problem else None,
                contest_set_id=contest_set.id if contest_set else None,
                type="session.message",
                message=f"User: {message[:120]}",
                source="session",
                payload={"tools": tools},
            )

        await session.flush()
        return user_msg, asst, tools

    @staticmethod
    async def set_control_mode(
        session: AsyncSession, problem: Problem, mode: str
    ) -> Problem:
        if mode not in ("HUMAN", "AGENT", "HYBRID"):
            raise ValueError("control_mode must be HUMAN, AGENT, or HYBRID")
        problem.control_mode = mode
        await emit_event(
            session,
            problem_id=problem.id,
            type="session.control_mode",
            message=f"control_mode → {mode}",
            source="session",
        )
        await session.flush()
        return problem
