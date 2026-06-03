"""Suggested next-step actions after Session Agent replies (Claude-style chips)."""

from __future__ import annotations

import json
import re

from sqlalchemy.ext.asyncio import AsyncSession

from duliu.agents.llm_client import chat_completion
from duliu.agents.llm_config import get_active_llm
from duliu.config import settings
from duliu.db.models import ContestSet, Problem
from duliu.workflows.registry import CREATION_WORKFLOWS


def _action(action_id: str, label: str, message: str, *, kind: str = "chat") -> dict:
    return {"id": action_id, "label": label, "message": message, "kind": kind}


def _creation_workflow_chips() -> list[dict]:
    chips: list[dict] = []
    for m in CREATION_WORKFLOWS.values():
        msg = m.chat_triggers[0] if m.chat_triggers else m.id
        chips.append(_action(f"wf_{m.id}", m.name_zh, msg, kind="chat"))
    return chips


def _rule_suggestions(problem: Problem | None, contest_set: ContestSet | None) -> list[dict]:
    wf = _creation_workflow_chips()
    if contest_set and not problem:
        return [
            _action("set_eval", "套题评估", "套题评估"),
            _action("set_status", "套题状态", "套题状态"),
            _action("set_approve", "通过套题评估", "通过套题评估"),
        ]

    if not problem:
        return wf + [_action("help", "查看帮助", "状态")]

    stage = problem.current_stage
    spec = problem.spec_json or {}
    imp = spec.get("import") or {}
    opts: list[dict] = []

    if problem.originality == "NON_ORIGINAL" and stage in ("IMPORT", "SPEC"):
        if not imp.get("import_check_ok"):
            opts.append(
                _action("import_check", "运行 import_check", "import_check", kind="action")
            )
        opts.append(_action("fetch_std", "拉取 CF 标程", "fetch_std", kind="action"))
        if imp.get("problem_url"):
            opts.append(
                _action("open_source", "打开原题", imp["problem_url"], kind="link")
            )
        if not imp.get("submission_confirmed"):
            opts.append(
                _action("import_confirm", "确认已提交原题", "import_confirm", kind="action")
            )

    if stage == "STATEMENT":
        opts.append({"id": "pane_stmt", "label": "查看题面", "message": "statement", "kind": "pane"})
        opts.append(_action("dispatch_stmt", "生成/润色题面", "dispatch STATEMENT"))
    elif stage == "SOLUTION":
        opts.append({"id": "pane_code", "label": "编辑标程", "message": "code", "kind": "pane"})
        opts.append(_action("load_sample", "加载样例", "load_sample", kind="action"))
        opts.append(_action("dispatch_sol", "调度标程", "dispatch SOLUTION"))
    elif stage == "STRESS":
        opts.append(_action("stress_quick", "快速对拍", "stress_quick", kind="action"))
        opts.append(_action("dispatch_stress", "调度对拍", "dispatch STRESS"))
    elif stage == "PACKAGE":
        opts.append(_action("polygon_zip", "Polygon zip", "polygon_zip", kind="action"))
        opts.append(_action("dispatch_pkg", "调度题包", "dispatch PACKAGE"))
    elif stage == "EDITORIAL":
        opts.append({"id": "pane_ed", "label": "查看题解", "message": "editorial", "kind": "pane"})
        opts.append(_action("dispatch_ed", "调度题解", "dispatch EDITORIAL"))
    else:
        opts.append(_action("dispatch_cur", f"调度 {stage}", f"dispatch {stage}"))

    opts.append(_action("approve_cur", f"通过 {stage}", f"approve {stage}"))
    opts.append(_action("status", "流水线状态", "状态"))
    opts.append(_action("events", "最近事件", "最近事件"))

    seen: set[str] = set()
    out: list[dict] = []
    for o in wf + opts:
        if o["id"] in seen:
            continue
        seen.add(o["id"])
        out.append(o)
        if len(out) >= 8:
            break
    return out


async def _llm_suggestions(
    problem: Problem | None,
    contest_set: ContestSet | None,
    reply_text: str,
) -> list[dict] | None:
    if not get_active_llm().is_configured():
        return None
    ctx = ""
    if problem:
        ctx = f"题目={problem.title} 阶段={problem.current_stage} 风格={problem.contest_style}"
    if contest_set:
        ctx += f" 套题={contest_set.name}"
    sys_prompt = (
        "你是 Duliu 工作流助手。根据对话回复，给出 3–5 个用户可点的「下一步」建议。"
        "只输出 JSON 数组，每项含 id, label, message, kind。"
        "kind 为 chat（发 message 给 Agent）、action（前端动作 id）、pane（切题面/题解/代码）。"
        "message 为 chat 时发送的文本；kind=action 时 message 为动作 id；kind=pane 时 message 为 statement|editorial|code。"
        "label 为按钮上显示的短中文。"
    )
    user_prompt = f"上下文: {ctx}\n助手刚回复:\n{reply_text[:1500]}\n\n输出 JSON 数组:"
    text = await chat_completion(system=sys_prompt, user=user_prompt, max_tokens=400)
    if not text:
        return None
    m = re.search(r"\[[\s\S]*\]", text)
    if not m:
        return None
    try:
        raw = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    out: list[dict] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        out.append(
            {
                "id": str(item.get("id") or f"llm_{i}"),
                "label": label[:40],
                "message": str(item.get("message") or label),
                "kind": str(item.get("kind") or "chat"),
            }
        )
    return out[:6] if out else None


async def build_suggested_actions(
    session: AsyncSession,
    problem: Problem | None,
    contest_set: ContestSet | None,
    reply_text: str,
    tools_used: list[dict],
) -> list[dict]:
    del session, tools_used
    rules = _rule_suggestions(problem, contest_set)
    if not settings.session_tools_enabled:
        return rules
    llm = await _llm_suggestions(problem, contest_set, reply_text)
    if llm:
        return llm
    return rules
