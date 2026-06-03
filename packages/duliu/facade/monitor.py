import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from duliu.db.models import Event


class MonitorFacade:
    @staticmethod
    async def query_recent_events(
        session: AsyncSession,
        *,
        problem_id: uuid.UUID | None = None,
        run_id: uuid.UUID | None = None,
        limit: int = 20,
    ) -> list[Event]:
        q = select(Event).order_by(Event.created_at.desc()).limit(min(limit, 200))
        if problem_id:
            q = q.where(Event.problem_id == problem_id)
        if run_id:
            q = q.where(Event.run_id == run_id)
        return list((await session.execute(q)).scalars().all())
