"""M10/M12 monitor event stream (SSE + WebSocket)."""

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


def event_to_dict(event: Event) -> dict:
    return {
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


def event_to_sse(event: Event) -> str:
    return f"data: {json.dumps(event_to_dict(event), ensure_ascii=False)}\n\n"


async def iter_new_events(
    session_factory,
    *,
    problem_id: uuid.UUID | None,
    contest_set_id: uuid.UUID | None,
    poll_seconds: float,
):
    """Yield new event batches forever."""
    cursor: uuid.UUID | None = None
    while True:
        async with session_factory() as session:
            events = await fetch_events_since(
                session,
                problem_id=problem_id,
                contest_set_id=contest_set_id,
                after_id=cursor,
                limit=100,
            )
        if events:
            cursor = events[-1].id
        yield events
        await asyncio.sleep(poll_seconds)


async def sse_event_generator(
    session_factory,
    *,
    problem_id: uuid.UUID | None,
    contest_set_id: uuid.UUID | None,
    poll_seconds: float = 2.0,
):
    yield "data: {\"type\":\"connected\"}\n\n"
    async for events in iter_new_events(
        session_factory,
        problem_id=problem_id,
        contest_set_id=contest_set_id,
        poll_seconds=poll_seconds,
    ):
        for e in events:
            yield event_to_sse(e)


async def ws_event_loop(
    send_json,
    session_factory,
    *,
    problem_id: uuid.UUID | None,
    contest_set_id: uuid.UUID | None,
    poll_seconds: float = 2.0,
) -> None:
    """Drive WebSocket with same DB poll loop as SSE."""
    await send_json({"type": "connected", "transport": "websocket"})
    async for events in iter_new_events(
        session_factory,
        problem_id=problem_id,
        contest_set_id=contest_set_id,
        poll_seconds=poll_seconds,
    ):
        for e in events:
            await send_json(event_to_dict(e))
