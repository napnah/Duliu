"""M8 artifact version list and restore."""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from duliu.db.models import Artifact
from duliu.facade.events import emit_event


class ArtifactFacade:
    @staticmethod
    async def list_versions(
        session: AsyncSession, problem_id: uuid.UUID, kind: str
    ) -> list[dict]:
        rows = (
            await session.execute(
                select(Artifact)
                .where(Artifact.problem_id == problem_id, Artifact.kind == kind)
                .order_by(Artifact.version.desc())
            )
        ).scalars().all()
        return [
            {
                "version": a.version,
                "id": str(a.id),
                "author": a.author,
                "language": a.language,
                "sha256": a.sha256,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in rows
        ]

    @staticmethod
    async def restore_version(
        session: AsyncSession,
        problem_id: uuid.UUID,
        kind: str,
        version: int,
        *,
        author: str = "restore",
    ) -> Artifact:
        result = await session.execute(
            select(Artifact).where(
                Artifact.problem_id == problem_id,
                Artifact.kind == kind,
                Artifact.version == version,
            )
        )
        src = result.scalar_one_or_none()
        if not src:
            raise ValueError(f"No artifact {kind} version {version}")

        latest = (
            await session.execute(
                select(Artifact)
                .where(Artifact.problem_id == problem_id, Artifact.kind == kind)
                .order_by(Artifact.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        new_ver = (latest.version + 1) if latest else 1
        content = src.content_text
        art = Artifact(
            problem_id=problem_id,
            kind=kind,
            version=new_ver,
            content_text=content,
            sha256=hashlib.sha256(content.encode()).hexdigest(),
            author=author,
            language=src.language,
        )
        session.add(art)
        await emit_event(
            session,
            problem_id=problem_id,
            type="artifact.restored",
            message=f"Restored {kind} from v{version} → v{new_ver}",
            source="artifact",
            payload={"from_version": version, "to_version": new_ver, "kind": kind},
        )
        await session.flush()
        return art
