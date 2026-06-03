"""HTTP fetch with optional session cookies from workspace secrets."""

from __future__ import annotations

import httpx

DEFAULT_HEADERS = {
    "User-Agent": "Duliu-M5-Crawler/1.0 (educational; +https://github.com/napnah/Duliu)",
    "Accept": "text/html,application/xhtml+xml",
}


async def fetch_url(url: str, *, cookie: str | None = None, timeout: float = 30.0) -> str:
    headers = dict(DEFAULT_HEADERS)
    if cookie:
        headers["Cookie"] = cookie.strip()
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        r = await client.get(url, headers=headers)
        r.raise_for_status()
        return r.text
