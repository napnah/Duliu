"""Build Polygon-compatible package (zip) from problem artifacts."""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from duliu.db.models import Artifact, Problem


def _render_problem_xml(problem: Problem) -> str:
    spec = problem.spec_json or {}
    limits = spec.get("limits", {})
    time_ms = limits.get("time_ms", 1000)
    memory_mb = limits.get("memory_mb", 256)
    inp = spec.get("input_file", "stdin")
    out = spec.get("output_file", "stdout")
    return f"""<?xml version="1.0" encoding="utf-8"?>
<problem>
  <name>{escape(problem.title)}</name>
  <time_limit>{time_ms / 1000.0:.3f}</time_limit>
  <memory_limit>{memory_mb}</memory_limit>
  <input_file>{escape(inp)}</input_file>
  <output_file>{escape(out)}</output_file>
  <contest_style>{escape(problem.contest_style)}</contest_style>
  <problem_type>{escape(problem.problem_type)}</problem_type>
</problem>
"""


def _artifact_map(artifacts: list[Artifact]) -> dict[str, Artifact]:
    latest: dict[str, Artifact] = {}
    for a in artifacts:
        if a.kind not in latest or a.version > latest[a.kind].version:
            latest[a.kind] = a
    return latest


def build_polygon_zip(problem: Problem, artifacts: list[Artifact]) -> bytes:
    kinds = _artifact_map(artifacts)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("problem.xml", _render_problem_xml(problem))
        if stmt := kinds.get("statement"):
            html = f"<html><body><pre>{escape(stmt.content_text)}</pre></body></html>"
            zf.writestr("statements/english.html", html)
            zf.writestr("statements/chinese.html", html)
        if std := kinds.get("std"):
            ext = {"cpp": ".cpp", "python": ".py", "java": ".java"}.get(std.language or "cpp", ".cpp")
            zf.writestr(f"solutions/standard{ext}", std.content_text)
        if brute := kinds.get("brute"):
            ext = {"cpp": ".cpp", "python": ".py", "java": ".java"}.get(brute.language or "cpp", ".cpp")
            zf.writestr(f"solutions/brute{ext}", brute.content_text)
        if chk := kinds.get("checker"):
            zf.writestr("scripts/checker.py", chk.content_text)
        if inter := kinds.get("interactor"):
            zf.writestr("scripts/interactor.py", inter.content_text)
        if gen := kinds.get("gen"):
            zf.writestr("scripts/gen.py", gen.content_text)
        if proto := kinds.get("protocol"):
            zf.writestr("protocols/comm.md", proto.content_text)
        samples = problem.spec_json.get("samples") or []
        for i, s in enumerate(samples, start=1):
            if "input" in s:
                zf.writestr(f"tests/{i}.in", s["input"])
            if "output" in s:
                zf.writestr(f"tests/{i}.out", s["output"])
        manifest = {
            "problem_id": str(problem.id),
            "title": problem.title,
            "files": zf.namelist(),
            "problem_type": problem.problem_type,
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    return buf.getvalue()


def export_polygon_to_dir(problem: Problem, artifacts: list[Artifact], out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_bytes = build_polygon_zip(problem, artifacts)
    zip_path = out_dir / f"{_safe_name(problem.title)}.zip"
    zip_path.write_bytes(zip_bytes)
    kinds = _artifact_map(artifacts)
    missing = []
    if problem.problem_type in ("INTERACTIVE", "COMMUNICATION") and "interactor" not in kinds:
        missing.append("interactor")
    if problem.problem_type == "COMMUNICATION" and "protocol" not in kinds:
        missing.append("protocol")
    if problem.problem_type == "SUBMIT_ANSWER" and "checker" not in kinds:
        missing.append("checker")
    if "statement" not in kinds:
        missing.append("statement")
    if "std" not in kinds:
        missing.append("std")
    return {
        "ok": len(missing) == 0,
        "zip_path": str(zip_path),
        "zip_size": len(zip_bytes),
        "missing": missing,
        "file_count": len(zipfile.ZipFile(io.BytesIO(zip_bytes)).namelist()),
    }


def _safe_name(title: str) -> str:
    return re.sub(r"[^\w\-]+", "_", title).strip("_") or "problem"
