"""Load ICPC/OI workflow YAML from docs/."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

DOCS = Path(os.environ.get("DULIU_DOCS_DIR", str(Path(__file__).resolve().parents[3] / "docs")))


@lru_cache
def load_workflow(contest_style: str) -> dict:
    name = "workflow_icpc.yaml" if contest_style.upper() == "ICPC" else "workflow_oi.yaml"
    path = DOCS / name
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def contest_defaults(contest_style: str) -> dict:
    wf = load_workflow(contest_style)
    return wf.get("contest_defaults", {})
