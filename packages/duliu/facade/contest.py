import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from duliu.agents.set_evaluator import run_set_evaluation, save_set_evaluation_artifact
from duliu.db.models import (
    M3_STAGE_ORDER,
    ContestSet,
    ContestSlot,
    Problem,
    ProblemStage,
    StageStatus,
)
from duliu.facade.events import emit_event
from duliu.facade.pipeline import PipelineFacade


class ContestFacade:
    @staticmethod
    async def get_detail(session: AsyncSession, contest_set_id: uuid.UUID) -> dict | None:
        cs = await session.get(ContestSet, contest_set_id)
        if not cs:
            return None
        slots = (
            await session.execute(
                select(ContestSlot)
                .where(ContestSlot.contest_set_id == cs.id)
                .order_by(ContestSlot.slot_label)
            )
        ).scalars().all()
        slot_rows = []
        for slot in slots:
            row = {
                "id": str(slot.id),
                "slot_label": slot.slot_label,
                "status": slot.status,
                "problem_id": str(slot.problem_id) if slot.problem_id else None,
            }
            if slot.problem_id:
                p = await session.get(Problem, slot.problem_id)
                if p:
                    row["problem"] = {
                        "id": str(p.id),
                        "title": p.title,
                        "current_stage": p.current_stage,
                        "problem_type": p.problem_type,
                        "spec_json": p.spec_json,
                    }
            slot_rows.append(row)
        return {
            "id": str(cs.id),
            "name": cs.name,
            "contest_style": cs.contest_style,
            "slot_count": cs.slot_count,
            "status": cs.status,
            "target_difficulty_json": cs.target_difficulty_json,
            "set_eval_json": cs.set_eval_json,
            "slots": slot_rows,
        }

    @staticmethod
    async def bind_problem_to_slot(
        session: AsyncSession,
        contest_set: ContestSet,
        slot_label: str,
        problem_id: uuid.UUID,
    ) -> ContestSlot:
        result = await session.execute(
            select(ContestSlot).where(
                ContestSlot.contest_set_id == contest_set.id,
                ContestSlot.slot_label == slot_label,
            )
        )
        slot = result.scalar_one_or_none()
        if not slot:
            raise ValueError(f"Unknown slot {slot_label}")

        problem = await session.get(Problem, problem_id)
        if not problem:
            raise ValueError("problem not found")
        if problem.workspace_id != contest_set.workspace_id:
            raise ValueError("problem workspace mismatch")

        old_slots = (
            await session.execute(
                select(ContestSlot).where(
                    ContestSlot.contest_set_id == contest_set.id,
                    ContestSlot.problem_id == problem_id,
                )
            )
        ).scalars().all()
        for s in old_slots:
            if s.id != slot.id:
                s.problem_id = None
                s.status = "EMPTY"

        slot.problem_id = problem_id
        slot.status = "ASSIGNED"
        problem.contest_set_id = contest_set.id
        problem.contest_style = contest_set.contest_style

        await emit_event(
            session,
            contest_set_id=contest_set.id,
            problem_id=problem_id,
            type="contest.slot.bind",
            message=f"Bound {problem.title} to slot {slot_label}",
            source="contest",
            payload={"slot_label": slot_label},
        )
        await session.flush()
        return slot

    @staticmethod
    async def create_problem_in_slot(
        session: AsyncSession,
        contest_set: ContestSet,
        slot_label: str,
        *,
        title: str,
        problem_type: str = "TRADITIONAL",
        rating: int | None = None,
    ) -> Problem:
        result = await session.execute(
            select(ContestSlot).where(
                ContestSlot.contest_set_id == contest_set.id,
                ContestSlot.slot_label == slot_label,
            )
        )
        slot = result.scalar_one_or_none()
        if not slot:
            raise ValueError(f"Unknown slot {slot_label}")

        spec: dict = {
            "limits": {"time_ms": 1000, "memory_mb": 256},
            "samples": [],
        }
        if rating is not None:
            spec["difficulty"] = {"rating": rating, "model": "codeforces"}

        problem = Problem(
            workspace_id=contest_set.workspace_id,
            contest_set_id=contest_set.id,
            title=title,
            originality=contest_set.originality_policy,
            problem_type=problem_type,
            contest_style=contest_set.contest_style,
            control_mode="HUMAN",
            current_stage="SPEC",
            spec_json=spec,
        )
        session.add(problem)
        await session.flush()
        for stage_id in M3_STAGE_ORDER:
            session.add(
                ProblemStage(
                    problem_id=problem.id,
                    stage_id=stage_id,
                    status=StageStatus.AWAITING_HUMAN.value
                    if stage_id == "SPEC"
                    else StageStatus.PENDING.value,
                )
            )
        await ContestFacade.bind_problem_to_slot(session, contest_set, slot_label, problem.id)
        return problem

    @staticmethod
    async def evaluate_set(session: AsyncSession, contest_set: ContestSet) -> dict:
        report = await run_set_evaluation(session, contest_set)
        contest_set.set_eval_json = report
        contest_set.status = "SET_EVAL_PENDING"
        await save_set_evaluation_artifact(session, contest_set, report)
        await emit_event(
            session,
            contest_set_id=contest_set.id,
            type="contest.set_eval.done",
            message=report["summary"],
            source="set_evaluator",
            level="INFO" if report["ok"] else "WARN",
            payload={"chart": report.get("chart"), "ok": report["ok"]},
        )
        await session.flush()
        return report

    @staticmethod
    async def approve_set_eval(
        session: AsyncSession,
        contest_set: ContestSet,
        *,
        approved_by: str = "human",
        note: str | None = None,
    ) -> ContestSet:
        if contest_set.status != "SET_EVAL_PENDING":
            raise ValueError(f"Contest set status is {contest_set.status}, not SET_EVAL_PENDING")
        report = contest_set.set_eval_json or {}
        if not report:
            raise ValueError("Run set evaluation first")
        contest_set.status = "SET_EVAL_APPROVED"
        report["approved_by"] = approved_by
        report["approved_at"] = datetime.now(timezone.utc).isoformat()
        report["note"] = note
        contest_set.set_eval_json = report
        await emit_event(
            session,
            contest_set_id=contest_set.id,
            type="contest.set_eval.approved",
            message="Set evaluation approved",
            source="contest",
            payload={"by": approved_by, "note": note},
        )
        await session.flush()
        return contest_set
