"""HTTP client for the Duliu FastAPI service."""

from __future__ import annotations

from typing import Any

import httpx

from duliu_mcp.config import settings


class DuliuApiError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class DuliuApiClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self._base_url = (base_url or settings.duliu_api_base_url).rstrip("/")
        self._timeout = timeout or settings.duliu_api_timeout_seconds

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self._base_url}{path}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.request(method, url, **kwargs)
        if response.is_error:
            detail = response.text[:500]
            raise DuliuApiError(
                f"Duliu API {method} {path} failed ({response.status_code}): {detail}",
                status_code=response.status_code,
            )
        if response.status_code == 204:
            return None
        return response.json()

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/api/health")

    async def get_tree(self) -> dict[str, Any]:
        return await self._request("GET", "/api/tree")

    async def list_problems(self) -> list[dict[str, Any]]:
        tree = await self.get_tree()
        problems = tree.get("problems", [])
        return problems if isinstance(problems, list) else []

    async def get_problem(self, problem_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/problems/{problem_id}")

    async def list_artifacts(self, problem_id: str) -> list[dict[str, Any]]:
        data = await self._request("GET", f"/api/problems/{problem_id}/artifacts")
        return data if isinstance(data, list) else []

    async def get_artifact(self, problem_id: str, kind: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/problems/{problem_id}/artifacts/{kind}")
