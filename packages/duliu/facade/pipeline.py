import hashlib
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from duliu.agents.adversarial import report_to_artifact_content, run_adversarial_review
from duliu.agents.editorial import run_editorial_draft
from duliu.agents.package import run_package_build
from duliu.db.models import (
    Artifact,
    Problem,
    ProblemStage,
    StageStatus,
    stage_order_for,
)
from duliu.facade.events import emit_event
from duliu.facade.import_gate import validate_approve, validate_dispatch


class PipelineFacade:
    @staticmethod
    def next_stage(problem: Problem, current: str) -> str | None:
        order = stage_order_for(problem.contest_style, problem.originality)
        try:
            idx = order.index(current)
        except ValueError:
            return None
        if idx + 1 >= len(order):
            return None
        return order[idx + 1]

    @staticmethod
    async def approve_stage(
        session: AsyncSession,
        problem: Problem,
        stage_id: str,
        *,
        approved_by: str = "human",
        note: str | None = None,
    ) -> Problem:
        result = await session.execute(
            select(ProblemStage).where(
                ProblemStage.problem_id == problem.id,
                ProblemStage.stage_id == stage_id,
            )
        )
        stage = result.scalar_one_or_none()
        if not stage:
            raise ValueError(f"Unknown stage {stage_id}")

        if problem.current_stage != stage_id:
            raise ValueError(f"Problem is at {problem.current_stage}, not {stage_id}")

        validate_approve(problem, stage_id)

        stage.status = StageStatus.APPROVED.value
        stage.approved_by = approved_by
        stage.approved_at = datetime.now(timezone.utc)
        stage.note = note

        nxt = PipelineFacade.next_stage(problem, stage_id)
        if nxt:
            problem.current_stage = nxt
            res2 = await session.execute(
                select(ProblemStage).where(
                    ProblemStage.problem_id == problem.id,
                    ProblemStage.stage_id == nxt,
                )
            )
            next_row = res2.scalar_one_or_none()
            if next_row:
                next_row.status = StageStatus.AWAITING_HUMAN.value
        else:
            problem.current_stage = "DONE"

        await emit_event(
            session,
            problem_id=problem.id,
            type="gate.approved",
            message=f"Stage {stage_id} approved",
            source="pipeline",
            stage_id=stage_id,
            payload={"next": nxt or "DONE", "note": note, "by": approved_by},
        )
        await session.flush()
        return problem

    @staticmethod
    async def reject_stage(
        session: AsyncSession,
        problem: Problem,
        stage_id: str,
        *,
        note: str,
    ) -> Problem:
        result = await session.execute(
            select(ProblemStage).where(
                ProblemStage.problem_id == problem.id,
                ProblemStage.stage_id == stage_id,
            )
        )
        stage = result.scalar_one_or_none()
        if not stage:
            raise ValueError(f"Unknown stage {stage_id}")
        stage.status = StageStatus.REJECTED.value
        stage.note = note
        await emit_event(
            session,
            problem_id=problem.id,
            type="gate.rejected",
            message=f"Stage {stage_id} rejected: {note}",
            source="pipeline",
            stage_id=stage_id,
            level="WARN",
        )
        await session.flush()
        return problem

    @staticmethod
    async def dispatch(
        session: AsyncSession,
        problem: Problem,
        stage_id: str,
        *,
        reason: str = "",
        run_id: uuid.UUID | None = None,
    ) -> dict:
        """M2/M3 dispatch; M7 optional LangGraph wrapper."""
        from duliu.config import settings

        if settings.use_langgraph:
            try:
                from duliu.pipeline.langgraph_runner import invoke_dispatch

                return await invoke_dispatch(
                    session, problem, stage_id, reason=reason, run_id=run_id
                )
            except (ImportError, ModuleNotFoundError):
                pass
        return await PipelineFacade.dispatch_core(
            session, problem, stage_id, reason=reason, run_id=run_id
        )

    @staticmethod
    async def dispatch_core(
        session: AsyncSession,
        problem: Problem,
        stage_id: str,
        *,
        reason: str = "",
        run_id: uuid.UUID | None = None,
    ) -> dict:
        """Core dispatch implementation (used by LangGraph node and direct path)."""
        rid = run_id or uuid.uuid4()
        if problem.current_stage != stage_id:
            raise ValueError(f"Problem is at {problem.current_stage}, cannot dispatch {stage_id}")

        validate_dispatch(problem, stage_id)

        res = await session.execute(
            select(ProblemStage).where(
                ProblemStage.problem_id == problem.id,
                ProblemStage.stage_id == stage_id,
            )
        )
        stage = res.scalar_one_or_none()
        if not stage:
            raise ValueError(f"Unknown stage {stage_id}")

        stage.status = StageStatus.AGENT_WORKING.value
        await emit_event(
            session,
            problem_id=problem.id,
            run_id=rid,
            type="pipeline.dispatch.start",
            message=f"Dispatch {stage_id}: {reason or 'started'}",
            source="pipeline",
            stage_id=stage_id,
            payload={"reason": reason},
        )

        result: dict
        if stage_id == "ADVERSARIAL_REVIEW":
            report = await run_adversarial_review(session, problem)
            content = report_to_artifact_content(report)
            latest = (
                await session.execute(
                    select(Artifact)
                    .where(Artifact.problem_id == problem.id, Artifact.kind == "adversarial_report")
                    .order_by(Artifact.version.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            ver = (latest.version + 1) if latest else 1
            session.add(
                Artifact(
                    problem_id=problem.id,
                    kind="adversarial_report",
                    version=ver,
                    content_text=content,
                    sha256=hashlib.sha256(content.encode()).hexdigest(),
                    author="adversarial_agent",
                    language=None,
                )
            )
            stage.status = StageStatus.AWAITING_HUMAN.value
            result = {"stage": stage_id, "report": report, "artifact_kind": "adversarial_report"}
            await emit_event(
                session,
                problem_id=problem.id,
                run_id=rid,
                type="pipeline.dispatch.done",
                message=report["summary"],
                source="pipeline",
                stage_id=stage_id,
                level="INFO" if report["ok"] else "WARN",
                payload=report,
            )
        elif stage_id == "PACKAGE":
            report = await run_package_build(session, problem)
            stage.status = StageStatus.AWAITING_HUMAN.value
            result = {"stage": stage_id, "report": report, "artifact_kind": "polygon_manifest"}
            await emit_event(
                session,
                problem_id=problem.id,
                run_id=rid,
                type="pipeline.dispatch.done",
                message=report["summary"],
                source="pipeline",
                stage_id=stage_id,
                level="INFO" if report.get("ok") else "WARN",
                payload=report,
            )
        elif stage_id == "EDITORIAL":
            report = await run_editorial_draft(session, problem)
            stage.status = StageStatus.AWAITING_HUMAN.value
            result = {"stage": stage_id, "report": report, "artifact_kind": "editorial"}
            await emit_event(
                session,
                problem_id=problem.id,
                run_id=rid,
                type="pipeline.dispatch.done",
                message=report["summary"],
                source="pipeline",
                stage_id=stage_id,
                payload=report,
            )
        elif stage_id == "STRESS":
            from duliu.agents.stress_agent import run_stress_agent

            report = await run_stress_agent(session, problem, mode="quick")
            stage.status = StageStatus.AWAITING_HUMAN.value
            result = {"stage": stage_id, "report": report, "agent": report.get("mode")}
            await emit_event(
                session,
                problem_id=problem.id,
                run_id=rid,
                type="pipeline.dispatch.done",
                message=report.get("summary", "STRESS agent"),
                source="pipeline",
                stage_id=stage_id,
                level="INFO" if report.get("ok") else "WARN",
                payload=report,
            )
        else:
            from duliu.agents.stage_agents import STAGE_LLM_STAGES, run_stage_agent

            if stage_id in STAGE_LLM_STAGES:
                report = await run_stage_agent(session, problem, stage_id)
                stage.status = StageStatus.AWAITING_HUMAN.value
                result = {"stage": stage_id, "report": report, "agent": report.get("mode")}
                await emit_event(
                    session,
                    problem_id=problem.id,
                    run_id=rid,
                    type="pipeline.dispatch.done",
                    message=report.get("summary", f"Stage {stage_id} agent done"),
                    source="pipeline",
                    stage_id=stage_id,
                    level="INFO" if report.get("ok") else "WARN",
                    payload=report,
                )
            else:
                stage.status = StageStatus.AWAITING_HUMAN.value
                result = {
                    "stage": stage_id,
                    "status": "awaiting_human",
                    "hint": "请用 Web 编辑器保存工件后人工 Gate",
                }
                await emit_event(
                    session,
                    problem_id=problem.id,
                    run_id=rid,
                    type="pipeline.dispatch.done",
                    message=f"Stage {stage_id} ready for human review",
                    source="pipeline",
                    stage_id=stage_id,
                    payload=result,
                )

        await session.flush()
        return {"run_id": str(rid), **result}
