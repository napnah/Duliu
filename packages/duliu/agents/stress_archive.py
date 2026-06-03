"""M21 Archive stress counterexamples as artifacts + spec_json index."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from duliu.db.models import Problem
from duliu.facade.artifact_save import save_artifact_text
from duliu.facade.events import emit_event

MAX_COUNTEREXAMPLES = 32


def _failure_payload(report: dict, job_id: uuid.UUID | str | None) -> dict | None:
    if report.get("ok"):
        return None
    round_idx = report.get("round")
    if round_idx is None:
        round_idx = report.get("failed_at")
    payload = {
        "reason": report.get("reason"),
        "round": round_idx,
        "job_id": str(job_id) if job_id else None,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    if report.get("input") is not None:
        payload["input"] = report["input"]
    if report.get("stdout_std") is not None:
        payload["stdout_std"] = report["stdout_std"]
    if report.get("stdout_brute") is not None:
        payload["stdout_brute"] = report["stdout_brute"]
    if report.get("std"):
        payload["std_verdict"] = (report.get("std") or {}).get("verdict")
    if report.get("brute"):
        payload["brute_verdict"] = (report.get("brute") or {}).get("verdict")
    if payload.get("input") is None and round_idx is None:
        return None
    return payload


async def archive_stress_counterexample(
    session: AsyncSession,
    problem: Problem,
    report: dict,
    *,
    job_id: uuid.UUID | str | None = None,
) -> dict | None:
    """On stress failure, persist counterexample artifact and index in spec_json."""
    payload = _failure_payload(report, job_id)
    if not payload:
        return None

    content = json.dumps(payload, ensure_ascii=False, indent=2)
    ver = await save_artifact_text(
        session, problem, "counterexample", content, author="stress_archive", language="json"
    )

    spec = dict(problem.spec_json or {})
    items = list(spec.get("stress_counterexamples") or [])
    entry = {**payload, "artifact_version": ver}
    items.append(entry)
    spec["stress_counterexamples"] = items[-MAX_COUNTEREXAMPLES:]
    spec["last_stress"] = {
        **(spec.get("last_stress") or {}),
        "last_counterexample": entry,
    }
    problem.spec_json = spec

    await emit_event(
        session,
        problem_id=problem.id,
        type="stress.counterexample.archived",
        message=f"Counterexample round={payload.get('round')} reason={payload.get('reason')}",
        source="stress",
        job_id=uuid.UUID(str(job_id)) if job_id else None,
        level="WARN",
        payload=entry,
    )
    await session.flush()
    return entry
