"""M15 Session Agent OpenAI tool schemas and execution."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from duliu.db.models import ContestSet, Problem, ProblemStage
from duliu.facade.contest import ContestFacade
from duliu.facade.jobs import JobFacade
from duliu.facade.monitor import MonitorFacade
from duliu.facade.pipeline import PipelineFacade

SESSION_TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "dispatch_stage",
            "description": "调度题目的指定流水线阶段",
            "parameters": {
                "type": "object",
                "properties": {
                    "stage_id": {
                        "type": "string",
                        "enum": [
                            "SPEC",
                            "STATEMENT",
                            "SOLUTION",
                            "GENERATOR",
                            "STRESS",
                            "ADVERSARIAL_REVIEW",
                            "PACKAGE",
                            "EDITORIAL",
                            "IMPORT",
                        ],
                    },
                    "reason": {"type": "string"},
                },
                "required": ["stage_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "approve_stage",
            "description": "通过（批准）当前题目的指定阶段 Gate",
            "parameters": {
                "type": "object",
                "properties": {
                    "stage_id": {"type": "string"},
                    "note": {"type": "string"},
                },
                "required": ["stage_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "enqueue_stress",
            "description": "排队运行 std+brute 对拍",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "enum": ["quick", "import_check"]},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "problem_status",
            "description": "查询题目各阶段状态",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recent_events",
            "description": "查询题目最近监控事件",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer"}},
            },
        },
    },
]


async def execute_session_tool(
    session: AsyncSession,
    *,
    problem: Problem | None,
    contest_set: ContestSet | None,
    name: str,
    arguments: dict[str, Any],
) -> str:
    args = arguments or {}
    if name == "dispatch_stage":
        if not problem:
            return "无题目上下文，无法 dispatch"
        stage = (args.get("stage_id") or "").upper()
        if stage == "ADVERSARIAL":
            stage = "ADVERSARIAL_REVIEW"
        out = await PipelineFacade.dispatch(
            session, problem, stage, reason=args.get("reason") or "session_tool"
        )
        rep = out.get("report") or {}
        return json.dumps(
            {"ok": True, "run_id": out.get("run_id"), "summary": rep.get("summary", out.get("hint"))},
            ensure_ascii=False,
        )

    if name == "approve_stage":
        if not problem:
            return "无题目上下文"
        stage = (args.get("stage_id") or "").upper()
        if stage == "ADVERSARIAL":
            stage = "ADVERSARIAL_REVIEW"
        await PipelineFacade.approve_stage(
            session, problem, stage, approved_by="session_tool", note=args.get("note")
        )
        return json.dumps({"ok": True, "current_stage": problem.current_stage}, ensure_ascii=False)

    if name == "enqueue_stress":
        if not problem:
            return "无题目上下文"
        job = await JobFacade.enqueue_stress(session, problem, mode=args.get("mode") or "quick")
        return json.dumps({"ok": True, "job_id": str(job.id)}, ensure_ascii=False)

    if name == "problem_status":
        if not problem:
            return "无题目上下文"
        rows = (
            await session.execute(select(ProblemStage).where(ProblemStage.problem_id == problem.id))
        ).scalars().all()
        return json.dumps(
            {
                "title": problem.title,
                "current_stage": problem.current_stage,
                "stages": [{"id": s.stage_id, "status": s.status} for s in rows],
            },
            ensure_ascii=False,
        )

    if name == "recent_events":
        if not problem:
            return "无题目上下文"
        limit = int(args.get("limit") or 8)
        events = await MonitorFacade.query_recent_events(session, problem_id=problem.id, limit=limit)
        return json.dumps(
            [{"type": e.type, "message": e.message, "source": e.source} for e in events],
            ensure_ascii=False,
        )

    if name == "evaluate_contest_set" and contest_set:
        report = await ContestFacade.evaluate_set(session, contest_set)
        return json.dumps(report, ensure_ascii=False)

    return json.dumps({"error": f"unknown_tool:{name}"}, ensure_ascii=False)
