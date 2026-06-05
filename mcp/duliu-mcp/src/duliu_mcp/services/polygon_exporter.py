"""Export services — test data and Polygon-compatible packages.

M2+ can delegate to packages/duliu/polygon/ when that module lands in the main app.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from duliu_mcp.config import settings


class TestDataExporter:
    """Build test files from problem spec_json samples (M1 bootstrap)."""

    def __init__(self, export_root: Path | None = None) -> None:
        self._export_root = export_root or settings.duliu_export_dir

    def export(
        self,
        problem: dict[str, Any],
        *,
        output_dir: Path | None = None,
        as_zip: bool = False,
        samples_only: bool = True,
    ) -> dict[str, Any]:
        problem_id = str(problem["id"])
        target = output_dir or (self._export_root / problem_id / "tests")
        target.mkdir(parents=True, exist_ok=True)

        samples = problem.get("spec_json", {}).get("samples", [])
        if samples_only and not samples:
            return {
                "status": "empty",
                "message": "No samples in spec_json; full test export requires M2+ generator artifacts.",
                "output_dir": str(target),
                "files": [],
            }

        written: list[str] = []
        for idx, sample in enumerate(samples, start=1):
            inp = sample.get("input", "")
            out = sample.get("output", "")
            in_path = target / f"{idx}.in"
            out_path = target / f"{idx}.out"
            in_path.write_text(inp if inp.endswith("\n") else inp + "\n", encoding="utf-8")
            out_path.write_text(out if out.endswith("\n") else out + "\n", encoding="utf-8")
            written.extend([str(in_path), str(out_path)])

        zip_path: str | None = None
        if as_zip:
            zip_path = str(target.parent / "tests.zip")
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for path in written:
                    p = Path(path)
                    zf.write(p, arcname=p.name)

        return {
            "status": "ok",
            "problem_id": problem_id,
            "output_dir": str(target),
            "files": written,
            "zip_path": zip_path,
            "test_count": len(samples),
        }


class PolygonExporter:
    """Scaffold a Polygon-style directory from Duliu artifacts."""

    def __init__(self, export_root: Path | None = None) -> None:
        self._export_root = export_root or settings.duliu_export_dir

    def export(
        self,
        problem: dict[str, Any],
        artifacts: list[dict[str, Any]],
        *,
        output_dir: Path | None = None,
        language: str = "chinese",
    ) -> dict[str, Any]:
        problem_id = str(problem["id"])
        title = problem.get("title", "Untitled")
        target = output_dir or (self._export_root / problem_id / "polygon_package")
        target.mkdir(parents=True, exist_ok=True)

        spec = problem.get("spec_json", {})
        limits = spec.get("limits", {})
        time_ms = limits.get("time_ms", 1000)
        memory_mb = limits.get("memory_mb", 256)

        statements_dir = target / "statements"
        solutions_dir = target / "solutions"
        tests_dir = target / "tests"
        scripts_dir = target / "scripts"
        for d in (statements_dir, solutions_dir, tests_dir, scripts_dir):
            d.mkdir(exist_ok=True)

        artifact_map = {a["kind"]: a for a in artifacts}

        if "statement" in artifact_map:
            stmt = artifact_map["statement"]["content_text"]
            if language in ("chinese", "both"):
                (statements_dir / "chinese.html").write_text(stmt, encoding="utf-8")
            if language in ("english", "both"):
                (statements_dir / "english.html").write_text(stmt, encoding="utf-8")

        if "std" in artifact_map:
            std = artifact_map["std"]
            ext = _lang_to_ext(std.get("language"))
            (solutions_dir / f"standard{ext}").write_text(std["content_text"], encoding="utf-8")

        if "gen" in artifact_map:
            gen = artifact_map["gen"]
            ext = _lang_to_ext(gen.get("language"), default=".py")
            (scripts_dir / f"gen{ext}").write_text(gen["content_text"], encoding="utf-8")

        test_result = TestDataExporter(self._export_root).export(
            problem, output_dir=tests_dir, as_zip=False, samples_only=True
        )

        problem_xml = _render_problem_xml(title=title, time_ms=time_ms, memory_mb=memory_mb)
        (target / "problem.xml").write_text(problem_xml, encoding="utf-8")

        manifest = {
            "problem_id": problem_id,
            "title": title,
            "output_dir": str(target),
            "artifacts_used": list(artifact_map.keys()),
            "tests": test_result,
        }
        (target / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return {
            "status": "ok",
            "problem_id": problem_id,
            "output_dir": str(target),
            "manifest_path": str(target / "manifest.json"),
            "artifacts_used": list(artifact_map.keys()),
            "test_count": test_result.get("test_count", 0),
        }


def _lang_to_ext(language: str | None, default: str = ".cpp") -> str:
    mapping = {
        "cpp": ".cpp",
        "c++": ".cpp",
        "python": ".py",
        "java": ".java",
    }
    if not language:
        return default
    return mapping.get(language.lower(), default)


def _render_problem_xml(*, title: str, time_ms: int, memory_mb: int) -> str:
    time_sec = max(1, time_ms // 1000)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<problem>
  <name>{_xml_escape(title)}</name>
  <time-limit>{time_sec}</time-limit>
  <memory-limit>{memory_mb}</memory-limit>
  <input-file>stdin</input-file>
  <output-file>stdout</output-file>
</problem>
"""


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
