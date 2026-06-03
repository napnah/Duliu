from dataclasses import dataclass
from pathlib import Path


@dataclass
class CompileResult:
    ok: bool
    binary: Path | None
    log: str


@dataclass
class RunResult:
    verdict: str
    exit_code: int
    time_ms: int
    stdout: str
    stderr: str
    compile_log: str = ""


@dataclass
class SourceRun:
    verdict: str
    exit_code: int
    time_ms: int
    stdout: str
    stderr: str
    compile_log: str = ""
    language: str = "cpp"
