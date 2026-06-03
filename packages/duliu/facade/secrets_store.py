"""Workspace secret read/write helpers (M5 crawler + OpenAI)."""

from __future__ import annotations

import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from duliu.db.models import Workspace, WorkspaceSecret


async def get_workspace_secret(
    session: AsyncSession, workspace_id: uuid.UUID, key_name: str
) -> str | None:
    row = (
        await session.execute(
            select(WorkspaceSecret).where(
                WorkspaceSecret.workspace_id == workspace_id,
                WorkspaceSecret.key_name == key_name,
            )
        )
    ).scalar_one_or_none()
    if row and row.value_encrypted:
        return row.value_encrypted
    return None


async def set_workspace_secret(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    key_name: str,
    value: str | None,
) -> None:
    row = (
        await session.execute(
            select(WorkspaceSecret).where(
                WorkspaceSecret.workspace_id == workspace_id,
                WorkspaceSecret.key_name == key_name,
            )
        )
    ).scalar_one_or_none()
    if value is None or value == "":
        if row:
            await session.delete(row)
        return
    if row:
        row.value_encrypted = value
    else:
        session.add(
            WorkspaceSecret(
                workspace_id=workspace_id,
                key_name=key_name,
                value_encrypted=value,
            )
        )


async def get_crawler_config(session: AsyncSession, workspace: Workspace) -> dict:
    sites_raw = await get_workspace_secret(session, workspace.id, "crawler_sites")
    sites = []
    if sites_raw:
        try:
            sites = json.loads(sites_raw)
        except json.JSONDecodeError:
            sites = [ln.strip() for ln in sites_raw.splitlines() if ln.strip()]
    cf = await get_workspace_secret(session, workspace.id, "crawler_cf_cookie")
    lg = await get_workspace_secret(session, workspace.id, "crawler_luogu_cookie")
    poly = await get_workspace_secret(session, workspace.id, "crawler_polygon_cookie")
    pkey = await get_workspace_secret(session, workspace.id, "polygon_api_key")
    psec = await get_workspace_secret(session, workspace.id, "polygon_api_secret")
    return {
        "crawl_sites": sites if isinstance(sites, list) else [],
        "cf_cookie_configured": bool(cf),
        "cf_cookie_masked": _mask(cf),
        "luogu_cookie_configured": bool(lg),
        "luogu_cookie_masked": _mask(lg),
        "polygon_cookie_configured": bool(poly),
        "polygon_cookie_masked": _mask(poly),
        "polygon_api_configured": bool(pkey and psec),
        "polygon_api_key_masked": _mask(pkey),
        "whitelist_hosts": sorted(
            {
                "codeforces.com",
                "atcoder.jp",
                "luogu.com.cn",
            }
        ),
    }


async def set_crawler_config(session: AsyncSession, workspace: Workspace, body: dict) -> dict:
    if "crawl_sites" in body and body["crawl_sites"] is not None:
        await set_workspace_secret(
            session,
            workspace.id,
            "crawler_sites",
            json.dumps(body["crawl_sites"], ensure_ascii=False),
        )
    if "cf_cookie" in body:
        await set_workspace_secret(session, workspace.id, "crawler_cf_cookie", body["cf_cookie"])
    if "luogu_cookie" in body:
        await set_workspace_secret(session, workspace.id, "crawler_luogu_cookie", body["luogu_cookie"])
    if "polygon_cookie" in body:
        await set_workspace_secret(
            session, workspace.id, "crawler_polygon_cookie", body["polygon_cookie"]
        )
    if "polygon_api_key" in body:
        await set_workspace_secret(session, workspace.id, "polygon_api_key", body["polygon_api_key"])
    if "polygon_api_secret" in body:
        await set_workspace_secret(
            session, workspace.id, "polygon_api_secret", body["polygon_api_secret"]
        )
    return await get_crawler_config(session, workspace)


def _mask(val: str | None) -> str | None:
    if not val:
        return None
    if len(val) < 8:
        return "****"
    return val[:3] + "..." + val[-4:]
