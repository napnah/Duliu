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
            "name": "evaluate_contest_set",
            "description": "运行套题评估（需套题上下文）",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "prepare_polygon_upload",
            "description": "导出 Polygon zip 并记录上传指引（需题目上下文）",
            "parameters": {
                "type": "object",
                "properties": {"force_reexport": {"type": "boolean"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "langgraph_history",
            "description": "查询题目或套题的 LangGraph checkpoint 历史",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer"},
                    "scope": {"type": "string", "enum": ["problem", "contest_set"]},
                },
            },
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

    if name == "evaluate_contest_set":
        if not contest_set:
            return json.dumps({"error": "no_contest_set_context"}, ensure_ascii=False)
        report = await ContestFacade.evaluate_set(session, contest_set)
        return json.dumps(report, ensure_ascii=False)

    if name == "prepare_polygon_upload":
        if not problem:
            return json.dumps({"error": "no_problem_context"}, ensure_ascii=False)
        from duliu.polygon.upload import prepare_polygon_upload

        ws_id = problem.workspace_id
        report = await prepare_polygon_upload(
            session,
            problem,
            workspace_id=ws_id,
            force_reexport=bool(args.get("force_reexport")),
        )
        return json.dumps(
            {
                "ok": report.get("ok"),
                "zip_path": (report.get("upload") or {}).get("zip_path"),
                "instructions": (report.get("upload") or {}).get("instructions"),
            },
            ensure_ascii=False,
        )

    if name == "langgraph_history":
        from duliu.config import settings as cfg
        from duliu.pipeline.langgraph_runner import langgraph_enabled, list_checkpoint_history

        if not langgraph_enabled():
            return json.dumps({"enabled": False, "history": []}, ensure_ascii=False)
        limit = int(args.get("limit") or 10)
        scope = (args.get("scope") or "problem").lower()
        if scope == "contest_set":
            if not contest_set:
                return json.dumps({"error": "no_contest_set_context"}, ensure_ascii=False)
            from duliu.pipeline.contest_langgraph_runner import list_contest_checkpoint_history

            thread_id = (contest_set.set_eval_json or {}).get("langgraph_thread_id") or str(
                contest_set.id
            )
            history = await list_contest_checkpoint_history(thread_id, limit=limit)
            return json.dumps(
                {"enabled": cfg.use_langgraph, "thread_id": thread_id, "history": history},
                ensure_ascii=False,
            )
        if not problem:
            return json.dumps({"error": "no_problem_context"}, ensure_ascii=False)
        thread_id = (problem.spec_json or {}).get("langgraph_thread_id") or str(problem.id)
        history = await list_checkpoint_history(thread_id, limit=limit)
        return json.dumps(
            {"enabled": True, "thread_id": thread_id, "history": history},
            ensure_ascii=False,
        )

    return json.dumps({"error": f"unknown_tool:{name}"}, ensure_ascii=False)
