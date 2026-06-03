"""M4 Set Evaluator: difficulty curve and contest-set quality report."""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from duliu.db.models import Artifact, ContestSet, ContestSlot, Problem


def _rating_from_problem(problem: Problem) -> int | None:
    diff = problem.spec_json.get("difficulty") or {}
    if "rating" in diff:
        return int(diff["rating"])
    if "target_rating" in diff:
        return int(diff["target_rating"])
    return None


async def run_set_evaluation(session: AsyncSession, contest_set: ContestSet) -> dict:
    slots = (
        await session.execute(
            select(ContestSlot).where(ContestSlot.contest_set_id == contest_set.id).order_by(ContestSlot.slot_label)
        )
    ).scalars().all()

    slot_reports: list[dict] = []
    ratings: list[int] = []
    target_dist = (contest_set.target_difficulty_json or {}).get("distribution") or []
    done_count = 0
    filled = 0
    issues: list[dict] = []

    for slot in slots:
        entry: dict = {
            "slot_label": slot.slot_label,
            "status": slot.status,
            "problem_id": str(slot.problem_id) if slot.problem_id else None,
        }
        if not slot.problem_id:
            issues.append({"code": "empty_slot", "severity": "medium", "slot": slot.slot_label})
            slot_reports.append(entry)
            continue
        filled += 1
        problem = await session.get(Problem, slot.problem_id)
        if not problem:
            issues.append({"code": "missing_problem", "severity": "high", "slot": slot.slot_label})
            slot_reports.append(entry)
            continue
        entry["title"] = problem.title
        entry["current_stage"] = problem.current_stage
        entry["problem_type"] = problem.problem_type
        rating = _rating_from_problem(problem)
        if rating is not None:
            entry["rating"] = rating
            ratings.append(rating)
        else:
            issues.append({"code": "no_rating", "severity": "low", "slot": slot.slot_label})
        if problem.current_stage == "DONE":
            done_count += 1
        elif problem.current_stage != "DONE":
            issues.append(
                {
                    "code": "not_done",
                    "severity": "medium",
                    "slot": slot.slot_label,
                    "stage": problem.current_stage,
                }
            )
        slot_reports.append(entry)

    curve_ok = True
    if len(ratings) >= 2:
        for i in range(1, len(ratings)):
            if ratings[i] < ratings[i - 1] - 200:
                curve_ok = False
                issues.append(
                    {
                        "code": "difficulty_drop",
                        "severity": "medium",
                        "msg": f"槽位 {slot_reports[i]['slot_label']} 难度低于前一题",
                    }
                )
                break

    target_min = contest_set.target_difficulty_json.get("min_rating")
    target_max = contest_set.target_difficulty_json.get("max_rating")
    if target_min is not None and ratings and min(ratings) < int(target_min) - 150:
        issues.append({"code": "below_target", "severity": "low", "msg": "存在低于目标下限的题"})
    if target_max is not None and ratings and max(ratings) > int(target_max) + 150:
        issues.append({"code": "above_target", "severity": "low", "msg": "存在高于目标上限的题"})

    chart = {
        "labels": [s["slot_label"] for s in slot_reports if s.get("rating")],
        "ratings": [s["rating"] for s in slot_reports if s.get("rating")],
        "target_band": {
            "min": target_min,
            "max": target_max,
            "distribution": target_dist,
        },
    }

    all_done = filled > 0 and done_count == filled
    high_issues = [i for i in issues if i["severity"] == "high"]
    ok = filled >= max(1, contest_set.slot_count // 4) and curve_ok and not high_issues

    return {
        "ok": ok,
        "contest_style": contest_set.contest_style,
        "slot_count": contest_set.slot_count,
        "filled_slots": filled,
        "done_count": done_count,
        "all_done": all_done,
        "curve_ok": curve_ok,
        "slots": slot_reports,
        "chart": chart,
        "issues": issues,
        "summary": "套题评估通过" if ok else f"套题评估发现 {len(issues)} 项问题",
    }


async def save_set_evaluation_artifact(
    session: AsyncSession, contest_set: ContestSet, report: dict
) -> None:
    content = json.dumps(report, ensure_ascii=False, indent=2)
    prob_id = None
    for s in report.get("slots", []):
        if s.get("problem_id"):
            prob_id = s["problem_id"]
            break
    if not prob_id:
        return
    from uuid import UUID

    pid = UUID(prob_id) if isinstance(prob_id, str) else prob_id
    latest = (
        await session.execute(
            select(Artifact)
            .where(Artifact.problem_id == pid, Artifact.kind == "set_evaluation")
            .order_by(Artifact.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    ver = (latest.version + 1) if latest else 1
    session.add(
        Artifact(
            problem_id=pid,
            kind="set_evaluation",
            version=ver,
            content_text=content,
            sha256=hashlib.sha256(content.encode()).hexdigest(),
            author="set_evaluator",
            language=None,
        )
    )
