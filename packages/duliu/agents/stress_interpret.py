"""M20 STRESS result LLM interpretation."""

from __future__ import annotations

import json
import re

from duliu.agents.llm_client import chat_completion
from duliu.config import settings
from duliu.db.models import Problem


def _rule_interpret(report: dict) -> dict:
    ok = report.get("ok")
    reason = report.get("reason") or ""
    failed = report.get("failed_at")
    summary = "对拍通过" if ok else f"对拍失败: {reason}"
    if failed is not None:
        summary += f"（第 {failed} 组）"
    hints = []
    if not ok:
        hints.append("检查标程/暴力逻辑、checker、数据范围")
        if "tle" in reason.lower() or "timeout" in reason.lower():
            hints.append("考虑优化标程或提高时限")
        if "wa" in reason.lower() or "wrong" in reason.lower():
            hints.append("对比失败用例的输入输出")
    return {
        "summary": summary,
        "hints": hints,
        "severity": "ok" if ok else "error",
        "mode": "rule",
    }


async def interpret_stress_report(problem: Problem, report: dict) -> dict:
    """Summarize stress job result for humans / spec_json storage."""
    if not report:
        return {"ok": False, "mode": "empty", "summary": "无对拍报告"}

    base = _rule_interpret(report)
    if not settings.stage_llm_enabled:
        return {**base, "ok": True}

    sys_prompt = (
        "你是 Duliu 验题助手。根据对拍 JSON 用中文输出简短结论 JSON："
        '{"summary":"...","hints":["..."],"severity":"ok|warn|error","root_cause":"..."}'
    )
    user_prompt = json.dumps(
        {
            "title": problem.title,
            "style": problem.contest_style,
            "report": {
                k: report.get(k)
                for k in ("ok", "reason", "failed_at", "total", "passed", "mode")
                if k in report
            },
        },
        ensure_ascii=False,
    )
    text = await chat_completion(system=sys_prompt, user=user_prompt, max_tokens=500)
    if not text:
        return {**base, "ok": True}

    try:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            data = json.loads(m.group(0))
            data["mode"] = "llm"
            data.setdefault("summary", base["summary"])
            return {"ok": True, **data}
    except json.JSONDecodeError:
        pass
    return {**base, "ok": True, "llm_notes": text[:2000], "mode": "llm_text"}
