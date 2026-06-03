"""M14 LLM/rule stage agents for SPEC, STATEMENT, SOLUTION, GENERATOR."""

from __future__ import annotations

import hashlib
import json
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from duliu.agents.llm_client import chat_completion
from duliu.config import settings
from duliu.db.models import Artifact, Problem

STAGE_LLM_STAGES = frozenset({"SPEC", "STATEMENT", "SOLUTION", "GENERATOR"})


async def _next_version(session: AsyncSession, problem_id, kind: str) -> int:
    row = (
        await session.execute(
            select(Artifact)
            .where(Artifact.problem_id == problem_id, Artifact.kind == kind)
            .order_by(Artifact.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return (row.version + 1) if row else 1


async def _save_artifact(
    session: AsyncSession,
    problem: Problem,
    kind: str,
    content: str,
    *,
    author: str,
    language: str | None = None,
) -> int:
    ver = await _next_version(session, problem.id, kind)
    session.add(
        Artifact(
            problem_id=problem.id,
            kind=kind,
            version=ver,
            content_text=content,
            sha256=hashlib.sha256(content.encode()).hexdigest(),
            author=author,
            language=language,
        )
    )
    return ver


def _rule_spec(problem: Problem) -> dict:
    spec = dict(problem.spec_json or {})
    limits = dict(spec.get("limits") or {"time_ms": 1000, "memory_mb": 256})
    samples = list(spec.get("samples") or [])
    if not samples:
        samples = [{"input": "1 2\n", "output": "3\n", "note": "M14 rule placeholder"}]
    return {
        "limits": limits,
        "samples": samples,
        "notes": f"Rule-based SPEC draft for {problem.title}",
    }


def _rule_statement(problem: Problem) -> str:
    spec = problem.spec_json or {}
    limits = spec.get("limits", {})
    samples = spec.get("samples") or []
    sample_txt = ""
    if samples:
        s0 = samples[0]
        sample_txt = f"\n\n## 样例\n\n输入:\n```\n{s0.get('input', '')}```\n\n输出:\n```\n{s0.get('output', '')}```\n"
    return f"""# {problem.title}

## 题目描述

（M14 规则草稿，请编辑完善）

- 时限: {limits.get('time_ms', 1000)} ms
- 内存: {limits.get('memory_mb', 256)} MB
{sample_txt}
"""


def _rule_std(problem: Problem) -> str:
    return f"""# M14 draft std for {problem.title}
# TODO: implement
import sys
data = sys.stdin.read().strip().split()
if len(data) >= 2:
    print(int(data[0]) + int(data[1]))
else:
    print(0)
"""


def _rule_gen(problem: Problem) -> str:
    return f"""# M14 generator stub for {problem.title}
import random
print(2, 3)
"""


async def run_stage_agent(session: AsyncSession, problem: Problem, stage_id: str) -> dict:
    """Run stage agent; returns report dict with mode llm|rule."""
    if stage_id not in STAGE_LLM_STAGES:
        return {"ok": False, "mode": "none", "summary": f"No agent for {stage_id}"}

    if not settings.stage_llm_enabled:
        return {"ok": False, "mode": "disabled", "summary": "Stage LLM disabled"}

    sys_prompt = (
        f"You are Duliu stage agent for {stage_id} on problem '{problem.title}'. "
        f"Style={problem.contest_style} type={problem.problem_type}. "
        "Respond in Chinese where appropriate."
    )
    user_prompt = json.dumps(
        {"stage": stage_id, "spec_json": problem.spec_json, "title": problem.title},
        ensure_ascii=False,
        indent=2,
    )
    llm_text = await chat_completion(system=sys_prompt, user=user_prompt)
    mode = "llm" if llm_text else "rule"

    if stage_id == "SPEC":
        if llm_text:
            patch = {"agent_notes": llm_text[:8000]}
            try:
                m = re.search(r"\{[\s\S]*\}", llm_text)
                if m:
                    patch = json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        else:
            patch = _rule_spec(problem)
        problem.spec_json = {**(problem.spec_json or {}), **patch, "_last_agent": stage_id}
        return {"ok": True, "mode": mode, "summary": f"SPEC updated ({mode})", "artifact_kind": None}

    if stage_id == "STATEMENT":
        content = llm_text if llm_text else _rule_statement(problem)
        ver = await _save_artifact(
            session, problem, "statement", content, author=f"stage_{mode}", language="markdown"
        )
        return {"ok": True, "mode": mode, "summary": f"statement v{ver}", "artifact_kind": "statement", "version": ver}

    if stage_id == "SOLUTION":
        content = llm_text if llm_text else _rule_std(problem)
        if "```" in content:
            m = re.search(r"```(?:python|cpp)?\n([\s\S]*?)```", content)
            if m:
                content = m.group(1).strip()
        lang = "python" if "def " in content or "import " in content else "cpp"
        ver = await _save_artifact(
            session, problem, "std", content, author=f"stage_{mode}", language=lang
        )
        return {"ok": True, "mode": mode, "summary": f"std v{ver}", "artifact_kind": "std", "version": ver}

    if stage_id == "GENERATOR":
        content = llm_text if llm_text else _rule_gen(problem)
        if "```" in content:
            m = re.search(r"```(?:python)?\n([\s\S]*?)```", content)
            if m:
                content = m.group(1).strip()
        ver = await _save_artifact(
            session, problem, "gen", content, author=f"stage_{mode}", language="python"
        )
        return {"ok": True, "mode": mode, "summary": f"gen v{ver}", "artifact_kind": "gen", "version": ver}

    return {"ok": False, "mode": mode, "summary": "unhandled"}
