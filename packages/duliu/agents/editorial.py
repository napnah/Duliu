"""S8 EDITORIAL: ensure editorial draft exists."""

from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from duliu.db.models import Artifact, Problem

DEFAULT_EDITORIAL = """# 题解（草稿）

## 思路

（待补充）

## 复杂度

- 时间：
- 空间：

## 实现要点

（待补充）
"""


async def run_editorial_draft(session: AsyncSession, problem: Problem) -> dict:
    existing = (
        await session.execute(
            select(Artifact)
            .where(Artifact.problem_id == problem.id, Artifact.kind == "editorial")
            .order_by(Artifact.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing:
        return {"ok": True, "created": False, "version": existing.version, "summary": "题解已存在"}
    session.add(
        Artifact(
            problem_id=problem.id,
            kind="editorial",
            version=1,
            content_text=DEFAULT_EDITORIAL.replace("（草稿）", f"（{problem.title}）"),
            sha256=hashlib.sha256(DEFAULT_EDITORIAL.encode()).hexdigest(),
            author="editorialist",
            language="markdown",
        )
    )
    return {"ok": True, "created": True, "version": 1, "summary": "已生成题解草稿"}
