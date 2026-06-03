"""M3: interactive / communication runs via Python interactor driving compiled solution."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from duliu.runner.languages import compile_source


def run_interactive(
    std_source: str,
    std_language: str,
    interactor_source: str,
    problem_id: str,
    job_id: str,
    time_ms: int,
) -> dict:
    """
    Interactor contract (Python):
      - Env DULIU_SOLUTION_BIN: path to compiled solution
      - Exit 0 => AC, non-zero => WA/RTE
      - May print verdict line to stdout
    """
    from duliu.runner.executor import _work_dir

    work = _work_dir(problem_id, job_id)
    comp = compile_source(std_source, std_language, work, name="main")
    if not comp.ok or not comp.binary:
        return {"verdict": "CE", "compile_log": comp.log}

    inter_path = work / "interactor.py"
    inter_path.write_text(interactor_source, encoding="utf-8")
    env = {**os.environ, "DULIU_SOLUTION_BIN": str(comp.binary)}
    try:
        proc = subprocess.run(
            ["python3", str(inter_path)],
            capture_output=True,
            text=True,
            timeout=max(time_ms / 1000.0, 1.0),
            cwd=str(work),
            env=env,
        )
    except subprocess.TimeoutExpired:
        return {"verdict": "TLE", "stdout": "", "stderr": "interactor timeout"}

    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode == 0:
        verdict = "AC"
        if "WA" in out.upper():
            verdict = "WA"
        return {"verdict": verdict, "stdout": proc.stdout or "", "stderr": proc.stderr or "", "exit_code": 0}
    return {
        "verdict": "WA" if "WA" in (proc.stdout or "").upper() else "RTE",
        "stdout": proc.stdout or "",
        "stderr": proc.stderr or "",
        "exit_code": proc.returncode,
    }
