"""S7 PACKAGE: Polygon package build."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from duliu.db.models import Artifact, Problem
from duliu.polygon.export import export_polygon_to_dir


async def run_package_build(session: AsyncSession, problem: Problem) -> dict:
    artifacts = (
        await session.execute(select(Artifact).where(Artifact.problem_id == problem.id))
    ).scalars().all()
    base = Path(os.environ.get("DULIU_PACKAGE_DIR", "/tmp/duliu-packages"))
    out_dir = base / str(problem.id)
    report = export_polygon_to_dir(problem, list(artifacts), out_dir)
    polygon_sync = None
    try:
        from duliu.polygon.api_ops import sync_package_with_polygon

        polygon_sync = await sync_package_with_polygon(
            session, problem, workspace_id=problem.workspace_id, local_report=report
        )
    except Exception as exc:
        polygon_sync = {"ok": False, "reason": "sync_error", "error": str(exc)}

    summary = (
        f"题包已生成: {report['zip_path']} ({report['file_count']} 文件)"
        if report["ok"]
        else f"题包已生成但缺少: {', '.join(report['missing'])}"
    )
    if polygon_sync and polygon_sync.get("mode") == "bidirectional" and polygon_sync.get("ok"):
        dl = (polygon_sync.get("download") or {}).get("path")
        summary += f"；Polygon 已同步落盘: {dl}"
    elif polygon_sync and polygon_sync.get("reason") == "polygon_api_not_configured":
        summary += "（未配置 Polygon API，仅本地包）"
    manifest = {**report, "summary": summary, "polygon_sync": polygon_sync}
    content = json.dumps(manifest, ensure_ascii=False, indent=2)
    latest = (
        await session.execute(
            select(Artifact)
            .where(Artifact.problem_id == problem.id, Artifact.kind == "polygon_manifest")
            .order_by(Artifact.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    ver = (latest.version + 1) if latest else 1
    session.add(
        Artifact(
            problem_id=problem.id,
            kind="polygon_manifest",
            version=ver,
            content_text=content,
            sha256=hashlib.sha256(content.encode()).hexdigest(),
            author="polygon_adapter",
            language=None,
        )
    )
    return manifest
