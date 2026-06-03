"""M19 Polygon official API client (key/secret signing)."""

from __future__ import annotations

import hashlib
import random
import string
import time
from typing import Any

import httpx

POLYGON_API_BASE = "https://polygon.codeforces.com/api/"
_ALPHABET = string.ascii_lowercase + string.digits


def _api_sig(method_name: str, params: dict[str, str], secret: str) -> str:
    rand = "".join(random.choice(_ALPHABET) for _ in range(6))
    pairs = sorted((k, str(v)) for k, v in params.items() if k != "apiSig")
    query = "&".join(f"{k}={v}" for k, v in pairs)
    digest = hashlib.sha512(f"{rand}/{method_name}?{query}#{secret}".encode()).hexdigest()
    return rand + digest


class PolygonApiError(Exception):
    def __init__(self, method: str, comment: str):
        self.method = method
        self.comment = comment
        super().__init__(f"{method}: {comment}")


async def polygon_api_request(
    method: str,
    *,
    api_key: str,
    api_secret: str,
    pin: str | None = None,
    timeout: float = 30.0,
    **params: Any,
) -> Any:
    """Call Polygon API method (e.g. problem.info). Returns result JSON or raises."""
    body: dict[str, str] = {k: str(v) for k, v in params.items() if v is not None}
    if pin:
        body["pin"] = pin
    body["apiKey"] = api_key
    body["time"] = str(int(time.time()))
    body["apiSig"] = _api_sig(method, body, api_secret)

    url = f"{POLYGON_API_BASE}{method}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, data=body)
        r.raise_for_status()
        data = r.json()

    if data.get("status") != "OK":
        raise PolygonApiError(method, data.get("comment") or "unknown error")
    return data.get("result")


async def polygon_api_configured(session, workspace_id) -> tuple[str | None, str | None]:
    from duliu.facade.secrets_store import get_workspace_secret

    key = await get_workspace_secret(session, workspace_id, "polygon_api_key")
    secret = await get_workspace_secret(session, workspace_id, "polygon_api_secret")
    return key, secret
