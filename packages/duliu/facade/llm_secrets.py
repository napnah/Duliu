"""Workspace LLM provider secrets (OpenAI / DeepSeek / Qwen / GLM)."""

from __future__ import annotations

import os
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from duliu.agents.llm_config import apply_active_from_workspace, resolve_from_env, set_active_llm
from duliu.agents.llm_providers import ACTIVE_PROVIDER_SECRET, PROVIDERS, PROVIDER_IDS
from duliu.db.models import Workspace
from duliu.facade.secrets_store import get_workspace_secret, set_workspace_secret


def _mask(val: str | None) -> str | None:
    if not val:
        return None
    if len(val) < 8:
        return "****"
    return val[:3] + "..." + val[-4:]


async def _load_secret_map(session: AsyncSession, workspace_id: uuid.UUID) -> dict[str, str | None]:
    keys = [ACTIVE_PROVIDER_SECRET]
    for spec in PROVIDERS.values():
        keys.extend([spec.api_key_secret, spec.model_secret])
    out: dict[str, str | None] = {}
    for k in keys:
        out[k] = await get_workspace_secret(session, workspace_id, k)
    return out


async def get_llm_config(session: AsyncSession, workspace: Workspace) -> dict:
    secrets = await _load_secret_map(session, workspace.id)
    active = (secrets.get(ACTIVE_PROVIDER_SECRET) or "openai").strip().lower()
    if active not in PROVIDER_IDS:
        active = "openai"

    providers_out = {}
    any_configured = False
    for pid in PROVIDER_IDS:
        spec = PROVIDERS[pid]
        key = secrets.get(spec.api_key_secret)
        if pid == "openai" and not key:
            from duliu.config import settings

            if settings.openai_api_key:
                key = settings.openai_api_key
        model = secrets.get(spec.model_secret) or spec.default_model
        configured = bool(key)
        if configured:
            any_configured = True
        providers_out[pid] = {
            "label": spec.label,
            "configured": configured,
            "api_key_masked": _mask(key),
            "model": model,
            "default_model": spec.default_model,
        }

    env_cfg = resolve_from_env()
    if env_cfg and env_cfg.is_configured() and not any_configured:
        any_configured = True
        providers_out[env_cfg.provider]["configured"] = True
        providers_out[env_cfg.provider]["api_key_masked"] = _mask(env_cfg.api_key)
        providers_out[env_cfg.provider]["model"] = env_cfg.model
        if not secrets.get(ACTIVE_PROVIDER_SECRET):
            active = env_cfg.provider

    return {
        "active_provider": active,
        "providers": providers_out,
        "any_configured": any_configured,
        "active_configured": providers_out.get(active, {}).get("configured", False),
    }


async def set_llm_config(session: AsyncSession, workspace: Workspace, body: dict) -> dict:
    if "active_provider" in body and body["active_provider"] is not None:
        p = str(body["active_provider"]).strip().lower()
        if p in PROVIDER_IDS:
            await set_workspace_secret(session, workspace.id, ACTIVE_PROVIDER_SECRET, p)

    for pid in PROVIDER_IDS:
        spec = PROVIDERS[pid]
        key_field = f"{pid}_api_key"
        model_field = f"{pid}_model"
        if key_field in body:
            await set_workspace_secret(session, workspace.id, spec.api_key_secret, body[key_field])
        if model_field in body:
            await set_workspace_secret(session, workspace.id, spec.model_secret, body[model_field])

    # backward compat: openai_api_key on combined secrets PUT
    if body.get("openai_api_key") is not None:
        await set_workspace_secret(session, workspace.id, "openai_api_key", body["openai_api_key"])

    await session.flush()
    return await apply_llm_secrets(session, workspace.id)


async def apply_llm_secrets(session: AsyncSession, workspace_id: uuid.UUID) -> dict:
    """Load workspace LLM secrets into runtime; returns get_llm_config-shaped summary."""
    secrets = await _load_secret_map(session, workspace_id)
    active = (secrets.get(ACTIVE_PROVIDER_SECRET) or "openai").strip().lower()
    if active not in PROVIDER_IDS:
        active = "openai"

    cfg = apply_active_from_workspace(active_provider=active, secrets=secrets)
    if not cfg.is_configured():
        env_cfg = resolve_from_env()
        if env_cfg:
            set_active_llm(
                provider=env_cfg.provider,
                api_key=env_cfg.api_key,
                model=env_cfg.model,
                base_url=env_cfg.base_url,
            )
            cfg = env_cfg

    ws = await session.get(Workspace, workspace_id)
    if ws:
        return await get_llm_config(session, ws)
    return {"active_provider": cfg.provider, "any_configured": cfg.is_configured()}


async def bootstrap_llm_from_env(session: AsyncSession, workspace: Workspace) -> list[str]:
    """Seed provider API keys from env when not already in DB."""
    seeded: list[str] = []
    for pid, spec in PROVIDERS.items():
        val = (os.environ.get(spec.env_api_key) or "").strip()
        if pid == "openai" and not val:
            from duliu.config import settings

            val = (settings.openai_api_key or "").strip()
        if not val:
            continue
        existing = await get_workspace_secret(session, workspace.id, spec.api_key_secret)
        if existing:
            continue
        await set_workspace_secret(session, workspace.id, spec.api_key_secret, val)
        seeded.append(spec.api_key_secret)
        model = (os.environ.get(spec.env_model) or "").strip()
        if model:
            await set_workspace_secret(session, workspace.id, spec.model_secret, model)

    preferred = (os.environ.get("DULIU_LLM_PROVIDER") or "").strip().lower()
    if preferred in PROVIDER_IDS:
        existing = await get_workspace_secret(session, workspace.id, ACTIVE_PROVIDER_SECRET)
        if not existing:
            await set_workspace_secret(session, workspace.id, ACTIVE_PROVIDER_SECRET, preferred)
            seeded.append(ACTIVE_PROVIDER_SECRET)
    return seeded
