"""M10 SSE monitor event stream."""

from __future__ import annotations

import asyncio
import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from duliu.db.models import Event


async def fetch_events_since(
    session: AsyncSession,
    *,
    problem_id: uuid.UUID | None = None,
    contest_set_id: uuid.UUID | None = None,
    after_id: uuid.UUID | None = None,
    limit: int = 50,
) -> list[Event]:
    q = select(Event).order_by(Event.created_at.asc()).limit(limit)
    if problem_id:
        q = q.where(Event.problem_id == problem_id)
    if contest_set_id:
        q = q.where(Event.contest_set_id == contest_set_id)
    if after_id:
        ref = await session.get(Event, after_id)
        if ref and ref.created_at:
            q = q.where(Event.created_at > ref.created_at)
    rows = (await session.execute(q)).scalars().all()
    return list(rows)


def event_to_sse(event: Event) -> str:
    payload = {
        "id": str(event.id),
        "created_at": event.created_at.isoformat() if event.created_at else None,
        "source": event.source,
        "type": event.type,
        "message": event.message,
        "problem_id": str(event.problem_id) if event.problem_id else None,
        "contest_set_id": str(event.contest_set_id) if event.contest_set_id else None,
        "run_id": str(event.run_id) if event.run_id else None,
        "level": event.level,
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def sse_event_generator(
    session_factory,
    *,
    problem_id: uuid.UUID | None,
    contest_set_id: uuid.UUID | None,
    poll_seconds: float = 2.0,
):
    last_id: uuid.UUID | None = None
    yield "data: {\"type\":\"connected\"}\n\n"
    while True:
        async with session_factory() as session:
            events = await fetch_events_since(
                session,
                problem_id=problem_id,
                contest_set_id=contest_set_id,
                after_id=last_id,
                limit=100,
            )
        for e in events:
            last_id = e.id
            yield event_to_sse(e)
        await asyncio.sleep(poll_seconds)
