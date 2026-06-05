import json

from mcp.server.fastmcp import FastMCP

from duliu_mcp.client import DuliuApiClient, DuliuApiError
from duliu_mcp.schemas import ExportPolygonPackageInput, ExportTestDataInput
from duliu_mcp.services import PolygonExporter, TestDataExporter


def register(mcp: FastMCP) -> None:
    client = DuliuApiClient()
    test_exporter = TestDataExporter()
    polygon_exporter = PolygonExporter()

    @mcp.tool(
        name="duliu_export_test_data",
        annotations={
            "title": "Export test data",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
        },
    )
    async def duliu_export_test_data(
        problem_id: str,
        output_dir: str | None = None,
        format: str = "files",
        include_samples_only: bool = True,
    ) -> str:
        """Export test data (.in/.out or zip) for a problem.

        M1: exports samples from spec_json. M2+ will add generator-produced tests.
        """
        from pathlib import Path

        params = ExportTestDataInput(
            problem_id=problem_id,
            output_dir=Path(output_dir) if output_dir else None,
            format=format,  # type: ignore[arg-type]
            include_samples_only=include_samples_only,
        )
        try:
            problem = await client.get_problem(params.problem_id)
            result = test_exporter.export(
                problem,
                output_dir=params.output_dir,
                as_zip=params.format == "zip",
                samples_only=params.include_samples_only,
            )
            return json.dumps(result, ensure_ascii=False, indent=2)
        except DuliuApiError as exc:
            return json.dumps({"error": str(exc), "problem_id": params.problem_id})

    @mcp.tool(
        name="duliu_export_polygon_package",
        annotations={
            "title": "Export Polygon package",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
        },
    )
    async def duliu_export_polygon_package(
        problem_id: str,
        output_dir: str | None = None,
        language: str = "chinese",
    ) -> str:
        """Export a Polygon-compatible package directory for manual upload to Polygon."""
        from pathlib import Path

        params = ExportPolygonPackageInput(
            problem_id=problem_id,
            output_dir=Path(output_dir) if output_dir else None,
            language=language,  # type: ignore[arg-type]
        )
        try:
            problem = await client.get_problem(params.problem_id)
            artifacts = await client.list_artifacts(params.problem_id)
            result = polygon_exporter.export(
                problem,
                artifacts,
                output_dir=params.output_dir,
                language=params.language,
            )
            return json.dumps(result, ensure_ascii=False, indent=2)
        except DuliuApiError as exc:
            return json.dumps({"error": str(exc), "problem_id": params.problem_id})
