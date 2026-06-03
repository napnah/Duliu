import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from duliu.db.models import Event


async def emit_event(
    session: AsyncSession,
    *,
    type: str,
    message: str,
    problem_id: uuid.UUID | None = None,
    contest_set_id: uuid.UUID | None = None,
    run_id: uuid.UUID | None = None,
    source: str = "system",
    level: str = "INFO",
    stage_id: str | None = None,
    job_id: uuid.UUID | None = None,
    payload: dict | None = None,
) -> Event:
    ev = Event(
        problem_id=problem_id,
        contest_set_id=contest_set_id,
        run_id=run_id,
        type=type,
        message=message,
        source=source,
        level=level,
        stage_id=stage_id,
        job_id=job_id,
        payload_json=payload or {},
    )
    session.add(ev)
    await session.flush()
    return ev
