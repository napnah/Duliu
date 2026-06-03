"""M21 Import Polygon-compatible zip into Duliu artifacts."""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from duliu.db.models import Problem
from duliu.facade.artifact_save import save_artifact_text
from duliu.facade.events import emit_event


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", "", html)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _lang_from_name(name: str) -> str | None:
    low = name.lower()
    if low.endswith(".cpp") or low.endswith(".cc"):
        return "cpp"
    if low.endswith(".py"):
        return "python"
    if low.endswith(".java"):
        return "java"
    return None


async def import_polygon_zip(
    session: AsyncSession,
    problem: Problem,
    zip_path: str | Path,
) -> dict:
    """Extract zip and import known paths into artifacts + samples."""
    path = Path(zip_path)
    if not path.is_file():
        return {"ok": False, "reason": "zip_not_found", "path": str(path)}

    imported: list[str] = []
    samples_added = 0
    spec = dict(problem.spec_json or {})
    samples = list(spec.get("samples") or [])

    with zipfile.ZipFile(path, "r") as zf:
        names = zf.namelist()
        for name in names:
            if name.endswith("/"):
                continue
            try:
                data = zf.read(name)
            except Exception as exc:
                continue
            text = data.decode("utf-8", errors="replace")
            base = name.lower()

            if base.startswith("solutions/") and "standard" in Path(name).stem.lower():
                lang = _lang_from_name(name) or "cpp"
                await save_artifact_text(
                    session, problem, "std", text, author="polygon_import", language=lang
                )
                imported.append(name)
            elif base.startswith("solutions/") and "brute" in Path(name).stem.lower():
                lang = _lang_from_name(name) or "cpp"
                await save_artifact_text(
                    session, problem, "brute", text, author="polygon_import", language=lang
                )
                imported.append(name)
            elif base.startswith("statements/") and (base.endswith(".html") or base.endswith(".md")):
                content = _strip_html(text) if base.endswith(".html") else text
                await save_artifact_text(
                    session, problem, "statement", content, author="polygon_import", language="markdown"
                )
                imported.append(name)
            elif base.endswith("scripts/gen.py") or base.endswith("/gen.py"):
                await save_artifact_text(
                    session, problem, "gen", text, author="polygon_import", language="python"
                )
                imported.append(name)
            elif "checker" in base and ("scripts/" in base or base.endswith(".py") or base.endswith(".cpp")):
                lang = _lang_from_name(name) or "python"
                await save_artifact_text(
                    session, problem, "checker", text, author="polygon_import", language=lang
                )
                imported.append(name)
            elif "interactor" in base and "scripts/" in base:
                lang = _lang_from_name(name) or "cpp"
                await save_artifact_text(
                    session, problem, "interactor", text, author="polygon_import", language=lang
                )
                imported.append(name)
            elif base.startswith("protocols/"):
                await save_artifact_text(
                    session, problem, "protocol", text, author="polygon_import", language="markdown"
                )
                imported.append(name)

        test_ins = {}
        for name in names:
            m = re.match(r"tests/(\d+)\.in$", name, re.I)
            if m:
                test_ins[m.group(1)] = zf.read(name).decode("utf-8", errors="replace")
        for name in names:
            m = re.match(r"tests/(\d+)\.out$", name, re.I)
            if not m:
                continue
            idx = m.group(1)
            if idx not in test_ins:
                continue
            inp, out = test_ins[idx], zf.read(name).decode("utf-8", errors="replace")
            if any(s.get("input") == inp and s.get("output") == out for s in samples):
                continue
            samples.append({"input": inp, "output": out, "note": f"polygon_import test {idx}"})
            samples_added += 1
            imported.append(f"tests/{idx}")

    spec["samples"] = samples
    spec["polygon_import"] = {
        "zip_path": str(path),
        "files": imported,
        "samples_added": samples_added,
    }
    problem.spec_json = spec

    await emit_event(
        session,
        problem_id=problem.id,
        type="polygon.import.done",
        message=f"Imported {len(imported)} paths from zip",
        source="polygon",
        payload={"imported": len(imported), "samples_added": samples_added},
    )
    await session.flush()
    return {
        "ok": True,
        "zip_path": str(path),
        "imported_count": len(imported),
        "imported_files": imported[:50],
        "samples_added": samples_added,
    }
