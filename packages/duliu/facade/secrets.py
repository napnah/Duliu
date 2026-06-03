from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from duliu.config import settings
from duliu.db.models import WorkspaceSecret


async def apply_workspace_secrets(session: AsyncSession, workspace_id) -> None:
    row = (
        await session.execute(
            select(WorkspaceSecret).where(
                WorkspaceSecret.workspace_id == workspace_id,
                WorkspaceSecret.key_name == "openai_api_key",
            )
        )
    ).scalar_one_or_none()
    if row and row.value_encrypted:
        settings.openai_api_key = row.value_encrypted
