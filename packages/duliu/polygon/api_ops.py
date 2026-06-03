"""M19 Polygon API operations tied to Duliu problems."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from duliu.db.models import Problem
from duliu.facade.events import emit_event
from duliu.polygon.api_client import PolygonApiError, polygon_api_configured, polygon_api_request


def _polygon_meta(problem: Problem) -> dict:
    return dict((problem.spec_json or {}).get("polygon_api") or {})


def _set_polygon_meta(problem: Problem, patch: dict) -> None:
    problem.spec_json = {
        **(problem.spec_json or {}),
        "polygon_api": {**_polygon_meta(problem), **patch},
    }


def polygon_problem_id(problem: Problem) -> int | None:
    meta = _polygon_meta(problem)
    raw = meta.get("problem_id") or (problem.spec_json or {}).get("polygon_problem_id")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


async def polygon_api_status(session: AsyncSession, workspace_id: uuid.UUID) -> dict:
    key, secret = await polygon_api_configured(session, workspace_id)
    return {
        "api_configured": bool(key and secret),
        "methods": [
            "problems.list",
            "problem.info",
            "problem.packages",
            "problem.commitChanges",
            "problem.buildPackage",
            "problem.package",
        ],
    }


def _latest_package_id(packages: list | Any) -> int | None:
    if not isinstance(packages, list) or not packages:
        return None
    best_id = -1
    for pkg in packages:
        if not isinstance(pkg, dict):
            continue
        pid = pkg.get("id") or pkg.get("packageId")
        try:
            n = int(pid)
        except (TypeError, ValueError):
            continue
        if n > best_id:
            best_id = n
    return best_id if best_id >= 0 else None


async def link_polygon_problem(
    session: AsyncSession,
    problem: Problem,
    *,
    workspace_id: uuid.UUID,
    polygon_problem_id: int | None = None,
    pin: str | None = None,
) -> dict:
    key, secret = await polygon_api_configured(session, workspace_id)
    if not key or not secret:
        return {"ok": False, "reason": "polygon_api_not_configured"}

    pid = polygon_problem_id
    if pid is None:
        try:
            problems = await polygon_api_request(
                "problems.list",
                api_key=key,
                api_secret=secret,
                pin=pin,
                name=problem.title[:80],
            )
            if isinstance(problems, list) and problems:
                pid = int(problems[0].get("id"))
        except (PolygonApiError, TypeError, ValueError, IndexError) as exc:
            return {"ok": False, "reason": "link_failed", "error": str(exc)}

    if pid is None:
        return {"ok": False, "reason": "no_polygon_problem_id"}

    info = await polygon_api_request(
        "problem.info",
        api_key=key,
        api_secret=secret,
        pin=pin,
        problemId=pid,
    )
    _set_polygon_meta(
        problem,
        {
            "problem_id": pid,
            "linked_at": datetime.now(timezone.utc).isoformat(),
            "info": info if isinstance(info, dict) else {"raw": info},
        },
    )
    await emit_event(
        session,
        problem_id=problem.id,
        type="polygon.api.linked",
        message=f"Linked Polygon problem {pid}",
        source="polygon_api",
        payload={"problem_id": pid},
    )
    await session.flush()
    return {"ok": True, "polygon_problem_id": pid, "info": info}


async def sync_polygon_packages(
    session: AsyncSession,
    problem: Problem,
    *,
    workspace_id: uuid.UUID,
    pin: str | None = None,
) -> dict:
    key, secret = await polygon_api_configured(session, workspace_id)
    if not key or not secret:
        return {"ok": False, "reason": "polygon_api_not_configured"}

    pid = polygon_problem_id(problem)
    if pid is None:
        link = await link_polygon_problem(session, problem, workspace_id=workspace_id, pin=pin)
        if not link.get("ok"):
            return link
        pid = link["polygon_problem_id"]

    try:
        packages = await polygon_api_request(
            "problem.packages",
            api_key=key,
            api_secret=secret,
            pin=pin,
            problemId=pid,
        )
        info = await polygon_api_request(
            "problem.info",
            api_key=key,
            api_secret=secret,
            pin=pin,
            problemId=pid,
        )
    except PolygonApiError as exc:
        return {"ok": False, "reason": "api_error", "error": str(exc)}

    _set_polygon_meta(
        problem,
        {
            "problem_id": pid,
            "synced_at": datetime.now(timezone.utc).isoformat(),
            "packages": packages,
            "info": info if isinstance(info, dict) else {"raw": info},
        },
    )
    await emit_event(
        session,
        problem_id=problem.id,
        type="polygon.api.synced",
        message=f"Synced Polygon packages for {pid}",
        source="polygon_api",
        payload={"package_count": len(packages) if isinstance(packages, list) else 0},
    )
    await session.flush()
    return {
        "ok": True,
        "polygon_problem_id": pid,
        "packages": packages,
        "package_count": len(packages) if isinstance(packages, list) else 0,
    }


async def build_polygon_package(
    session: AsyncSession,
    problem: Problem,
    *,
    workspace_id: uuid.UUID,
    full: bool = False,
    verify: bool = True,
    commit_first: bool = True,
    pin: str | None = None,
) -> dict:
    key, secret = await polygon_api_configured(session, workspace_id)
    if not key or not secret:
        return {"ok": False, "reason": "polygon_api_not_configured"}

    pid = polygon_problem_id(problem)
    if pid is None:
        link = await link_polygon_problem(session, problem, workspace_id=workspace_id, pin=pin)
        if not link.get("ok"):
            return link
        pid = link["polygon_problem_id"]

    steps: list[dict[str, Any]] = []
    try:
        if commit_first:
            await polygon_api_request(
                "problem.commitChanges",
                api_key=key,
                api_secret=secret,
                pin=pin,
                problemId=pid,
                minorChanges="true",
            )
            steps.append({"step": "commitChanges", "ok": True})

        await polygon_api_request(
            "problem.buildPackage",
            api_key=key,
            api_secret=secret,
            pin=pin,
            problemId=pid,
            full="true" if full else "false",
            verify="true" if verify else "false",
        )
        steps.append({"step": "buildPackage", "ok": True, "full": full, "verify": verify})

        packages = await polygon_api_request(
            "problem.packages",
            api_key=key,
            api_secret=secret,
            pin=pin,
            problemId=pid,
        )
        steps.append({"step": "packages", "count": len(packages) if isinstance(packages, list) else 0})
    except PolygonApiError as exc:
        return {
            "ok": False,
            "reason": "api_error",
            "error": str(exc),
            "polygon_problem_id": pid,
            "steps": steps,
        }

    _set_polygon_meta(
        problem,
        {
            "problem_id": pid,
            "last_build": {
                "at": datetime.now(timezone.utc).isoformat(),
                "full": full,
                "verify": verify,
                "packages": packages,
            },
        },
    )
    await emit_event(
        session,
        problem_id=problem.id,
        type="polygon.api.build_package",
        message=f"buildPackage queued/done for Polygon {pid}",
        source="polygon_api",
        payload={"full": full, "verify": verify},
    )
    await session.flush()
    return {
        "ok": True,
        "polygon_problem_id": pid,
        "packages": packages,
        "steps": steps,
    }


async def download_polygon_package(
    session: AsyncSession,
    problem: Problem,
    *,
    workspace_id: uuid.UUID,
    package_id: int | None = None,
    package_type: str = "standard",
    pin: str | None = None,
) -> dict:
    """Download Polygon package zip to local package dir."""
    import os
    from pathlib import Path

    from duliu.polygon.api_client import polygon_api_download

    key, secret = await polygon_api_configured(session, workspace_id)
    if not key or not secret:
        return {"ok": False, "reason": "polygon_api_not_configured"}

    pid = polygon_problem_id(problem)
    if pid is None:
        link = await link_polygon_problem(session, problem, workspace_id=workspace_id, pin=pin)
        if not link.get("ok"):
            return link
        pid = link["polygon_problem_id"]

    packages = await polygon_api_request(
        "problem.packages",
        api_key=key,
        api_secret=secret,
        pin=pin,
        problemId=pid,
    )
    pkg_id = package_id or _latest_package_id(packages)
    if pkg_id is None:
        return {"ok": False, "reason": "no_packages_on_polygon", "polygon_problem_id": pid}

    base = Path(os.environ.get("DULIU_PACKAGE_DIR", "/tmp/duliu-packages")) / str(problem.id)
    dest = base / f"polygon_api_{pkg_id}_{package_type}.zip"
    try:
        dl = await polygon_api_download(
            "problem.package",
            dest,
            api_key=key,
            api_secret=secret,
            pin=pin,
            problemId=pid,
            packageId=pkg_id,
            type=package_type,
        )
    except PolygonApiError as exc:
        return {"ok": False, "reason": "api_error", "error": str(exc), "package_id": pkg_id}

    _set_polygon_meta(
        problem,
        {
            "problem_id": pid,
            "last_download": {
                "at": datetime.now(timezone.utc).isoformat(),
                "package_id": pkg_id,
                "type": package_type,
                **dl,
            },
        },
    )
    await emit_event(
        session,
        problem_id=problem.id,
        type="polygon.api.download",
        message=f"Downloaded Polygon package {pkg_id} -> {dl['path']}",
        source="polygon_api",
        payload=dl,
    )
    await session.flush()
    return {
        "ok": True,
        "polygon_problem_id": pid,
        "package_id": pkg_id,
        "package_type": package_type,
        **dl,
    }


async def sync_package_with_polygon(
    session: AsyncSession,
    problem: Problem,
    *,
    workspace_id: uuid.UUID,
    pin: str | None = None,
    local_report: dict | None = None,
) -> dict:
    """M20: local export + Polygon commit/build + download latest package."""
    import os
    from pathlib import Path

    from sqlalchemy import select

    from duliu.db.models import Artifact
    from duliu.polygon.export import export_polygon_to_dir

    if local_report is not None:
        local = local_report
    else:
        artifacts = (
            await session.execute(select(Artifact).where(Artifact.problem_id == problem.id))
        ).scalars().all()
        base = Path(os.environ.get("DULIU_PACKAGE_DIR", "/tmp/duliu-packages")) / str(problem.id)
        local = export_polygon_to_dir(problem, list(artifacts), base)

    key, secret = await polygon_api_configured(session, workspace_id)
    if not key or not secret:
        return {
            "ok": local.get("ok", False),
            "mode": "local_only",
            "local": local,
            "reason": "polygon_api_not_configured",
        }

    build = await build_polygon_package(
        session, problem, workspace_id=workspace_id, pin=pin, commit_first=True
    )
    download = await download_polygon_package(
        session, problem, workspace_id=workspace_id, pin=pin
    )
    _set_polygon_meta(
        problem,
        {
            "last_sync": {
                "at": datetime.now(timezone.utc).isoformat(),
                "local_zip": local.get("zip_path"),
                "remote_zip": download.get("path"),
                "build_ok": build.get("ok"),
                "download_ok": download.get("ok"),
            },
        },
    )
    await session.flush()
    return {
        "ok": bool(local.get("ok")) and build.get("ok") and download.get("ok"),
        "mode": "bidirectional",
        "local": local,
        "build": build,
        "download": download,
    }
