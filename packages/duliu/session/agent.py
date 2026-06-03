"""M2/M15 Session Agent: rules + OpenAI tool calling."""

from __future__ import annotations

import json
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from duliu.agents.llm_client import chat_messages
from duliu.config import settings
from duliu.db.models import ContestSet, Problem, ProblemStage, Session
from duliu.facade.contest import ContestFacade
from duliu.facade.jobs import JobFacade
from duliu.facade.monitor import MonitorFacade
from duliu.facade.pipeline import PipelineFacade
from duliu.session.tools import SESSION_TOOL_SCHEMAS, execute_session_tool


class SessionAgent:
    async def reply(
        self,
        session: AsyncSession,
        chat: Session,
        problem: Problem | None,
        user_text: str,
        *,
        contest_set: ContestSet | None = None,
    ) -> tuple[str, list[dict]]:
        tools_used: list[dict] = []
        text = user_text.strip()

        from duliu.agents.llm_config import get_active_llm

        if get_active_llm().is_configured() and settings.session_tools_enabled and problem:
            tool_reply = await self._try_tool_calling(
                session, problem, text, contest_set=contest_set
            )
            if tool_reply:
                content, used = tool_reply
                return (content, used)

        return await self._reply_rules(
            session, chat, problem, text, contest_set=contest_set, tools_used=tools_used
        )

    async def _try_tool_calling(
        self,
        session: AsyncSession,
        problem: Problem,
        text: str,
        *,
        contest_set: ContestSet | None,
    ) -> tuple[str, list[dict]] | None:
        tools_used: list[dict] = []
        ctx = f"题目={problem.title} 阶段={problem.current_stage} 风格={problem.contest_style}"
        if contest_set:
            ctx += f" 套题={contest_set.name}"
        messages: list[dict] = [
            {
                "role": "system",
                "content": (
                    "你是 Duliu Session Agent。用中文简洁回复。"
                    "需要操作时调用工具，不要编造 job_id。"
                    "五步出题：找题 find_problem、题面 write_statement、解法 solution_analysis、"
                    "数据 generate_data、题解 write_editorial — 用 run_creation_workflow。"
                    f" 上下文: {ctx}"
                ),
            },
            {"role": "user", "content": text},
        ]
        for _ in range(4):
            msg = await chat_messages(messages, tools=SESSION_TOOL_SCHEMAS)
            if not msg:
                return None
            tool_calls = msg.get("tool_calls") or []
            if tool_calls:
                messages.append(
                    {
                        "role": "assistant",
                        "content": msg.get("content"),
                        "tool_calls": tool_calls,
                    }
                )
                for tc in tool_calls:
                    fn = tc.get("function") or {}
                    name = fn.get("name") or ""
                    try:
                        args = json.loads(fn.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    result = await execute_session_tool(
                        session,
                        problem=problem,
                        contest_set=contest_set,
                        name=name,
                        arguments=args,
                    )
                    tools_used.append({"tool": name, "args": args, "result": result[:500]})
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.get("id"),
                            "content": result,
                        }
                    )
                continue
            content = (msg.get("content") or "").strip()
            if content:
                return (content, tools_used)
        return None

    async def _reply_rules(
        self,
        session: AsyncSession,
        chat: Session,
        problem: Problem | None,
        text: str,
        *,
        contest_set: ContestSet | None,
        tools_used: list[dict],
    ) -> tuple[str, list[dict]]:
        from duliu.workflows import run_creation_workflow
        from duliu.workflows.intent import detect_workflow_from_text, parse_workflow_params
        from duliu.workflows.registry import get_workflow

        wid = detect_workflow_from_text(text)
        if wid:
            meta = get_workflow(wid)
            if not meta.requires_problem or problem:
                params = parse_workflow_params(text, wid)
                try:
                    result = await run_creation_workflow(
                        session, wid, params, problem=problem
                    )
                    tools_used.append({"tool": "run_creation_workflow", "workflow": wid, "result": result})
                    preview = (result.get("report_preview") or result.get("summary") or "")[:1200]
                    return (
                        f"【{meta.name_zh}】{result.get('summary', '完成')}\n\n{preview}".strip(),
                        tools_used,
                    )
                except ValueError as e:
                    return (f"工作流失败: {e}", tools_used)

        if contest_set and re.search(r"(套题评估|set\s*eval|evaluate\s*set)", text, re.I):
            try:
                report = await ContestFacade.evaluate_set(session, contest_set)
                tools_used.append({"tool": "set_evaluate", "ok": report.get("ok")})
                return (
                    f"{report['summary']}（filled={report['filled_slots']}, "
                    f"curve_ok={report['curve_ok']}）",
                    tools_used,
                )
            except ValueError as e:
                return (f"套题评估失败: {e}", tools_used)

        if contest_set and re.search(r"(通过套题|approve\s*set|set\s*approve)", text, re.I):
            try:
                await ContestFacade.approve_set_eval(session, contest_set, approved_by="session")
                tools_used.append({"tool": "approve_set_eval"})
                return (f"套题 {contest_set.name} 评估已通过，status=SET_EVAL_APPROVED", tools_used)
            except ValueError as e:
                return (f"套题 Gate 失败: {e}", tools_used)

        if contest_set and re.search(r"(套题状态|contest\s*status)", text, re.I):
            detail = await ContestFacade.get_detail(session, contest_set.id)
            if not detail:
                return ("套题不存在。", tools_used)
            tools_used.append({"tool": "contest_status"})
            lines = [
                f"套题: {detail['name']} ({detail['contest_style']}) status={detail['status']}",
                f"槽位: {detail['slot_count']}",
            ]
            for s in detail["slots"]:
                t = s.get("problem", {}).get("title") if s.get("problem") else "(空)"
                st = s.get("problem", {}).get("current_stage") if s.get("problem") else "-"
                lines.append(f"  {s['slot_label']}: {t} [{st}]")
            ev = detail.get("set_eval_json") or {}
            if ev.get("summary"):
                lines.append(f"最近评估: {ev['summary']}")
            return ("\n".join(lines), tools_used)

        m_dispatch = re.search(
            r"(?:dispatch|调度)\s+(SPEC|STATEMENT|SOLUTION|GENERATOR|STRESS|ADVERSARIAL(?:_REVIEW)?|PACKAGE|EDITORIAL)",
            text,
            re.I,
        )
        if problem and m_dispatch:
            stage = m_dispatch.group(1).upper()
            if stage == "ADVERSARIAL":
                stage = "ADVERSARIAL_REVIEW"
            try:
                out = await PipelineFacade.dispatch(
                    session, problem, stage, reason=f"session:{text[:80]}"
                )
                tools_used.append({"tool": "dispatch_stage", "stage": stage, "result": out})
                summary = out.get("report", {}).get("summary", out.get("hint", ""))
                return (f"已调度阶段 {stage}。run_id={out.get('run_id')}。{summary}", tools_used)
            except ValueError as e:
                return (f"调度失败: {e}", tools_used)

        m_approve = re.search(
            r"(?:approve|通过)\s+(SPEC|STATEMENT|SOLUTION|GENERATOR|STRESS|ADVERSARIAL(?:_REVIEW)?|PACKAGE|EDITORIAL)",
            text,
            re.I,
        )
        if problem and m_approve:
            stage = m_approve.group(1).upper()
            if stage == "ADVERSARIAL":
                stage = "ADVERSARIAL_REVIEW"
            try:
                await PipelineFacade.approve_stage(session, problem, stage, approved_by="session")
                tools_used.append({"tool": "approve_stage", "stage": stage})
                return (f"已通过阶段 {stage}，当前阶段 → {problem.current_stage}", tools_used)
            except ValueError as e:
                return (f"Gate 失败: {e}", tools_used)

        if problem and re.search(r"(对拍|stress)", text, re.I):
            job = await JobFacade.enqueue_stress(session, problem, mode="quick")
            tools_used.append({"tool": "enqueue_stress", "job_id": str(job.id)})
            return (f"已排队快速对拍，job_id={job.id}", tools_used)

        if problem and re.search(r"(状态|status)", text, re.I):
            rows = (
                await session.execute(select(ProblemStage).where(ProblemStage.problem_id == problem.id))
            ).scalars().all()
            lines = [f"当前阶段: {problem.current_stage} ({problem.contest_style}/{problem.problem_type})"]
            for s in rows:
                lines.append(f"  - {s.stage_id}: {s.status}")
            return ("\n".join(lines), tools_used)

        if problem and re.search(r"(最近|事件|日志|监控)", text, re.I):
            events = await MonitorFacade.query_recent_events(session, problem_id=problem.id, limit=8)
            tools_used.append({"tool": "query_events", "count": len(events)})
            if not events:
                return ("暂无监控事件。", tools_used)
            lines = [f"[{e.source}] {e.type}: {e.message}" for e in events]
            return ("最近事件:\n" + "\n".join(lines), tools_used)

        from duliu.agents.llm_config import get_active_llm

        if get_active_llm().is_configured() and problem:
            msg = await chat_messages(
                [
                    {
                        "role": "system",
                        "content": f"Duliu Session Agent，题目 {problem.title}，阶段 {problem.current_stage}。中文简答。",
                    },
                    {"role": "user", "content": text},
                ]
            )
            if msg and msg.get("content"):
                return (msg["content"], tools_used)

        hints = [
            "我是 Duliu Session Agent。可尝试：",
            "- 五步出题：找题 / 写题面 / 解法分析 / 生成数据 / 写题解",
            "- workflow:find_problem 或 工作流:write_statement",
            "- dispatch STRESS / PACKAGE / EDITORIAL",
            "- approve STRESS — 通过某阶段 Gate",
            "- 对拍 / 状态 / 最近事件",
        ]
        if settings.session_tools_enabled and get_active_llm().is_configured():
            hints.append(f"（已启用 LLM Tool Calling · {get_active_llm().provider}）")
        if contest_set:
            hints.extend(["- 套题评估 / 通过套题 / 套题状态（套题上下文）"])
        return ("\n".join(hints), tools_used)
