"""Execute creation workflows — invoked by Session Agent, API, CLI."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from duliu.agents.editorial import run_editorial_draft
from duliu.agents.llm_client import chat_completion
from duliu.agents.llm_config import get_active_llm
from duliu.agents.stage_agents import run_stage_agent
from duliu.db.models import Problem
from duliu.facade.events import emit_event
from duliu.facade.jobs import JobFacade
from duliu.workflows.artifacts import save_artifact
from duliu.workflows.registry import get_workflow, list_workflows


async def _llm(system: str, user: str, *, max_tokens: int = 4000) -> str:
    if not get_active_llm().is_configured():
        return ""
    return (await chat_completion(system=system, user=user, max_tokens=max_tokens)) or ""


def _patch_spec(problem: Problem, key: str, value: Any) -> None:
    spec = dict(problem.spec_json or {})
    wf = dict(spec.get("creation_workflows") or {})
    wf[key] = value
    spec["creation_workflows"] = wf
    problem.spec_json = spec


async def run_find_problem(
    session: AsyncSession,
    problem: Problem | None,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Step 1: recommend/search strategy and candidate problems."""
    difficulty = params.get("difficulty") or params.get("rating") or "未指定"
    topics = params.get("topics") or params.get("knowledge_points") or []
    if isinstance(topics, str):
        topics = [t.strip() for t in re.split(r"[,，、\s]+", topics) if t.strip()]
    style = (params.get("contest_style") or params.get("style") or "OI").upper()
    partial = bool(params.get("partial_scoring") or params.get("partial_friendly") or style == "OI")
    count = int(params.get("count") or 5)
    sources = params.get("sources") or ["codeforces", "luogu", "atcoder"]

    sys_prompt = """你是竞赛命题顾问，负责「找题/选题」。
根据用户约束输出 Markdown 报告，包含：
1. 检索策略（各平台关键词、标签、难度筛选方式）
2. 候选题目列表（至少按用户要求数量），每项含：平台、题目名/链接占位、估计难度、知识点标签、选题理由
3. 若为 OI：必须评估「易于划分部分分」——给出建议的子任务划分（特殊性质 / 数据范围 / 预期分值比例）
4. 风险与排除项（原题过旧、题面质量差、难以造数据等）
不要编造不存在的具体题号；可写「建议在 CF 搜索 tag:dp, rating 2000-2300」等可执行步骤。
若无法联网搜题，明确说明需用户自行打开链接核验。"""

    user_prompt = json.dumps(
        {
            "difficulty": difficulty,
            "topics": topics,
            "contest_style": style,
            "partial_scoring_required": partial,
            "candidate_count": count,
            "preferred_sources": sources,
            "extra_requirements": params.get("notes") or params.get("extra") or "",
        },
        ensure_ascii=False,
        indent=2,
    )

    body = await _llm(sys_prompt, user_prompt, max_tokens=3500)
    if not body:
        body = (
            f"# 找题报告（规则草稿）\n\n"
            f"- 目标难度: {difficulty}\n- 知识点: {', '.join(topics) or '未指定'}\n"
            f"- 赛制: {style}\n- OI 部分分: {'是' if partial else '否'}\n\n"
            "请配置 LLM 后重新运行本工作流，或在洛谷/CF 按上述条件手动检索。\n"
        )

    report = f"# 找题 / 选题报告\n\n{body}\n"
    ver = None
    if problem:
        ver = await save_artifact(
            session, problem, "find_report", report, author="workflow_find_problem", language="markdown"
        )
        _patch_spec(
            problem,
            "find_problem",
            {"difficulty": difficulty, "topics": topics, "style": style, "version": ver},
        )
        await session.flush()

    return {
        "ok": True,
        "workflow": "find_problem",
        "summary": f"已生成找题报告（{count} 题规模建议）",
        "artifact_kind": "find_report" if problem else None,
        "version": ver,
        "report_preview": report[:2000],
        "llm_used": bool(get_active_llm().is_configured()),
    }


