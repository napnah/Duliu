"""M11: seed workspace secrets from environment (dev/test only, skips if already set)."""

from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncSession

from duliu.db.models import Workspace
from duliu.facade.secrets_store import get_workspace_secret, set_workspace_secret

_ENV_SECRETS = (
    ("DULIU_CF_COOKIE", "crawler_cf_cookie"),
    ("DULIU_LUOGU_COOKIE", "crawler_luogu_cookie"),
    ("DULIU_POLYGON_COOKIE", "crawler_polygon_cookie"),
    ("DULIU_POLYGON_API_KEY", "polygon_api_key"),
    ("DULIU_POLYGON_API_SECRET", "polygon_api_secret"),
)


async def bootstrap_secrets_from_env(session: AsyncSession, workspace: Workspace) -> list[str]:
    """Return list of secret keys seeded from env."""
    seeded: list[str] = []
    for env_name, key_name in _ENV_SECRETS:
        val = (os.environ.get(env_name) or "").strip()
        if not val:
            continue
        existing = await get_workspace_secret(session, workspace.id, key_name)
        if existing:
            continue
        await set_workspace_secret(session, workspace.id, key_name, val)
        seeded.append(key_name)
    return seeded
