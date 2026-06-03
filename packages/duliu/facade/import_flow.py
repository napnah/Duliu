"""M6 NON_ORIGINAL import helpers: brute seed, import_check, submission confirm."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from duliu.db.models import Artifact, Problem, stage_order_for
from duliu.facade.events import emit_event
from duliu.facade.jobs import JobFacade

DEFAULT_BRUTE_PY = """# M6 seed brute (edit for real constraints)
import sys
data = sys.stdin.read().strip().split()
if len(data) >= 2:
    print(int(data[0]) + int(data[1]))
else:
    print(0)
"""


async def ensure_non_original_stages(session: AsyncSession, problem: Problem) -> None:
    """Add IMPORT stage row if missing (migration for older imports)."""
    from sqlalchemy import select
    from duliu.db.models import ProblemStage, StageStatus

    order = stage_order_for(problem.contest_style, problem.originality)
    problem.spec_json = {**problem.spec_json, "_stage_order": order}
    existing = (
        await session.execute(
            select(ProblemStage).where(ProblemStage.problem_id == problem.id)
        )
    ).scalars().all()
    by_id = {s.stage_id: s for s in existing}
    for sid in order:
        if sid not in by_id:
            session.add(
                ProblemStage(
                    problem_id=problem.id,
                    stage_id=sid,
                    status=StageStatus.PENDING.value,
                )
            )
    if problem.originality == "NON_ORIGINAL" and problem.current_stage == "SPEC":
        problem.current_stage = "IMPORT"
        if "IMPORT" in by_id:
            by_id["IMPORT"].status = StageStatus.AWAITING_HUMAN.value


async def seed_brute_if_missing(session: AsyncSession, problem: Problem) -> bool:
    art = await JobFacade.latest_artifact(session, problem.id, "brute")
    if art:
        return False
    content = DEFAULT_BRUTE_PY
    session.add(
        Artifact(
            problem_id=problem.id,
            kind="brute",
            version=1,
            content_text=content,
            sha256=hashlib.sha256(content.encode()).hexdigest(),
            author="import_seed",
            language="python",
        )
    )
    await emit_event(
        session,
        problem_id=problem.id,
        type="import.brute_seeded",
        message="Seeded default python brute for import_check",
        source="import",
    )
    return True


async def enqueue_import_check(session: AsyncSession, problem: Problem):
    job = await JobFacade.enqueue_stress(session, problem, mode="import_check")
    imp = dict(problem.spec_json.get("import") or {})
    imp["import_check_job_id"] = str(job.id)
    problem.spec_json = {**problem.spec_json, "import": imp}
    await session.flush()
    return job


async def confirm_submission(
    session: AsyncSession,
    problem: Problem,
    *,
    submission_url: str | None = None,
    handle: str | None = None,
) -> Problem:
    if problem.originality != "NON_ORIGINAL":
        raise ValueError("Only NON_ORIGINAL problems require submission confirmation")
    imp = dict(problem.spec_json.get("import") or {})
    req = dict(imp.get("submission_requirement") or {})
    req["required"] = True
    req["user_confirmed"] = True
    req["user_confirmed_at"] = datetime.now(timezone.utc).isoformat()
    if submission_url:
        req["submission_url"] = submission_url
    if handle:
        req["handle"] = handle
    imp["submission_requirement"] = req
    problem.spec_json = {**problem.spec_json, "import": imp}
    await emit_event(
        session,
        problem_id=problem.id,
        type="import.submission_confirmed",
        message="User confirmed original platform submission",
        source="import",
        payload=req,
    )
    await session.flush()
    return problem


async def record_import_check_result(session: AsyncSession, problem: Problem, report: dict) -> None:
    imp = dict(problem.spec_json.get("import") or {})
    imp["import_check"] = {
        "ok": bool(report.get("ok")),
        "rounds": report.get("rounds"),
        "reason": report.get("reason"),
        "at": datetime.now(timezone.utc).isoformat(),
    }
    problem.spec_json = {**problem.spec_json, "import": imp}
    await session.flush()


async def fetch_ac_std_and_save(
    session: AsyncSession,
    problem: Problem,
    *,
    cookie: str | None,
    handle: str | None = None,
) -> dict:
    """Pull latest CF AC source into std artifact (M10)."""
    if problem.originality != "NON_ORIGINAL":
        raise ValueError("AC std fetch only for NON_ORIGINAL")
    imp = dict(problem.spec_json.get("import") or {})
    url = imp.get("problem_url") or (problem.spec_json or {}).get("source_url")
    if not url:
        raise ValueError("No problem_url in import spec")
    from duliu.crawler.ac_fetch import fetch_ac_std_for_problem

    fetched = await fetch_ac_std_for_problem(
        problem_url=url,
        cookie=cookie,
        handle=handle or imp.get("handle"),
    )
    latest = await JobFacade.latest_artifact(session, problem.id, "std")
    ver = (latest.version + 1) if latest else 1
    content = fetched["source"]
    session.add(
        Artifact(
            problem_id=problem.id,
            kind="std",
            version=ver,
            content_text=content,
            sha256=hashlib.sha256(content.encode()).hexdigest(),
            author="ac_fetch",
            language=fetched.get("language") or "cpp",
        )
    )
    imp["ac_fetch"] = {
        "submission_id": fetched.get("submission_id"),
        "handle": fetched.get("handle"),
        "language": fetched.get("language"),
        "at": datetime.now(timezone.utc).isoformat(),
    }
    problem.spec_json = {**problem.spec_json, "import": imp}
    await emit_event(
        session,
        problem_id=problem.id,
        type="import.ac_std_fetched",
        message=f"Fetched AC std from submission {fetched.get('submission_id')}",
        source="import",
        payload=imp["ac_fetch"],
    )
    await session.flush()
    return {"version": ver, **fetched}
