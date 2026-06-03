from sqlalchemy.ext.asyncio import AsyncSession

from duliu.facade.llm_secrets import apply_llm_secrets


async def apply_workspace_secrets(session: AsyncSession, workspace_id) -> None:
    await apply_llm_secrets(session, workspace_id)
