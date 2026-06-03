"""M6 ProblemGraph orchestrator — wraps PipelineFacade with explicit stage graph."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from duliu.db.models import Problem, stage_order_for
from duliu.facade.pipeline import PipelineFacade


@dataclass
class GraphNode:
    stage_id: str
    index: int
    status: str | None = None


class PipelineOrchestrator:
    """Explicit stage graph for Web/CLI; swap-in point for LangGraph later."""

    @staticmethod
    def nodes_for(problem: Problem) -> list[GraphNode]:
        order = stage_order_for(problem.contest_style, problem.originality)
        return [GraphNode(stage_id=s, index=i) for i, s in enumerate(order)]

    @staticmethod
    async def snapshot(session: AsyncSession, problem: Problem) -> dict:
        from sqlalchemy import select
        from duliu.db.models import ProblemStage
        from duliu.facade.import_gate import (
            import_check_passed,
            import_ready,
            submission_confirmed,
        )

        order = stage_order_for(problem.contest_style, problem.originality)
        rows = (
            await session.execute(
                select(ProblemStage).where(ProblemStage.problem_id == problem.id)
            )
        ).scalars().all()
        by_id = {r.stage_id: r for r in rows}
        nodes = []
        for i, sid in enumerate(order):
            row = by_id.get(sid)
            nodes.append(
                {
                    "stage_id": sid,
                    "index": i,
                    "status": row.status if row else "PENDING",
                    "is_current": sid == problem.current_stage,
                }
            )
        imp = problem.spec_json.get("import") or {}
        return {
            "problem_id": str(problem.id),
            "originality": problem.originality,
            "current_stage": problem.current_stage,
            "nodes": nodes,
            "import": {
                "status": imp.get("status"),
                "import_check_ok": import_check_passed(problem),
                "submission_confirmed": submission_confirmed(problem),
                "problem_url": imp.get("problem_url"),
            },
        }

    @staticmethod
    async def run_dispatch(
        session: AsyncSession,
        problem: Problem,
        stage_id: str,
        *,
        reason: str = "",
    ) -> dict:
        return await PipelineFacade.dispatch(session, problem, stage_id, reason=reason)

    @staticmethod
    async def run_approve(
        session: AsyncSession,
        problem: Problem,
        stage_id: str,
        *,
        note: str | None = None,
    ) -> Problem:
        return await PipelineFacade.approve_stage(
            session, problem, stage_id, approved_by="human", note=note
        )
