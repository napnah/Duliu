"""M15/M19 STRESS stage agent: LLM preflight + seed artifacts + enqueue stress job."""

from __future__ import annotations

import json
import re

from sqlalchemy.ext.asyncio import AsyncSession

from duliu.agents.llm_client import chat_completion
from duliu.config import settings
from duliu.db.models import Problem
from duliu.facade.import_flow import seed_brute_if_missing
from duliu.facade.jobs import JobFacade


def _rule_stress_preflight(problem: Problem, *, has_gen: bool) -> dict:
    mode = "import_check" if problem.originality == "NON_ORIGINAL" else "quick"
    return {
        "recommended_mode": mode,
        "risks": [] if has_gen else ["缺少 gen，对拍仅 quick 子集"],
        "hints": ["确认 std/brute 语言与时限一致", "对拍失败时检查 checker/SPJ"],
        "confidence": "rule",
    }


async def _llm_stress_preflight(
    problem: Problem,
    *,
    std_preview: str,
    brute_preview: str,
    has_gen: bool,
) -> dict | None:
    sys_prompt = (
        "你是 Duliu STRESS 对拍助手。输出 JSON："
        '{"recommended_mode":"quick|import_check","risks":["..."],"hints":["..."],"test_focus":"..."}'
    )
    user_prompt = json.dumps(
        {
            "title": problem.title,
            "style": problem.contest_style,
            "type": problem.problem_type,
            "originality": problem.originality,
            "has_gen": has_gen,
            "limits": (problem.spec_json or {}).get("limits"),
            "std_head": std_preview[:400],
            "brute_head": brute_preview[:400],
        },
        ensure_ascii=False,
    )
    text = await chat_completion(system=sys_prompt, user=user_prompt, max_tokens=500)
    if not text:
        return None
    try:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            data = json.loads(m.group(0))
            data["confidence"] = "llm"
            return data
    except json.JSONDecodeError:
        pass
    return {"llm_notes": text[:1500], "confidence": "llm_text"}


async def run_stress_agent(
    session: AsyncSession,
    problem: Problem,
    *,
    mode: str = "quick",
) -> dict:
    """Ensure std/brute exist, LLM preflight, and queue stress job."""
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

    gen = await JobFacade.latest_artifact(session, problem.id, "gen")
    preflight = _rule_stress_preflight(problem, has_gen=bool(gen))
    llm_pf = await _llm_stress_preflight(
        problem,
        std_preview=(std.content_text or "")[:400],
        brute_preview=(brute.content_text or "")[:400],
        has_gen=bool(gen),
    )
    if llm_pf:
        preflight = {**preflight, **llm_pf}
    rec_mode = (preflight.get("recommended_mode") or mode).lower()
    if rec_mode in ("quick", "import_check"):
        mode = rec_mode

    job = await JobFacade.enqueue_stress(session, problem, mode=mode)
    spec = dict(problem.spec_json or {})
    spec["last_stress"] = {
        "job_id": str(job.id),
        "mode": mode,
        "seeded_brute": seeded_brute,
        "preflight": preflight,
    }
    problem.spec_json = spec

    pf_mode = preflight.get("confidence", "rule")
    summary = f"已排队 {mode} 对拍 job={job.id}（预检 {pf_mode}）"
    risks = preflight.get("risks") or []
    if risks:
        summary += f"；风险: {risks[0]}"

    return {
        "ok": True,
        "mode": "runner",
        "agent": "stress_llm" if llm_pf else "stress",
        "summary": summary,
        "job_id": str(job.id),
        "seeded_brute": seeded_brute,
        "preflight": preflight,
    }
