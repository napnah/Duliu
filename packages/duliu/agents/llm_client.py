"""Shared OpenAI chat helper for stage agents (M14)."""

from __future__ import annotations

from duliu.config import settings


async def chat_completion(
    *,
    system: str,
    user: str,
    max_tokens: int = 1200,
) -> str | None:
    if not settings.openai_api_key:
        return None
    import httpx

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": settings.openai_model,
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
