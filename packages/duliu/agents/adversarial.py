"""S6 Adversarial review agent (M2): rule-based report; LLM optional later."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from duliu.db.models import Artifact, Problem
from duliu.workflow.loader import load_workflow


async def run_adversarial_review(session: AsyncSession, problem: Problem) -> dict:
    arts = (
        await session.execute(select(Artifact).where(Artifact.problem_id == problem.id))
    ).scalars().all()
    kinds = {a.kind for a in arts}
    wf = load_workflow(problem.contest_style)
    findings: list[dict] = []

    if "statement" not in kinds:
        findings.append({"code": "missing_statement", "severity": "high", "msg": "缺少题面 statement"})
    if "std" not in kinds:
        findings.append({"code": "missing_std", "severity": "high", "msg": "缺少标程 std"})
    samples = problem.spec_json.get("samples") or []
    if not samples:
        findings.append({"code": "no_samples", "severity": "medium", "msg": "spec 无样例"})

    if problem.contest_style == "OI":
        if not problem.spec_json.get("subtasks"):
            findings.append(
                {
                    "code": "oi_no_subtasks",
                    "severity": "low",
                    "msg": "OI 题建议在 spec_json.subtasks 中声明子任务",
                }
            )
        if wf.get("scoring", {}).get("partial_scoring") and problem.problem_type == "TRADITIONAL":
            if "brute" not in kinds:
                findings.append(
                    {"code": "oi_brute_recommended", "severity": "medium", "msg": "OI 对拍建议提供 brute"}
                )
    if problem.problem_type == "INTERACTIVE" and "interactor" not in kinds:
        findings.append(
            {"code": "missing_interactor", "severity": "high", "msg": "交互题需 interactor 工件"}
        )
    if problem.problem_type == "COMMUNICATION":
        if "interactor" not in kinds:
            findings.append(
                {"code": "missing_interactor", "severity": "high", "msg": "通信题需 interactor 工件"}
            )
        if "protocol" not in kinds:
            findings.append(
                {"code": "missing_protocol", "severity": "high", "msg": "通信题需 protocol 工件"}
            )

    if problem.problem_type == "SUBMIT_ANSWER" and "checker" not in kinds:
        findings.append({"code": "spj_required", "severity": "high", "msg": "提交答案题必须提供 checker (SPJ)"})

    high = [f for f in findings if f["severity"] == "high"]
    ok = len(high) == 0
    return {
        "ok": ok,
        "contest_style": problem.contest_style,
        "problem_type": problem.problem_type,
        "findings": findings,
        "summary": "通过对抗评估" if ok else f"发现 {len(findings)} 项问题（{len(high)} 项高优先级）",
    }


def report_to_artifact_content(report: dict) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2)
