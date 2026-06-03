"""M13 Polygon package prepare + manual upload guidance (no official upload API)."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from duliu.db.models import Artifact, Problem
from duliu.facade.events import emit_event
from duliu.facade.secrets_store import get_workspace_secret
from duliu.polygon.export import export_polygon_to_dir

POLYGON_HOME = "https://polygon.codeforces.com/"


async def prepare_polygon_upload(
    session: AsyncSession,
    problem: Problem,
    *,
    workspace_id: uuid.UUID,
    force_reexport: bool = False,
) -> dict:
    """Export zip to package dir and record upload instructions in spec_json."""
    base = Path(os.environ.get("DULIU_PACKAGE_DIR", "/tmp/duliu-packages"))
    out_dir = base / str(problem.id)
    existing = (problem.spec_json or {}).get("polygon_upload") or {}
    if not force_reexport and existing.get("zip_path") and Path(existing["zip_path"]).is_file():
        report = {
            "ok": existing.get("ok", True),
            "zip_path": existing["zip_path"],
            "zip_size": existing.get("zip_size"),
            "missing": existing.get("missing", []),
            "reused": True,
        }
    else:
        artifacts = (
            await session.execute(select(Artifact).where(Artifact.problem_id == problem.id))
        ).scalars().all()
        report = export_polygon_to_dir(problem, list(artifacts), out_dir)
        report["reused"] = False

    cookie = await get_workspace_secret(session, workspace_id, "crawler_polygon_cookie")
    upload_meta = {
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "zip_path": report.get("zip_path"),
        "zip_size": report.get("zip_size"),
        "missing": report.get("missing", []),
        "ok": bool(report.get("ok")),
        "polygon_url": POLYGON_HOME,
        "mode": "manual",
        "cookie_configured": bool(cookie),
        "instructions": (
            "Download or open the local zip, then upload via Polygon web UI "
            "(Problems → Add → Upload package). Automatic upload is not supported."
        ),
    }
    if cookie:
        upload_meta["mode"] = "cookie_ready"
        upload_meta["note"] = "Polygon cookie stored; use browser session on polygon.codeforces.com"

    problem.spec_json = {**(problem.spec_json or {}), "polygon_upload": upload_meta}
    await emit_event(
        session,
        problem_id=problem.id,
        type="polygon.upload_prepared",
        message=f"Polygon package ready: {upload_meta.get('zip_path')}",
        source="polygon",
        payload=upload_meta,
    )
    await session.flush()
    return {**report, "upload": upload_meta}


async def attempt_polygon_upload(
    session: AsyncSession,
    problem: Problem,
    *,
    workspace_id: uuid.UUID,
) -> dict:
    """M16: prepare package + probe Polygon session with stored cookie."""
    import httpx

    base_report = await prepare_polygon_upload(
        session, problem, workspace_id=workspace_id, force_reexport=False
    )
    upload = dict((problem.spec_json or {}).get("polygon_upload") or {})
    cookie = await get_workspace_secret(session, workspace_id, "crawler_polygon_cookie")

    attempt = {
        "attempted_at": datetime.now(timezone.utc).isoformat(),
        "zip_path": upload.get("zip_path"),
        "auto_upload_supported": False,
    }

    if not cookie:
        attempt.update(
            {
                "ok": False,
                "mode": "manual",
                "reason": "polygon_cookie_not_configured",
                "instructions": upload.get("instructions"),
            }
        )
    else:
        session_ok = False
        status_code = 0
        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                r = await client.get(
                    POLYGON_HOME,
                    headers={"Cookie": cookie.strip()},
                )
                status_code = r.status_code
                body = r.text[:5000]
                session_ok = r.status_code == 200 and (
                    "polygon" in body.lower() or "logout" in body.lower() or "Problems" in body
                )
        except Exception as exc:
            attempt["probe_error"] = str(exc)

        attempt.update(
            {
                "ok": session_ok,
                "mode": "session_probe" if session_ok else "manual",
                "http_status": status_code,
                "session_valid": session_ok,
                "upload_entry_url": f"{POLYGON_HOME}",
                "instructions": (
                    "Cookie 探活"
                    + ("通过" if session_ok else "未确认")
                    + "。请在 Polygon 网页手动上传 zip："
                    + str(upload.get("zip_path") or "")
                ),
            }
        )

    upload["last_attempt"] = attempt
    problem.spec_json = {**(problem.spec_json or {}), "polygon_upload": upload}
    await emit_event(
        session,
        problem_id=problem.id,
        type="polygon.upload_attempted",
        message=attempt.get("instructions", "polygon upload attempt")[:200],
        source="polygon",
        payload=attempt,
    )
    await session.flush()
    return {**base_report, "attempt": attempt, "upload": upload}
