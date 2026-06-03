"""M5 crawl import facade."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from duliu.crawler.whitelist import validate_url
from duliu.db.models import Problem, ProblemStage, StageStatus, Workspace, stage_order_for
from duliu.facade.events import emit_event
from duliu.facade.jobs import JobFacade


class CrawlFacade:
    @staticmethod
    async def create_import_problem(
        session: AsyncSession,
        workspace: Workspace,
        *,
        url: str,
        title: str | None = None,
    ) -> Problem:
        platform, norm_url = validate_url(url)
        display = title or f"Import {platform}"
        problem = Problem(
            workspace_id=workspace.id,
            title=display,
            originality="NON_ORIGINAL",
            problem_type="TRADITIONAL",
            contest_style="ICPC",
            control_mode="HUMAN",
            current_stage="IMPORT",
            spec_json={
                "import": {
                    "status": "queued",
                    "platform": platform,
                    "problem_url": norm_url,
                    "keep_title": bool(title),
                    "submission_requirement": {"required": True, "user_confirmed": False},
                },
                "limits": {"time_ms": 1000, "memory_mb": 256},
                "samples": [],
            },
        )
        session.add(problem)
        await session.flush()
        order = stage_order_for("ICPC", "NON_ORIGINAL")
        for sid in order:
            session.add(
                ProblemStage(
                    problem_id=problem.id,
                    stage_id=sid,
                    status=StageStatus.AWAITING_HUMAN.value
                    if sid == "IMPORT"
                    else StageStatus.PENDING.value,
                )
            )
        problem.spec_json = {**problem.spec_json, "_stage_order": order}
        await emit_event(
            session,
            problem_id=problem.id,
            type="crawler.import.queued",
            message=f"Queued import from {norm_url}",
            source="crawler",
            payload={"url": norm_url},
        )
        return problem

    @staticmethod
    async def enqueue_crawl(
        session: AsyncSession,
        problem: Problem,
        *,
        url: str,
        workspace_id: uuid.UUID,
    ):
        validate_url(url)
        return await JobFacade.enqueue_crawl(session, problem, url=url, workspace_id=str(workspace_id))
