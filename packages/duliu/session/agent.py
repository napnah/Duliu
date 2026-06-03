"""M2 Session Agent: rule-based tools + optional OpenAI via httpx."""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from duliu.config import settings
from duliu.db.models import ContestSet, Problem, ProblemStage, Session
from duliu.facade.contest import ContestFacade
from duliu.facade.jobs import JobFacade
from duliu.facade.monitor import MonitorFacade
from duliu.facade.pipeline import PipelineFacade


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

        if settings.openai_api_key and problem:
            llm = await self._try_openai(problem, text)
            if llm:
                return (llm, tools_used)

        hints = [
            "我是 Duliu Session Agent。可尝试：",
            "- dispatch ADVERSARIAL_REVIEW / PACKAGE / EDITORIAL",
            "- approve STRESS — 通过某阶段 Gate",
            "- 对拍 / 状态 / 最近事件",
        ]
        if contest_set:
            hints.extend(["- 套题评估 / 通过套题 / 套题状态（套题上下文）"])
        return ("\n".join(hints), tools_used)

    async def _try_openai(self, problem: Problem, text: str) -> str | None:
        import httpx

        sys = (
            f"You are Duliu Session Agent for problem '{problem.title}' at stage {problem.current_stage}. "
            "Answer briefly in Chinese. Suggest dispatch/approve/stress commands when helpful."
        )
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                    json={
                        "model": settings.openai_model,
                        "messages": [
                            {"role": "system", "content": sys},
                            {"role": "user", "content": text},
                        ],
                        "max_tokens": 500,
                    },
                )
            if r.status_code != 200:
                return None
            return r.json()["choices"][0]["message"]["content"]
        except Exception:
            return None