async def run_write_statement(
    session: AsyncSession,
    problem: Problem,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Step 2: CF / NOIP style statement."""
    style = (params.get("style") or params.get("format") or "codeforces").lower()
    if style in ("noi", "noip", "noi-style"):
        style_key = "noip"
        style_guide = (
            "严格 NOIP / 中文 OI 题面：题目描述、输入格式、输出格式、样例（输入输出说明）、"
            "数据范围（含子任务表格若 OI）、提示（可选）。中文为主。"
        )
    else:
        style_key = "codeforces"
        style_guide = (
            "严格 Codeforces 题面：Markdown，英文或中英均可；含 legend、input/output format、"
            "examples with input/output blocks、constraints、notes（可选）。样例用 ``` 包裹。"
        )

    spec = problem.spec_json or {}
    sys_prompt = f"You write competition problem statements. {style_guide} Output Markdown only."
    user_prompt = json.dumps(
        {
            "title": problem.title,
            "contest_style": problem.contest_style,
            "problem_type": problem.problem_type,
            "spec_json": spec,
            "creation_context": (spec.get("creation_workflows") or {}),
        },
        ensure_ascii=False,
        indent=2,
    )
    content = await _llm(sys_prompt, user_prompt, max_tokens=4000)
    mode = "llm"
    if not content:
        out = await run_stage_agent(session, problem, "STATEMENT")
        return {
            "ok": out.get("ok", False),
            "workflow": "write_statement",
            "summary": out.get("summary", "题面已生成（规则）"),
            "mode": out.get("mode", "rule"),
            "artifact_kind": "statement",
        }

    ver = await save_artifact(
        session, problem, "statement", content, author=f"workflow_statement_{style_key}", language="markdown"
    )
    _patch_spec(problem, "write_statement", {"style": style_key, "version": ver})
    return {
        "ok": True,
        "workflow": "write_statement",
        "summary": f"题面已生成 ({style_key}) v{ver}",
        "artifact_kind": "statement",
        "version": ver,
        "mode": mode,
    }


async def run_solution_analysis(
    session: AsyncSession,
    problem: Problem,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Step 3: OI partial scoring plan or ICPC solution validation plan."""
    is_oi = (params.get("contest_style") or problem.contest_style or "OI").upper() == "OI"
    stmt = await JobFacade.latest_artifact(session, problem.id, "statement")

    if is_oi:
        sys_prompt = """你是 OI 命题专家。根据题面做细致分析，输出 Markdown：
## 1. 题目性质与难点
## 2. 正解思路（满分）
## 3. 中间解法链条（思考过程中出现的非满分做法）
对每个中间解法说明：适用数据范围/特殊性质、实现要点、预期得分比例（估算）
## 4. 建议子任务 / 部分分划分表（subtask | 约束 | 分值 | 对应解法）
## 5. 造数据建议（各档数据如何生成、如何防叉）
## 6. 验证清单（如何用标程/暴力在各档数据上验分）
要求：越接近正解分数越高；划分要「易于部分分」。"""

    else:
        sys_prompt = """你是 ICPC/传统命题专家。输出 Markdown：
## 1. 正解算法与复杂度
## 2. 关键实现细节
## 3. 常见错误解法（至少 3 类）及为何应 WA/TLE
## 4. 建议测试构造（能杀死错误解的数据形态）
## 5. 数据范围建议（time/memory）
只需给出正解为主，但必须覆盖错误解甄别。"""

    user_prompt = json.dumps(
        {
            "title": problem.title,
            "statement_excerpt": (stmt.content_text if stmt else "")[:6000],
            "spec_json": problem.spec_json,
        },
        ensure_ascii=False,
        indent=2,
    )
    body = await _llm(sys_prompt, user_prompt, max_tokens=4500)
    if not body:
        body = (
            f"# 解法分析（草稿）\n\n赛制: {'OI' if is_oi else 'ICPC'}\n"
            "请配置 LLM 后重新运行 workflow solution_analysis。\n"
        )

    ver = await save_artifact(
        session, problem, "solution_plan", body, author="workflow_solution_analysis", language="markdown"
    )
    _patch_spec(problem, "solution_analysis", {"oi": is_oi, "version": ver})
    return {
        "ok": True,
        "workflow": "solution_analysis",
        "summary": f"解法/部分分方案已写入 solution_plan v{ver}",
        "artifact_kind": "solution_plan",
        "version": ver,
        "oi_mode": is_oi,
    }


async def run_generate_data(
    session: AsyncSession,
    problem: Problem,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Step 4: generator + testlib guidance; optional stress job."""
    plan = await JobFacade.latest_artifact(session, problem.id, "solution_plan")
    std = await JobFacade.latest_artifact(session, problem.id, "std")
    is_oi = (problem.contest_style or "OI").upper() == "OI"

    sys_prompt = """你是数据生成专家。输出 Python 3 生成器代码（可用 testlib 风格注释说明）。
要求：
- 使用 print 输出测试输入；可 import random, os 等
- 注释中说明 testlib.checker 或 polygon 对接方式
- 若为题面中多样例，说明如何批量生成
- OI 题：注释标明各子任务数据生成策略，便于后续用标程/中间解法验部分分
只输出一个 ```python 代码块 + 简短 Markdown 说明。"""

    user_prompt = json.dumps(
        {
            "title": problem.title,
            "solution_plan_excerpt": (plan.content_text if plan else "")[:5000],
            "has_std": bool(std),
            "std_lang": std.language if std else None,
            "oi": is_oi,
            "test_count": params.get("test_count") or 20,
        },
        ensure_ascii=False,
        indent=2,
    )
    raw = await _llm(sys_prompt, user_prompt, max_tokens=3500)
    gen_code = ""
    if raw:
        m = re.search(r"```(?:python)?\n([\s\S]*?)```", raw)
        gen_code = (m.group(1) if m else raw).strip()
    if not gen_code:
        gen_code = (
            f"# generator for {problem.title}\nimport random\n"
            "for _ in range(10):\n    print(2, 3)\n"
        )

    ver = await save_artifact(
        session, problem, "gen", gen_code, author="workflow_generate_data", language="python"
    )
    _patch_spec(problem, "generate_data", {"gen_version": ver})

    job_id = None
    if params.get("run_stress") and std:
        brute = await JobFacade.latest_artifact(session, problem.id, "brute")
        if brute:
            job = await JobFacade.enqueue_stress(session, problem, mode="quick")
            job_id = str(job.id)

    hint = "已写入 gen.py 工件；建议安装 testlib 于 Polygon/checker 流程。"
    if is_oi:
        hint += " OI：请按 solution_plan 对各档解法分别 run 验证部分分。"
    if job_id:
        hint += f" 已排队对拍 job={job_id}"

    return {
        "ok": True,
        "workflow": "generate_data",
        "summary": f"数据生成器 v{ver}" + (f"; stress job {job_id}" if job_id else ""),
        "artifact_kind": "gen",
        "version": ver,
        "stress_job_id": job_id,
        "testlib_hint": hint,
    }


async def run_write_editorial(
    session: AsyncSession,
    problem: Problem,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Step 5: editorial markdown."""
    stmt = await JobFacade.latest_artifact(session, problem.id, "statement")
    plan = await JobFacade.latest_artifact(session, problem.id, "solution_plan")
    std = await JobFacade.latest_artifact(session, problem.id, "std")

    sys_prompt = """你是题解作者。写中文 Markdown 题解，含：
- 题意简述
- 正解思路（分步骤）
- 复杂度
- 实现要点 / 坑点
- （OI）各子任务 / 部分分解法简述
- （可选）参考代码说明
风格清晰，可发布于 CF blog / 洛谷题解区。"""

    user_prompt = json.dumps(
        {
            "title": problem.title,
            "statement_excerpt": (stmt.content_text if stmt else "")[:4000],
            "solution_plan_excerpt": (plan.content_text if plan else "")[:4000],
            "std_excerpt": (std.content_text if std else "")[:2000],
        },
        ensure_ascii=False,
        indent=2,
    )
    body = await _llm(sys_prompt, user_prompt, max_tokens=4000)
    if body:
        ver = await save_artifact(
            session, problem, "editorial", body, author="workflow_editorial", language="markdown"
        )
        _patch_spec(problem, "write_editorial", {"version": ver})
        return {
            "ok": True,
            "workflow": "write_editorial",
            "summary": f"题解已生成 v{ver}",
            "artifact_kind": "editorial",
            "version": ver,
            "mode": "llm",
        }

    report = await run_editorial_draft(session, problem)
    return {
        "ok": report.get("ok", False),
        "workflow": "write_editorial",
        "summary": report.get("summary", "题解"),
        "artifact_kind": "editorial",
        "mode": "rule",
    }


async def run_creation_workflow(
    session: AsyncSession,
    workflow_id: str,
    params: dict[str, Any] | None = None,
    *,
    problem: Problem | None = None,
) -> dict[str, Any]:
    meta = get_workflow(workflow_id)
    if meta.requires_problem and not problem:
        raise ValueError(f"workflow {workflow_id} 需要绑定题目（problem_id）")

    params = dict(params or {})
    handlers = {
        "find_problem": run_find_problem,
        "write_statement": run_write_statement,
        "solution_analysis": run_solution_analysis,
        "generate_data": run_generate_data,
        "write_editorial": run_write_editorial,
    }
    result = await handlers[workflow_id](session, problem, params)

    if problem:
        await emit_event(
            session,
            problem_id=problem.id,
            type="workflow.done",
            message=f"{meta.name_zh}: {result.get('summary', 'done')}",
            source="workflow",
            payload={"workflow_id": workflow_id, "result": result},
        )
        await session.flush()
    return result


__all__ = ["run_creation_workflow", "list_workflows", "CREATION_WORKFLOWS"]
