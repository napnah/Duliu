"""OpenAI-compatible chat helper for stage/session agents."""

from __future__ import annotations

from duliu.agents.llm_config import get_active_llm


async def chat_completion(
    *,
    system: str,
    user: str,
    max_tokens: int = 1200,
) -> str | None:
    cfg = get_active_llm()
    if not cfg.is_configured():
        return None
    import httpx

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                cfg.base_url,
                headers={"Authorization": f"Bearer {cfg.api_key}"},
                json={
                    "model": cfg.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "max_tokens": max_tokens,
                },
            )
            r.raise_for_status()
            data = r.json()
        return (data.get("choices") or [{}])[0].get("message", {}).get("content")
    except Exception:
        return None


async def chat_messages(
    messages: list[dict],
    *,
    tools: list[dict] | None = None,
    max_tokens: int = 800,
) -> dict | None:
    """Return assistant message dict (may include tool_calls)."""
    cfg = get_active_llm()
    if not cfg.is_configured():
        return None
    import httpx

    body: dict = {
        "model": cfg.model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            r = await client.post(
                cfg.base_url,
                headers={"Authorization": f"Bearer {cfg.api_key}"},
                json=body,
            )
            r.raise_for_status()
            data = r.json()
        return (data.get("choices") or [{}])[0].get("message") or {}
    except Exception:
        return None
