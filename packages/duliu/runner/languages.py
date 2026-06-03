"""Compile and run C++ / Python / Java sources (M2)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from duliu.runner.types import CompileResult, RunResult, SourceRun


def compile_source(source: str, language: str, work: Path, name: str = "main") -> CompileResult:
    lang = (language or "cpp").lower()
    if lang in ("cpp", "c++"):
        return _compile_cpp(source, work, name)
    if lang == "python":
        return _prepare_python(source, work, name)
    if lang == "java":
        return _compile_java(source, work, name)
    return CompileResult(ok=False, binary=None, log=f"unsupported_language:{lang}")


def _compile_cpp(source: str, work: Path, name: str) -> CompileResult:
    src = work / f"{name}.cpp"
    bin_path = work / name
    src.write_text(source, encoding="utf-8")
    proc = subprocess.run(
        ["g++", str(src), "-O2", "-std=c++17", "-o", str(bin_path)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    log = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return CompileResult(ok=False, binary=None, log=log)
    return CompileResult(ok=True, binary=bin_path, log=log)


def _prepare_python(source: str, work: Path, name: str) -> CompileResult:
    src = work / f"{name}.py"
    src.write_text(source, encoding="utf-8")
    return CompileResult(ok=True, binary=src, log="")


def _compile_java(source: str, work: Path, name: str) -> CompileResult:
    class_name = "Main"
    if "public class " in source:
        for line in source.splitlines():
            if "public class " in line:
                class_name = line.split("public class ")[1].split()[0].strip("{")
                break
    else:
        source = f"public class {class_name} {{\n{source}\n}}\n"
    src = work / f"{class_name}.java"
    src.write_text(source, encoding="utf-8")
    proc = subprocess.run(
        ["javac", str(src)],
        capture_output=True,
        text=True,
        timeout=90,
        cwd=str(work),
    )
    log = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return CompileResult(ok=False, binary=None, log=log)
    return CompileResult(ok=True, binary=work / f"{class_name}.class", log=log)


def run_compiled(
    comp: CompileResult,
    language: str,
    input_data: str,
    time_ms: int,
    max_output_bytes: int,
    work: Path,
    class_name: str = "Main",
) -> RunResult:
    lang = (language or "cpp").lower()
    if not comp.ok or not comp.binary:
        return RunResult(verdict="CE", exit_code=-1, time_ms=0, stdout="", stderr="", compile_log=comp.log)

    if lang in ("cpp", "c++"):
        return _run_binary(
            comp.binary, input_data, time_ms, max_output_bytes, comp.log, work_dir=work
        )

    if lang == "python":
        from duliu.runner.sandbox import run_program_argv

        return run_program_argv(
            [comp.binary.name],
            work,
            input_data,
            time_ms,
            max_output_bytes,
            compile_log=comp.log,
            runtime="python",
        )

    if lang == "java":
        from duliu.runner.sandbox import run_program_argv

        return run_program_argv(
            ["java", "-cp", str(work), class_name],
            work,
            input_data,
            time_ms,
            max_output_bytes,
            compile_log=comp.log,
            runtime="java",
        )

    return RunResult(verdict="CE", exit_code=-1, time_ms=0, stdout="", stderr="", compile_log="bad_lang")


def _run_binary(
    binary: Path,
    input_data: str,
    time_ms: int,
    max_output_bytes: int,
    compile_log: str,
    *,
    work_dir: Path | None = None,
) -> RunResult:
    from duliu.runner.sandbox import run_program_argv

    wd = work_dir or binary.parent
    return run_program_argv(
        [binary.name],
        wd,
        input_data,
        time_ms,
        max_output_bytes,
        compile_log=compile_log,
        prefer_isolate=True,
    )


def _result_from_proc(proc: subprocess.CompletedProcess[str], max_output_bytes: int, compile_log: str) -> RunResult:
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


def run_source(
    source: str,
    language: str,
    input_data: str,
    problem_id: str,
    job_id: str,
    time_ms: int,
    max_output_bytes: int,
    *,
    name: str = "main",
) -> SourceRun:
    from duliu.runner.executor import _work_dir

    work = _work_dir(problem_id, job_id)
    comp = compile_source(source, language, work, name=name)
    java_class = comp.binary.stem if comp.binary and language == "java" else "Main"
    result = run_compiled(comp, language, input_data, time_ms, max_output_bytes, work, class_name=java_class)
    return SourceRun(
        verdict=result.verdict,
        exit_code=result.exit_code,
        time_ms=result.time_ms,
        stdout=result.stdout,
        stderr=result.stderr,
        compile_log=result.compile_log,
        language=language,
    )


def compare_output(user_out: str, expected: str) -> str:
    if user_out.encode() == expected.encode():
        return "AC"
    return "WA"
