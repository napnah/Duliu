"""M9 execution sandbox: subprocess (default) or isolate when available."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from duliu.config import settings


def isolate_available() -> bool:
    return shutil.which("isolate") is not None


def sandbox_mode() -> str:
    if settings.use_isolate and isolate_available():
        return "isolate"
    return "subprocess"


def run_isolated(
    command: list[str],
    work_dir: Path,
    input_data: str,
    time_ms: int,
    max_output_bytes: int,
    *,
    box_id: int = 0,
) -> tuple[str, str, int, str]:
    """Run command in isolate box; returns stdout, stderr, exit_code, verdict_hint."""
    work_dir.mkdir(parents=True, exist_ok=True)
    in_path = work_dir / "input.txt"
    out_path = work_dir / "stdout.txt"
    err_path = work_dir / "stderr.txt"
    in_path.write_text(input_data, encoding="utf-8")
    meta = work_dir / "meta"
    if meta.exists():
        meta.unlink()
    time_sec = max(1, (time_ms + 999) // 1000)
    cmd = [
        "isolate",
        "--box-id",
        str(box_id),
        "--dir",
        f"/box={work_dir}",
        "--time",
        str(time_sec),
        "--mem",
        "256000",
        "--processes",
        "32",
        "--run",
        "--",
        *command,
    ]
    env = os.environ.copy()
    env["ISOLATE_INPUT"] = str(in_path)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=time_sec + 5,
            cwd=str(work_dir),
            env=env,
        )
    except subprocess.TimeoutExpired:
        return "", "isolate timeout", -1, "TLE"
    stdout = out_path.read_text(encoding="utf-8", errors="replace") if out_path.exists() else ""
    stderr = (proc.stderr or "") + (
        err_path.read_text(encoding="utf-8", errors="replace") if err_path.exists() else ""
    )
    if len(stdout.encode()) > max_output_bytes:
        stdout = stdout[:max_output_bytes]
        return stdout, stderr, proc.returncode, "OLE"
    if proc.returncode != 0:
        return stdout, stderr, proc.returncode, "RTE"
    return stdout, stderr, 0, "OK"
