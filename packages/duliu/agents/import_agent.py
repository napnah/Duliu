"""M16 IMPORT stage agent for NON_ORIGINAL problems."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from duliu.agents.llm_client import chat_completion
from duliu.config import settings
from duliu.db.models import Problem
from duliu.facade.import_flow import ensure_non_original_stages, seed_brute_if_missing


def _rule_checklist(problem: Problem) -> dict:
    imp = dict(problem.spec_json.get("import") or {})
    return {
        "steps": [
            "确认 problem_url 可访问",
            "配置 CF Cookie 后可拉取 AC 标程",
            "运行 import_check（std vs brute）",
            "在原平台提交后勾选 submission 确认",
        ],
        "problem_url": imp.get("problem_url"),
        "has_std": bool(imp.get("ac_fetch") or imp.get("std_provenance")),
        "import_check_ok": (imp.get("import_check") or {}).get("ok"),
        "submission_confirmed": (imp.get("submission_requirement") or {}).get("user_confirmed"),
    }


async def run_import_agent(session: AsyncSession, problem: Problem) -> dict:
    if problem.originality != "NON_ORIGINAL":
        return {"ok": False, "mode": "skip", "summary": "IMPORT agent only for NON_ORIGINAL"}

    if not settings.stage_llm_enabled:
        return {"ok": False, "mode": "disabled", "summary": "Import agent disabled"}

    await ensure_non_original_stages(session, problem)
    seeded = await seed_brute_if_missing(session, problem)

    imp = dict(problem.spec_json.get("import") or {})
    sys_prompt = (
        "你是 Duliu 非原创题 IMPORT 助手。输出简短中文清单 JSON："
        '{"steps":["..."], "risks":["..."], "next_action":"..."}'
    )
    user_prompt = json.dumps(
        {"title": problem.title, "import": imp, "current_stage": problem.current_stage},
        ensure_ascii=False,
    )
    llm_text = await chat_completion(system=sys_prompt, user=user_prompt, max_tokens=600)
    mode = "llm" if llm_text else "rule"
    checklist = _rule_checklist(problem)
    if llm_text:
        try:
            import re

            m = re.search(r"\{[\s\S]*\}", llm_text)
            if m:
                checklist = {**checklist, **json.loads(m.group(0))}
            else:
                checklist["llm_notes"] = llm_text[:2000]
        except json.JSONDecodeError:
            checklist["llm_notes"] = llm_text[:2000]

    checklist["at"] = datetime.now(timezone.utc).isoformat()
    checklist["seeded_brute"] = seeded
    imp["agent_checklist"] = checklist
    problem.spec_json = {**problem.spec_json, "import": imp}

    missing = []
    if not imp.get("problem_url"):
        missing.append("problem_url")
    if not checklist.get("import_check_ok"):
        missing.append("import_check")

    return {
        "ok": len(missing) == 0 or bool(checklist.get("submission_confirmed")),
        "mode": mode,
        "summary": f"IMPORT 清单 ({mode})" + (f"; 待办: {', '.join(missing)}" if missing else ""),
        "checklist": checklist,
        "missing": missing,
    }
