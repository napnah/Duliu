"""M9/M11 execution sandbox: subprocess (default) or isolate for compiled binaries."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import time
from pathlib import Path

from duliu.config import settings
from duliu.runner.types import RunResult


def isolate_available() -> bool:
    return shutil.which("isolate") is not None


def sandbox_mode() -> str:
    if settings.use_isolate and isolate_available():
        return "isolate"
    return "subprocess"


def box_id_for(work_dir: Path, suffix: str = "") -> int:
    """Stable box id 1..899 from work path."""
    h = hashlib.sha256(f"{work_dir}{suffix}".encode()).hexdigest()
    return int(h[:6], 16) % 899 + 1


def _init_isolate_box(box_id: int) -> None:
    subprocess.run(
        ["isolate", "--box-id", str(box_id), "--init"],
        capture_output=True,
        timeout=10,
    )


def _isolate_dir_flags(shares: list[tuple[str, str, str]] | None) -> list[str]:
    flags: list[str] = []
    for host, box, mode in shares or []:
        flags.extend(["-d", f"{host}:{box}:{mode}"])
    return flags


def _default_python_shares() -> list[tuple[str, str, str]]:
    shares: list[tuple[str, str, str]] = []
    py = shutil.which("python3") or "/usr/bin/python3"
    py_path = Path(py)
    if py_path.is_file():
        shares.append((str(py_path.parent), str(py_path.parent), "maybe"))
    for lib in ("/usr/lib", "/lib", "/lib64"):
        if Path(lib).is_dir():
            shares.append((lib, lib, "maybe"))
    return shares


def _default_java_shares() -> list[tuple[str, str, str]]:
    shares: list[tuple[str, str, str]] = []
    java = shutil.which("java")
    if java:
        shares.append((str(Path(java).parent), str(Path(java).parent), "maybe"))
    jhome = os.environ.get("JAVA_HOME")
    if jhome and Path(jhome).is_dir():
        shares.append((jhome, jhome, "maybe"))
    for lib in ("/usr/lib/jvm", "/usr/lib"):
        if Path(lib).is_dir():
            shares.append((lib, lib, "maybe"))
    return shares


def run_isolated(
    argv: list[str],
    work_dir: Path,
    input_data: str,
    time_ms: int,
    max_output_bytes: int,
    *,
    box_id: int | None = None,
    compile_log: str = "",
    shares: list[tuple[str, str, str]] | None = None,
) -> RunResult:
    """Run argv[0] under /box (paths relative to work_dir unless absolute /box/...)."""
    work_dir.mkdir(parents=True, exist_ok=True)
    bid = box_id if box_id is not None else box_id_for(work_dir)
    _init_isolate_box(bid)

    in_path = work_dir / "input.txt"
    out_path = work_dir / "stdout.txt"
    err_path = work_dir / "stderr.txt"
    meta_path = work_dir / "isolate.meta"
    in_path.write_text(input_data, encoding="utf-8")
    for p in (out_path, err_path, meta_path):
        if p.exists():
            p.unlink()

    time_sec = max(0.1, time_ms / 1000.0)
    mem_kb = 262144
    box_argv = []
    for arg in argv:
        if arg.startswith("/box/"):
            box_argv.append(arg)
        elif arg.startswith("/"):
            box_argv.append(arg)
        else:
            box_argv.append(f"/box/{arg}")

    cmd = [
        "isolate",
        "--box-id",
        str(bid),
        "--dir",
        f"/box={work_dir}",
        *_isolate_dir_flags(shares),
        "-t",
        str(time_sec),
        "-w",
        str(time_sec + 1),
        "-M",
        str(mem_kb),
        "-i",
        str(in_path),
        "-o",
        str(out_path),
        "-e",
        str(err_path),
        "--meta",
        str(meta_path),
        "--run",
        "--",
        *box_argv,
    ]
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=time_sec + 10)
    except subprocess.TimeoutExpired:
        return RunResult(
            verdict="TLE",
            exit_code=-1,
            time_ms=time_ms,
            stdout="",
            stderr="isolate wall timeout",
            compile_log=compile_log,
        )

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    stdout = out_path.read_text(encoding="utf-8", errors="replace") if out_path.exists() else ""
    stderr = err_path.read_text(encoding="utf-8", errors="replace") if err_path.exists() else ""
    if proc.stderr:
        stderr = (stderr + "\n" + proc.stderr).strip()

    status = ""
    if meta_path.exists():
        for line in meta_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("status:"):
                status = line.split(":", 1)[1].strip().upper()
                break

    if len(stdout.encode()) > max_output_bytes:
        stdout = stdout.encode()[:max_output_bytes].decode(errors="replace")
        return RunResult(
            verdict="OLE",
            exit_code=proc.returncode,
            time_ms=elapsed_ms,
            stdout=stdout,
            stderr=stderr,
            compile_log=compile_log,
        )
    if status == "TO" or status == "TG":
        return RunResult(verdict="TLE", exit_code=-1, time_ms=elapsed_ms, stdout=stdout, stderr=stderr, compile_log=compile_log)
    if status == "SG":
        return RunResult(verdict="OLE", exit_code=-1, time_ms=elapsed_ms, stdout=stdout, stderr=stderr, compile_log=compile_log)
    if status == "RE" or proc.returncode != 0:
        return RunResult(
            verdict="RTE",
            exit_code=proc.returncode,
            time_ms=elapsed_ms,
            stdout=stdout,
            stderr=stderr,
            compile_log=compile_log,
        )
    return RunResult(
        verdict="OK",
        exit_code=0,
        time_ms=elapsed_ms,
        stdout=stdout,
        stderr=stderr,
        compile_log=compile_log,
    )


def run_subprocess(
    argv: list[str],
    input_data: str,
    time_ms: int,
    max_output_bytes: int,
    *,
    cwd: Path | None = None,
    compile_log: str = "",
) -> RunResult:
    try:
        proc = subprocess.run(
            argv,
            input=input_data,
            capture_output=True,
            text=True,
            timeout=max(time_ms / 1000.0, 0.1),
            cwd=str(cwd) if cwd else None,
        )
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") if isinstance(e.stdout, str) else (e.stdout or b"").decode(errors="replace")
        err = (e.stderr or "") if isinstance(e.stderr, str) else (e.stderr or b"").decode(errors="replace")
        return RunResult(verdict="TLE", exit_code=-1, time_ms=time_ms, stdout=out[:max_output_bytes], stderr=err, compile_log=compile_log)
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    if len(stdout.encode()) > max_output_bytes:
        stdout = stdout.encode()[:max_output_bytes].decode(errors="replace")
        verdict = "OLE"
    elif proc.returncode != 0:
        verdict = "RTE"
    else:
        verdict = "OK"
    return RunResult(
        verdict=verdict,
        exit_code=proc.returncode,
        time_ms=0,
        stdout=stdout,
        stderr=stderr,
        compile_log=compile_log,
    )


def run_program_argv(
    argv: list[str],
    work_dir: Path,
    input_data: str,
    time_ms: int,
    max_output_bytes: int,
    *,
    compile_log: str = "",
    prefer_isolate: bool = True,
    runtime: str = "binary",
) -> RunResult:
    """Dispatch to isolate or subprocess. runtime: binary | python | java."""
    use_iso = prefer_isolate and sandbox_mode() == "isolate"
    if use_iso and work_dir and argv:
        if runtime == "binary" and not Path(argv[0]).is_absolute():
            return run_isolated(argv, work_dir, input_data, time_ms, max_output_bytes, compile_log=compile_log)
        if runtime == "python":
            py = shutil.which("python3") or "/usr/bin/python3"
            script = argv[0] if not Path(argv[0]).is_absolute() else Path(argv[0]).name
            return run_isolated(
                [py, script],
                work_dir,
                input_data,
                time_ms,
                max_output_bytes,
                compile_log=compile_log,
                shares=_default_python_shares(),
            )
        if runtime == "java":
            java = shutil.which("java") or "java"
            cls = argv[-1] if len(argv) >= 1 else "Main"
            return run_isolated(
                [java, "-cp", "/box", cls],
                work_dir,
                input_data,
                time_ms,
                max_output_bytes,
                compile_log=compile_log,
                shares=_default_java_shares(),
            )
    abs_argv = [str(work_dir / argv[0]) if work_dir and not Path(argv[0]).is_absolute() else argv[0], *argv[1:]]
    return run_subprocess(abs_argv, input_data, time_ms, max_output_bytes, cwd=work_dir, compile_log=compile_log)


def isolate_supports_interpreters() -> bool:
    return isolate_available()
