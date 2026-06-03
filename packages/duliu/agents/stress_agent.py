"""M15 STRESS stage agent: seed artifacts + enqueue stress job."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from duliu.config import settings
from duliu.db.models import Problem
from duliu.facade.import_flow import seed_brute_if_missing
from duliu.facade.jobs import JobFacade


async def run_stress_agent(
    session: AsyncSession,
    problem: Problem,
    *,
    mode: str = "quick",
) -> dict:
    """Ensure std/brute exist and queue stress job."""
    if not settings.stage_llm_enabled:
        return {"ok": False, "mode": "disabled", "summary": "STRESS agent disabled"}

    std = await JobFacade.latest_artifact(session, problem.id, "std")
    brute = await JobFacade.latest_artifact(session, problem.id, "brute")
    seeded_brute = False
    if not brute:
        seeded_brute = await seed_brute_if_missing(session, problem)
        brute = await JobFacade.latest_artifact(session, problem.id, "brute")

    missing = []
    if not std:
        missing.append("std")
    if not brute:
        missing.append("brute")

    if missing:
        return {
            "ok": False,
            "mode": "blocked",
            "summary": f"缺少工件: {', '.join(missing)}，请先完成 SOLUTION 或保存 std/brute",
            "missing": missing,
        }

    job = await JobFacade.enqueue_stress(session, problem, mode=mode)
    spec = dict(problem.spec_json or {})
    spec["last_stress"] = {
        "job_id": str(job.id),
        "mode": mode,
        "seeded_brute": seeded_brute,
    }
    problem.spec_json = spec

    return {
        "ok": True,
        "mode": "runner",
        "summary": f"已排队 {mode} 对拍 job={job.id}",
        "job_id": str(job.id),
        "seeded_brute": seeded_brute,
    }
