import json

from mcp.server.fastmcp import FastMCP

from duliu_mcp.client import DuliuApiClient, DuliuApiError
from duliu_mcp.schemas import GetArtifactInput, ListArtifactsInput


def register(mcp: FastMCP) -> None:
    client = DuliuApiClient()

    @mcp.tool(
        name="duliu_list_artifacts",
        annotations={
            "title": "List problem artifacts",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
        },
    )
    async def duliu_list_artifacts(problem_id: str) -> str:
        """List artifact metadata for a problem (statement, std, gen, ...)."""
        params = ListArtifactsInput(problem_id=problem_id)
        try:
            artifacts = await client.list_artifacts(params.problem_id)
            return json.dumps(
                {"problem_id": params.problem_id, "count": len(artifacts), "artifacts": artifacts},
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        except DuliuApiError as exc:
            return json.dumps({"error": str(exc), "problem_id": params.problem_id})

    @mcp.tool(
        name="duliu_get_artifact",
        annotations={
            "title": "Get problem artifact content",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
        },
    )
    async def duliu_get_artifact(problem_id: str, kind: str) -> str:
        """Fetch full content of one artifact kind for a problem."""
        params = GetArtifactInput(problem_id=problem_id, kind=kind)
        try:
            artifact = await client.get_artifact(params.problem_id, params.kind)
            return json.dumps(artifact, ensure_ascii=False, indent=2, default=str)
        except DuliuApiError as exc:
            return json.dumps(
                {"error": str(exc), "problem_id": params.problem_id, "kind": params.kind},
            )
