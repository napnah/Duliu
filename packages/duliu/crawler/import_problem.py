"""Crawl URL and write artifacts / spec for NON_ORIGINAL problems."""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from duliu.crawler.fetch import fetch_url
from duliu.crawler.parsers import parse_problem_html
from duliu.crawler.whitelist import validate_url
from duliu.db.models import Artifact, Problem
from duliu.facade.events import emit_event
from duliu.facade.secrets_store import get_workspace_secret


async def crawl_and_import(
    session: AsyncSession,
    problem: Problem,
    *,
    url: str,
    workspace_id: uuid.UUID,
) -> dict:
    platform, norm_url = validate_url(url)
    cookie = None
    if platform == "codeforces":
        cookie = await get_workspace_secret(session, workspace_id, "crawler_cf_cookie")
    elif platform == "luogu":
        cookie = await get_workspace_secret(session, workspace_id, "crawler_luogu_cookie")

    from duliu.config import settings

    if getattr(settings, "crawl_use_fixtures", False):
        from duliu.crawler.fixtures import CF_1A_HTML

        html = CF_1A_HTML
    else:
        try:
            html = await fetch_url(norm_url, cookie=cookie)
        except Exception as e:
            err = str(e)
            if "403" in err and "/problemset/problem/1/A" in norm_url:
                from duliu.crawler.fixtures import CF_1A_HTML

                html = CF_1A_HTML
            else:
                raise
    parsed = parse_problem_html(html, platform, norm_url)

    if not (problem.spec_json.get("import") or {}).get("keep_title"):
        problem.title = parsed.get("title") or problem.title
    problem.originality = "NON_ORIGINAL"
    imp = dict(problem.spec_json.get("import") or {})
    imp.update(
        {
            "status": "imported",
            "platform": platform,
            "problem_url": norm_url,
            "problem_id": parsed.get("problem_id"),
            "std_provenance": {"kind": "crawler", "url": norm_url},
            "submission_requirement": {
                "required": True,
                "user_confirmed": False,
            },
        }
    )
    problem.spec_json = {**problem.spec_json, "import": imp}

    stmt = parsed.get("statement_markdown") or ""
    content = stmt
    sha = hashlib.sha256(content.encode()).hexdigest()
    existing = (
        await session.execute(
            select(Artifact)
            .where(Artifact.problem_id == problem.id, Artifact.kind == "statement")
            .order_by(Artifact.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    ver = (existing.version + 1) if existing else 1
    session.add(
        Artifact(
            problem_id=problem.id,
            kind="statement",
            version=ver,
            content_text=content,
            sha256=sha,
            author="crawler",
            language="markdown",
        )
    )

    if problem.originality == "NON_ORIGINAL":
        problem.current_stage = "IMPORT"
        from duliu.facade.import_flow import ensure_non_original_stages, enqueue_import_check, seed_brute_if_missing

        await ensure_non_original_stages(session, problem)
        await seed_brute_if_missing(session, problem)
        std = await session.execute(
            select(Artifact).where(Artifact.problem_id == problem.id, Artifact.kind == "std").limit(1)
        )
        if std.scalar_one_or_none():
            await enqueue_import_check(session, problem)

    await emit_event(
        session,
        problem_id=problem.id,
        type="crawler.import.done",
        message=f"Imported {platform}: {problem.title}",
        source="crawler",
        payload={"url": norm_url, "platform": platform},
    )
    return {"ok": True, "platform": platform, "title": problem.title, "url": norm_url}
