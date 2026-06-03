"""M15 Session Agent OpenAI tool schemas and execution."""

from __future__ import annotations

import json
import uuid
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
            "name": "polygon_api_sync",
            "description": "通过 Polygon 官方 API 同步题包列表（需 API Key）",
            "parameters": {
                "type": "object",
                "properties": {
                    "polygon_problem_id": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "polygon_api_build_package",
            "description": "调用 Polygon problem.buildPackage（需 API Key 与关联 problem_id）",
            "parameters": {
                "type": "object",
                "properties": {
                    "full": {"type": "boolean"},
                    "verify": {"type": "boolean"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "import_polygon_package",
            "description": "从 Polygon zip 导入工件到题目（std/brute/statement/tests 等）",
            "parameters": {
                "type": "object",
                "properties": {"zip_path": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_counterexamples",
            "description": "列出题目已归档的对拍反例",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "polygon_api_download_package",
            "description": "从 Polygon 下载最新 package zip 到本地",
            "parameters": {
                "type": "object",
                "properties": {
                    "package_id": {"type": "integer"},
                    "package_type": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "package_sync_polygon",
            "description": "本地导出 + Polygon buildPackage + 下载落盘",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stress_interpret",
            "description": "解读最近一次对拍结果（LLM/规则）",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stress_preflight",
            "description": "STRESS 预检：检查 std/brute 并返回对拍建议（不排队 job）",
            "parameters": {"type": "object", "properties": {}},
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

    if name == "polygon_api_sync":
        if not problem:
            return json.dumps({"error": "no_problem_context"}, ensure_ascii=False)
        from duliu.polygon.api_ops import link_polygon_problem, sync_polygon_packages

        ws_id = problem.workspace_id
        if args.get("polygon_problem_id"):
            await link_polygon_problem(
                session,
                problem,
                workspace_id=ws_id,
                polygon_problem_id=int(args["polygon_problem_id"]),
            )
        report = await sync_polygon_packages(session, problem, workspace_id=ws_id)
        return json.dumps(report, ensure_ascii=False)

    if name == "import_polygon_package":
        if not problem:
            return json.dumps({"error": "no_problem_context"}, ensure_ascii=False)
        from duliu.polygon.api_ops import import_polygon_package_for_problem

        report = await import_polygon_package_for_problem(
            session, problem, zip_path=args.get("zip_path")
        )
        return json.dumps(report, ensure_ascii=False)

    if name == "list_counterexamples":
        if not problem:
            return json.dumps({"error": "no_problem_context"}, ensure_ascii=False)
        items = (problem.spec_json or {}).get("stress_counterexamples") or []
        return json.dumps({"count": len(items), "items": items[-10:]}, ensure_ascii=False)

    if name == "polygon_api_download_package":
        if not problem:
            return json.dumps({"error": "no_problem_context"}, ensure_ascii=False)
        from duliu.polygon.api_ops import download_polygon_package

        report = await download_polygon_package(
            session,
            problem,
            workspace_id=problem.workspace_id,
            package_id=args.get("package_id"),
            package_type=args.get("package_type") or "standard",
        )
        return json.dumps(report, ensure_ascii=False)

    if name == "package_sync_polygon":
        if not problem:
            return json.dumps({"error": "no_problem_context"}, ensure_ascii=False)
        from duliu.polygon.api_ops import sync_package_with_polygon

        report = await sync_package_with_polygon(session, problem, workspace_id=problem.workspace_id)
        return json.dumps(report, ensure_ascii=False)

    if name == "stress_interpret":
        if not problem:
            return json.dumps({"error": "no_problem_context"}, ensure_ascii=False)
        from duliu.agents.stress_interpret import interpret_stress_report

        last = (problem.spec_json or {}).get("last_stress") or {}
        job_id = last.get("job_id")
        report = None
        if job_id:
            job = await JobFacade.get_job(session, uuid.UUID(str(job_id)))
            if job and job.result_json:
                report = job.result_json
        if not report:
            return json.dumps({"error": "no_stress_report"}, ensure_ascii=False)
        interp = await interpret_stress_report(problem, report)
        problem.spec_json = {**(problem.spec_json or {}), "last_stress": {**last, "interpretation": interp}}
        await session.flush()
        return json.dumps(interp, ensure_ascii=False)

    if name == "polygon_api_build_package":
        if not problem:
            return json.dumps({"error": "no_problem_context"}, ensure_ascii=False)
        from duliu.polygon.api_ops import build_polygon_package

        report = await build_polygon_package(
            session,
            problem,
            workspace_id=problem.workspace_id,
            full=bool(args.get("full")),
            verify=args.get("verify") is not False,
        )
        return json.dumps(report, ensure_ascii=False)

    if name == "stress_preflight":
        if not problem:
            return json.dumps({"error": "no_problem_context"}, ensure_ascii=False)
        from duliu.agents.stress_agent import (
            _llm_stress_preflight,
            _rule_stress_preflight,
        )

        std = await JobFacade.latest_artifact(session, problem.id, "std")
        brute = await JobFacade.latest_artifact(session, problem.id, "brute")
        gen = await JobFacade.latest_artifact(session, problem.id, "gen")
        missing = []
        if not std:
            missing.append("std")
        if not brute:
            missing.append("brute")
        pf = _rule_stress_preflight(problem, has_gen=bool(gen))
        if std and brute:
            llm = await _llm_stress_preflight(
                problem,
                std_preview=(std.content_text or "")[:400],
                brute_preview=(brute.content_text or "")[:400],
                has_gen=bool(gen),
            )
            if llm:
                pf = {**pf, **llm}
        return json.dumps({"ok": not missing, "missing": missing, "preflight": pf}, ensure_ascii=False)

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
