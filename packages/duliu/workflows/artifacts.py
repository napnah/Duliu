"""Shared artifact helpers for creation workflows."""

from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from duliu.db.models import Artifact, Problem


async def save_artifact(
    session: AsyncSession,
    problem: Problem,
    kind: str,
    content: str,
    *,
    author: str,
    language: str | None = None,
) -> int:
    row = (
        await session.execute(
            select(Artifact)
            .where(Artifact.problem_id == problem.id, Artifact.kind == kind)
            .order_by(Artifact.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    ver = (row.version + 1) if row else 1
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
    await session.flush()
    return ver
