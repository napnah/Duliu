"""M14 WebSocket job status stream."""

from __future__ import annotations

import asyncio
import uuid

from duliu.db.models import JobStatus, RunnerJob


async def ws_job_loop(send_json, session_factory, job_id: uuid.UUID, *, poll_seconds: float) -> None:
    await send_json({"type": "connected", "transport": "job_websocket", "job_id": str(job_id)})
    while True:
        async with session_factory() as session:
            job = await session.get(RunnerJob, job_id)
        if not job:
            await send_json({"type": "error", "message": "job not found"})
            return
        payload = {
            "type": "progress",
            "job_id": str(job.id),
            "kind": job.kind,
            "status": job.status,
            "result_json": job.result_json,
            "log_text": (job.log_text or "")[:500],
        }
        await send_json(payload)
        if job.status in (JobStatus.DONE.value, JobStatus.FAILED.value):
            await send_json({**payload, "type": "done"})
            return
        await asyncio.sleep(poll_seconds)
