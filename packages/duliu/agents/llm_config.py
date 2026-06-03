"""Runtime LLM config (populated from workspace secrets / env)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from duliu.agents.llm_providers import ACTIVE_PROVIDER_SECRET, PROVIDERS, PROVIDER_IDS


@dataclass
class ActiveLlmConfig:
    provider: str = "openai"
    api_key: str = ""
    model: str = ""
    base_url: str = ""

    def is_configured(self) -> bool:
        return bool(self.api_key.strip())


_active = ActiveLlmConfig()


def get_active_llm() -> ActiveLlmConfig:
    return _active


def set_active_llm(
    *,
    provider: str,
    api_key: str,
    model: str,
    base_url: str,
) -> None:
    global _active
    _active = ActiveLlmConfig(
        provider=provider,
        api_key=api_key.strip(),
        model=model.strip(),
        base_url=base_url,
    )


def resolve_from_env() -> ActiveLlmConfig | None:
    """Pick first provider with env API key (respect DULIU_LLM_PROVIDER if set)."""
    preferred = (os.environ.get("DULIU_LLM_PROVIDER") or "").strip().lower()
    order = [preferred] if preferred in PROVIDER_IDS else []
    order.extend(p for p in PROVIDER_IDS if p not in order)
    for pid in order:
        spec = PROVIDERS[pid]
        key = (os.environ.get(spec.env_api_key) or "").strip()
        if pid == "openai" and not key:
            from duliu.config import settings

            key = (settings.openai_api_key or "").strip()
        if not key:
            continue
        model = (os.environ.get(spec.env_model) or "").strip() or spec.default_model
        return ActiveLlmConfig(provider=pid, api_key=key, model=model, base_url=spec.base_url)
    return None


def apply_active_from_workspace(
    *,
    active_provider: str,
    secrets: dict[str, str | None],
) -> ActiveLlmConfig:
    """Build runtime config from workspace secret map."""
    provider = active_provider if active_provider in PROVIDER_IDS else "openai"
    spec = PROVIDERS[provider]
    key = (secrets.get(spec.api_key_secret) or "").strip()
    if not key and provider == "openai":
        from duliu.config import settings

        key = (settings.openai_api_key or "").strip()
    model = (secrets.get(spec.model_secret) or "").strip() or spec.default_model
    cfg = ActiveLlmConfig(provider=provider, api_key=key, model=model, base_url=spec.base_url)
    set_active_llm(
        provider=cfg.provider,
        api_key=cfg.api_key,
        model=cfg.model,
        base_url=cfg.base_url,
    )
    return cfg
