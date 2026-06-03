"""SPJ checker execution (M2): Python checker script with argv [input, user_out, answer]."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


def run_checker(
    checker_source: str,
    input_data: str,
    user_output: str,
    answer_output: str,
    *,
    language: str = "python",
    time_ms: int = 1000,
) -> dict:
    """
    Checker contract (Python):
      sys.argv[1]=input path, sys.argv[2]=user out path, sys.argv[3]=answer path
      exit 0 => AC, non-zero => WA
    """
    with tempfile.TemporaryDirectory(prefix="duliu-spj-") as tmp:
        base = Path(tmp)
        inp = base / "input.txt"
        out = base / "user.out"
        ans = base / "answer.out"
        inp.write_text(input_data, encoding="utf-8")
        out.write_text(user_output, encoding="utf-8")
        ans.write_text(answer_output, encoding="utf-8")

        if language != "python":
            return {"verdict": "CE", "error": "m2_checker_only_python"}

        checker_path = base / "checker.py"
        checker_path.write_text(checker_source, encoding="utf-8")
        try:
            proc = subprocess.run(
                ["python3", str(checker_path), str(inp), str(out), str(ans)],
                capture_output=True,
                text=True,
                timeout=max(time_ms / 1000.0, 0.5),
            )
        except subprocess.TimeoutExpired:
            return {"verdict": "TLE", "checker_log": "checker timeout"}

        log = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode == 0:
            return {"verdict": "AC", "checker_log": log}
        return {"verdict": "WA", "checker_log": log, "exit_code": proc.returncode}
