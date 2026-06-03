"""Sync problem artifacts between API and .duliu/problems/<id>/ for IDE editing."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ACTIVE_FILE = Path(".duliu/active.json")
WORKSPACE_ROOT = Path(".duliu/problems")

# artifact kind -> filename pattern (language suffix resolved on pull)
KIND_FILES: dict[str, str] = {
    "statement": "statement.md",
    "editorial": "editorial.md",
    "protocol": "protocol.md",
    "checker": "checker.py",
    "interactor": "interactor.py",
    "gen": "gen.py",
    "spec": "spec.yaml",
    "idea": "idea.yaml",
}

LANG_EXT = {"cpp": "cpp", "python": "py", "java": "java", "markdown": "md"}


def _lang_ext(language: str | None, default: str = "cpp") -> str:
    return LANG_EXT.get((language or default).lower(), default)


def _std_filename(kind: str, language: str | None) -> str:
    if kind in ("std", "brute"):
        return f"{kind}.{_lang_ext(language)}"
    return KIND_FILES.get(kind, f"{kind}.txt")


def active_problem_id() -> str | None:
    if not ACTIVE_FILE.is_file():
        return None
    try:
        data = json.loads(ACTIVE_FILE.read_text(encoding="utf-8"))
        return data.get("problem_id")
    except (json.JSONDecodeError, OSError):
        return None


def write_active(problem_id: str, title: str = "") -> Path:
    ACTIVE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_FILE.write_text(
        json.dumps({"problem_id": problem_id, "title": title}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return ACTIVE_FILE


def problem_dir(problem_id: str) -> Path:
    return WORKSPACE_ROOT / problem_id


def pull_tree(problem_id: str, artifacts: list[dict], meta: dict[str, Any]) -> Path:
    root = problem_dir(problem_id)
    root.mkdir(parents=True, exist_ok=True)
    (root / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    samples = (meta.get("spec_json") or {}).get("samples") or []
    if samples:
        samp_dir = root / "samples"
        samp_dir.mkdir(exist_ok=True)
        for i, s in enumerate(samples, start=1):
            if "input" in s:
                (samp_dir / f"{i}.in").write_text(s["input"], encoding="utf-8")
            if "output" in s:
                (samp_dir / f"{i}.out").write_text(s["output"], encoding="utf-8")

    for item in artifacts:
        kind = item.get("kind")
        if not kind:
            continue
        content = item.get("content_text") or ""
        lang = item.get("language")
        if kind in KIND_FILES:
            fname = KIND_FILES[kind]
        elif kind in ("std", "brute"):
            fname = _std_filename(kind, lang)
        else:
            fname = f"{kind}.txt"
        (root / fname).write_text(content, encoding="utf-8")
    return root


def collect_push_payload(root: Path) -> list[tuple[str, str, str | None]]:
    """Returns list of (kind, content, language)."""
    out: list[tuple[str, str, str | None]] = []
    if not root.is_dir():
        return out

    for kind, fname in KIND_FILES.items():
        path = root / fname
        if path.is_file():
            lang = "markdown" if kind in ("statement", "editorial") else None
            out.append((kind, path.read_text(encoding="utf-8"), lang))

    for kind in ("std", "brute"):
        for path in root.glob(f"{kind}.*"):
            if path.suffix.lower() in (".cpp", ".py", ".java", ".txt"):
                ext = path.suffix.lstrip(".").lower()
                lang = "cpp" if ext == "cpp" else ("python" if ext == "py" else ext)
                out.append((kind, path.read_text(encoding="utf-8"), lang))
                break

    for pattern, kind in (
        ("checker.*", "checker"),
        ("interactor.*", "interactor"),
        ("gen.*", "gen"),
    ):
        for path in root.glob(pattern):
            if path.is_file():
                out.append((kind, path.read_text(encoding="utf-8"), "python"))
                break

    return out


def resolve_problem_id(problem_id: str | None) -> str:
    pid = problem_id or active_problem_id()
    if not pid:
        raise SystemExit("未指定 problem_id，且 .duliu/active.json 不存在。先: duliu use <uuid>")
    return pid
