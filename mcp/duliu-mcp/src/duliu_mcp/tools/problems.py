import json

from mcp.server.fastmcp import FastMCP

from duliu_mcp.client import DuliuApiClient, DuliuApiError
from duliu_mcp.schemas import GetProblemInput


def register(mcp: FastMCP) -> None:
    client = DuliuApiClient()

    @mcp.tool(
        name="duliu_list_problems",
        annotations={
            "title": "List Duliu problems",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
        },
    )
    async def duliu_list_problems() -> str:
        """List all problems in the default Duliu workspace (via /api/tree)."""
        try:
            problems = await client.list_problems()
            return json.dumps({"count": len(problems), "problems": problems}, ensure_ascii=False, indent=2)
        except DuliuApiError as exc:
            return json.dumps({"error": str(exc), "hint": "Ensure Duliu API is running (docker compose up)."})

    @mcp.tool(
        name="duliu_get_problem",
        annotations={
            "title": "Get Duliu problem",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
        },
    )
    async def duliu_get_problem(problem_id: str) -> str:
        """Fetch a single problem by UUID, including spec_json and current stage."""
        params = GetProblemInput(problem_id=problem_id)
        try:
            problem = await client.get_problem(params.problem_id)
            return json.dumps(problem, ensure_ascii=False, indent=2, default=str)
        except DuliuApiError as exc:
            return json.dumps({"error": str(exc), "problem_id": params.problem_id})
