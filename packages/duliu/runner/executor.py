"""Linux subprocess runner. M2: multi-language + SPJ."""

from __future__ import annotations

import os
from pathlib import Path

from duliu.runner.languages import compare_output, compile_source, run_compiled, run_source
from duliu.runner.spj import run_checker
from duliu.runner.types import CompileResult, RunResult, SourceRun


def _work_dir(problem_id: str, job_id: str) -> Path:
    base = Path(os.environ.get("DULIU_RUNNER_WORK_DIR", "/tmp/duliu-runner"))
    d = base / problem_id / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def compile_cpp(source: str, work: Path, name: str = "main") -> CompileResult:
    return compile_source(source, "cpp", work, name=name)


def run_program(
    binary: Path,
    input_data: str,
    time_ms: int,
    max_output_bytes: int,
) -> RunResult:
    from duliu.runner.languages import _run_binary

    return _run_binary(binary, input_data, time_ms, max_output_bytes, "")


def run_cpp_source(
    source: str,
    input_data: str,
    problem_id: str,
    job_id: str,
    time_ms: int,
    max_output_bytes: int,
) -> RunResult:
    sr = run_source(source, "cpp", input_data, problem_id, job_id, time_ms, max_output_bytes)
    return RunResult(
        verdict=sr.verdict,
        exit_code=sr.exit_code,
        time_ms=sr.time_ms,
        stdout=sr.stdout,
        stderr=sr.stderr,
        compile_log=sr.compile_log,
    )


def run_with_expected(
    source: str,
    language: str,
    input_data: str,
    expected_out: str,
    problem_id: str,
    job_id: str,
    time_ms: int,
    max_output_bytes: int,
) -> RunResult:
    sr = run_source(source, language, input_data, problem_id, job_id, time_ms, max_output_bytes)
    if sr.verdict != "OK":
        return RunResult(
            verdict=sr.verdict,
            exit_code=sr.exit_code,
            time_ms=sr.time_ms,
            stdout=sr.stdout,
            stderr=sr.stderr,
            compile_log=sr.compile_log,
        )
    judge = compare_output(sr.stdout, expected_out)
    return RunResult(
        verdict=judge,
        exit_code=sr.exit_code,
        time_ms=sr.time_ms,
        stdout=sr.stdout,
        stderr=sr.stderr,
        compile_log=sr.compile_log,
    )


def run_compare_pair(
    std_source: str,
    brute_source: str,
    std_lang: str,
    brute_lang: str,
    input_data: str,
    problem_id: str,
    job_id: str,
    time_ms: int,
    max_output_bytes: int,
) -> dict:
    std_r = run_source(std_source, std_lang, input_data, problem_id, job_id, time_ms, max_output_bytes, name="std")
    brute_r = run_source(
        brute_source, brute_lang, input_data, problem_id, job_id, time_ms, max_output_bytes, name="brute"
    )
    match = std_r.stdout.encode() == brute_r.stdout.encode() and std_r.verdict == "OK" and brute_r.verdict == "OK"
    return {"match": match, "std": std_r.__dict__, "brute": brute_r.__dict__}


def stress_compare(
    std_source: str,
    brute_source: str,
    inputs: list[str],
    problem_id: str,
    job_id: str,
    time_ms: int,
    max_output_bytes: int,
    *,
    std_language: str = "cpp",
    brute_language: str = "cpp",
    checker_source: str | None = None,
    checker_language: str = "python",
) -> dict:
    work = _work_dir(problem_id, job_id)
    std_comp = compile_source(std_source, std_language, work, "std")
    brute_comp = compile_source(brute_source, brute_language, work, "brute")
    if not std_comp.ok:
        return {"ok": False, "reason": "std_compile_error", "log": std_comp.log}
    if not brute_comp.ok:
        return {"ok": False, "reason": "brute_compile_error", "log": brute_comp.log}

    rounds = 0
    for i, inp in enumerate(inputs):
        rounds += 1
        assert std_comp.binary and brute_comp.binary
        out_std = run_compiled(std_comp, std_language, inp, time_ms, max_output_bytes, work, class_name="std")
        out_brute = run_compiled(brute_comp, brute_language, inp, time_ms, max_output_bytes, work, class_name="brute")
        if out_std.verdict != "OK" or out_brute.verdict != "OK":
            return {
                "ok": False,
                "reason": "runtime_error",
                "round": i,
                "std": out_std.__dict__,
                "brute": out_brute.__dict__,
            }
        if checker_source:
            chk = run_checker(
                checker_source,
                inp,
                out_std.stdout,
                out_brute.stdout,
                language=checker_language,
                time_ms=time_ms,
            )
            if chk.get("verdict") != "AC":
                return {"ok": False, "reason": "spj_wa", "round": i, "checker": chk}
        elif out_std.stdout.encode() != out_brute.stdout.encode():
            return {
                "ok": False,
                "reason": "wa",
                "round": i,
                "input": inp,
                "stdout_std": out_std.stdout,
                "stdout_brute": out_brute.stdout,
            }

    return {"ok": True, "rounds": rounds, "spj": bool(checker_source)}
