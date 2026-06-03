import random
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from duliu.config import settings
from duliu.db.models import Artifact, JobKind, JobStatus, Problem, RunnerJob
from duliu.facade.events import emit_event
from duliu.facade.jobs import JobFacade
from duliu.runner.executor import (
    run_compare_pair,
    run_cpp_source,
    run_source,
    run_with_expected,
    stress_compare,
)
from duliu.runner.languages import compile_source
from duliu.runner.interactive import run_interactive
from duliu.runner.spj import run_checker
from duliu.polygon.export import export_polygon_to_dir
from duliu.crawler.import_problem import crawl_and_import


async def _resolve_source(
    session: AsyncSession,
    problem_id: uuid.UUID,
    program: str,
    payload: dict,
) -> tuple[str | None, str]:
    draft = payload.get("draft") or payload.get("draft_std")
    if draft and draft.get("source"):
        lang = draft.get("language") or payload.get("language") or "cpp"
        return draft["source"], lang
    version = payload.get("artifact_version")
    kind_map = {
        "std": "std",
        "brute": "brute",
        "checker": "checker",
        "interactor": "interactor",
    }
    kind = kind_map.get(program, "std")
    art = await JobFacade.latest_artifact(session, problem_id, kind, version)
    if not art:
        return None, "cpp"
    return art.content_text, art.language or payload.get("language") or ("python" if kind in ("checker", "interactor") else "cpp")


async def handle_run_single(session: AsyncSession, job: RunnerJob, problem: Problem) -> None:
    payload = job.payload_json
    program = payload.get("program", "std")
    input_data = payload.get("input", "")
    if len(input_data.encode()) > settings.max_input_bytes:
        job.status = JobStatus.FAILED.value
        job.result_json = {"error": "input_too_large"}
        return

    if program == "checker":
        checker_art = await JobFacade.latest_artifact(session, problem.id, "checker")
        if not checker_art:
            job.status = JobStatus.FAILED.value
            job.result_json = {"error": "checker_required"}
            return
        std_art = await JobFacade.latest_artifact(session, problem.id, "std")
        if not std_art:
            job.status = JobStatus.FAILED.value
            job.result_json = {"error": "std_required_for_checker"}
            return
        limits = problem.spec_json.get("limits", {})
        time_ms = int(limits.get("time_ms", 1000))
        sr = run_source(
            std_art.content_text,
            std_art.language or "cpp",
            input_data,
            str(problem.id),
            str(job.id),
            time_ms,
            settings.max_output_bytes,
        )
        if sr.verdict != "OK":
            job.status = JobStatus.DONE.value
            job.result_json = {**sr.__dict__, "verdict": sr.verdict}
            return
        expected = payload.get("expected_out") or ""
        if not expected:
            samples = problem.spec_json.get("samples") or []
            if samples:
                expected = samples[0].get("output", "")
        chk = run_checker(
            checker_art.content_text,
            input_data,
            sr.stdout,
            expected,
            language=checker_art.language or "python",
            time_ms=time_ms,
        )
        job.status = JobStatus.DONE.value
        job.result_json = {"verdict": chk.get("verdict", "WA"), "stdout": sr.stdout, "checker": chk, "program": "checker"}
        return

    source, language = await _resolve_source(session, problem.id, program, payload)
    if not source:
        job.status = JobStatus.FAILED.value
        job.result_json = {"error": f"missing_source_for_{program}"}
        return

    limits = problem.spec_json.get("limits", {})
    time_ms = int(limits.get("time_ms", 1000))

    expected = payload.get("expected_out")
    use_checker = payload.get("use_checker") and problem.problem_type == "SUBMIT_ANSWER"

    if use_checker:
        checker_art = await JobFacade.latest_artifact(session, problem.id, "checker")
        if not checker_art:
            job.status = JobStatus.FAILED.value
            job.result_json = {"error": "checker_required"}
            return
        run_r = run_source(
            source, language, input_data, str(problem.id), str(job.id), time_ms, settings.max_output_bytes
        )
        if run_r.verdict != "OK":
            job.result_json = {**run_r.__dict__, "language": language}
            job.status = JobStatus.DONE.value
            return
        answer = expected or ""
        if not answer:
            samples = problem.spec_json.get("samples") or []
            if samples:
                answer = samples[0].get("output", "")
        chk = run_checker(
            checker_art.content_text,
            input_data,
            run_r.stdout,
            answer,
            language=checker_art.language or "python",
            time_ms=time_ms,
        )
        job.status = JobStatus.DONE.value
        job.result_json = {
            "verdict": chk.get("verdict", "WA"),
            "stdout": run_r.stdout,
            "stderr": run_r.stderr,
            "compile_log": run_r.compile_log,
            "checker": chk,
            "language": language,
        }
    elif expected is not None:
        result = run_with_expected(
            source,
            language,
            input_data,
            expected,
            str(problem.id),
            str(job.id),
            time_ms,
            settings.max_output_bytes,
        )
        job.status = JobStatus.DONE.value
        job.result_json = {
            "verdict": result.verdict,
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "compile_log": result.compile_log,
            "language": language,
        }
    else:
        if language == "cpp" and not payload.get("draft"):
            result = run_cpp_source(
                source, input_data, str(problem.id), str(job.id), time_ms, settings.max_output_bytes
            )
        else:
            sr = run_source(
                source, language, input_data, str(problem.id), str(job.id), time_ms, settings.max_output_bytes
            )
            result = sr
        job.status = JobStatus.DONE.value
        job.result_json = {
            "verdict": result.verdict,
            "exit_code": result.exit_code,
            "time_ms": getattr(result, "time_ms", 0),
            "stdout": result.stdout,
            "stderr": result.stderr,
            "compile_log": getattr(result, "compile_log", ""),
            "language": language,
        }

    job.log_text = (job.result_json or {}).get("compile_log", "") + "\n" + (job.result_json or {}).get("stderr", "")
    await emit_event(
        session,
        problem_id=problem.id,
        type="runner.run_single.done",
        message=f"run_single {program}: {(job.result_json or {}).get('verdict')}",
        source="runner",
        job_id=job.id,
        payload={"verdict": (job.result_json or {}).get("verdict")},
    )


async def handle_compile(session: AsyncSession, job: RunnerJob, problem: Problem) -> None:
    payload = job.payload_json
    program = payload.get("program", "std")
    source, language = await _resolve_source(session, problem.id, program, payload)
    if not source:
        job.status = JobStatus.FAILED.value
        job.result_json = {"error": f"missing_source_for_{program}"}
        return
    from duliu.runner.executor import _work_dir

    work = _work_dir(str(problem.id), str(job.id))
    comp = compile_source(source, language, work, name=program)
    job.status = JobStatus.DONE.value
    job.result_json = {
        "ok": comp.ok,
        "verdict": "OK" if comp.ok else "CE",
        "compile_log": comp.log,
        "language": language,
    }
    job.log_text = comp.log


async def handle_run_compare(session: AsyncSession, job: RunnerJob, problem: Problem) -> None:
    std_art = await JobFacade.latest_artifact(session, problem.id, "std")
    brute_art = await JobFacade.latest_artifact(session, problem.id, "brute")
    if not std_art or not brute_art:
        job.status = JobStatus.FAILED.value
        job.result_json = {"error": "std_and_brute_required"}
        return
    input_data = job.payload_json.get("input", "")
    limits = problem.spec_json.get("limits", {})
    time_ms = int(limits.get("time_ms", 1000))
    report = run_compare_pair(
        std_art.content_text,
        brute_art.content_text,
        std_art.language or "cpp",
        brute_art.language or "cpp",
        input_data,
        str(problem.id),
        str(job.id),
        time_ms,
        settings.max_output_bytes,
    )
    job.status = JobStatus.DONE.value
    job.result_json = report
    job.log_text = str(report)


async def handle_stress(session: AsyncSession, job: RunnerJob, problem: Problem) -> None:
    std_art = await JobFacade.latest_artifact(session, problem.id, "std")
    brute_art = await JobFacade.latest_artifact(session, problem.id, "brute")
    if not std_art or not brute_art:
        job.status = JobStatus.FAILED.value
        job.result_json = {"error": "std_and_brute_required"}
        return

    samples = problem.spec_json.get("samples", [])
    inputs = [s["input"] for s in samples if "input" in s]
    mode = job.payload_json.get("mode", "quick")
    if mode == "import_check":
        target = 200
    elif mode == "quick":
        target = 50
    else:
        target = 500
    while len(inputs) < target:
        inputs.append(f"{random.randint(-1000, 1000)} {random.randint(-1000, 1000)}\n")

    limits = problem.spec_json.get("limits", {})
    time_ms = int(limits.get("time_ms", 1000))
    checker_art = await JobFacade.latest_artifact(session, problem.id, "checker")
    report = stress_compare(
        std_art.content_text,
        brute_art.content_text,
        inputs[:target],
        str(problem.id),
        str(job.id),
        time_ms,
        settings.max_output_bytes,
        std_language=std_art.language or "cpp",
        brute_language=brute_art.language or "cpp",
        checker_source=checker_art.content_text if checker_art else None,
        checker_language=checker_art.language or "python" if checker_art else "python",
    )
    job.status = JobStatus.DONE.value
    job.result_json = report
    job.log_text = str(report)
    stage = "IMPORT" if mode == "import_check" else "STRESS"
    await emit_event(
        session,
        problem_id=problem.id,
        type="runner.stress.done",
        message="stress OK" if report.get("ok") else f"stress fail: {report.get('reason')}",
        source="runner",
        job_id=job.id,
        stage_id=stage,
        level="INFO" if report.get("ok") else "WARN",
        payload=report,
    )
    if mode == "import_check":
        from duliu.facade.import_flow import record_import_check_result

        await record_import_check_result(session, problem, report)


async def handle_interactive(session: AsyncSession, job: RunnerJob, problem: Problem) -> None:
    if problem.problem_type not in ("INTERACTIVE", "COMMUNICATION"):
        job.status = JobStatus.FAILED.value
        job.result_json = {"error": "problem_type_not_interactive"}
        return
    inter = await JobFacade.latest_artifact(session, problem.id, "interactor")
    if not inter:
        job.status = JobStatus.FAILED.value
        job.result_json = {"error": "interactor_required"}
        return
    draft = job.payload_json.get("draft_std")
    if draft and draft.get("source"):
        std_source, std_lang = draft["source"], draft.get("language", "cpp")
    else:
        std_art = await JobFacade.latest_artifact(session, problem.id, "std")
        if not std_art:
            job.status = JobStatus.FAILED.value
            job.result_json = {"error": "std_required"}
            return
        std_source, std_lang = std_art.content_text, std_art.language or "cpp"
    limits = problem.spec_json.get("limits", {})
    time_ms = int(limits.get("time_ms", 2000))
    report = run_interactive(
        std_source, std_lang, inter.content_text, str(problem.id), str(job.id), time_ms
    )
    job.status = JobStatus.DONE.value
    job.result_json = report
    job.log_text = str(report)
    await emit_event(
        session,
        problem_id=problem.id,
        type="runner.interactive.done",
        message=f"interactive: {report.get('verdict')}",
        source="runner",
        job_id=job.id,
        payload=report,
    )


async def handle_polygon_export(session: AsyncSession, job: RunnerJob, problem: Problem) -> None:
    import os
    from pathlib import Path

    from sqlalchemy import select

    from duliu.db.models import Artifact

    artifacts = (
        await session.execute(select(Artifact).where(Artifact.problem_id == problem.id))
    ).scalars().all()
    base = Path(os.environ.get("DULIU_PACKAGE_DIR", "/tmp/duliu-packages"))
    report = export_polygon_to_dir(problem, list(artifacts), base / str(problem.id))
    job.status = JobStatus.DONE.value
    job.result_json = report
    job.log_text = report.get("zip_path", "")
    await emit_event(
        session,
        problem_id=problem.id,
        type="polygon.export.done",
        message=f"Polygon export: {report.get('zip_path', 'done')}",
        source="polygon",
        job_id=job.id,
        payload=report,
    )


async def handle_crawl_import(session: AsyncSession, job: RunnerJob, problem: Problem) -> None:
    payload = job.payload_json
    url = payload.get("url")
    ws_id = payload.get("workspace_id")
    if not url or not ws_id:
        job.status = JobStatus.FAILED.value
        job.result_json = {"error": "missing_url_or_workspace"}
        return
    import uuid as _uuid

    report = await crawl_and_import(
        session, problem, url=url, workspace_id=_uuid.UUID(str(ws_id))
    )
    job.status = JobStatus.DONE.value
    job.result_json = report


async def process_job(session: AsyncSession, job_id: uuid.UUID) -> None:
    job = await session.get(RunnerJob, job_id)
    if not job or job.status != JobStatus.QUEUED.value:
        return
    problem = await session.get(Problem, job.problem_id)
    if not problem:
        job.status = JobStatus.FAILED.value
        return

    job.status = JobStatus.RUNNING.value
    await session.flush()

    try:
        if job.kind == JobKind.RUN_SINGLE.value:
            await handle_run_single(session, job, problem)
        elif job.kind == JobKind.COMPILE.value:
            await handle_compile(session, job, problem)
        elif job.kind == JobKind.RUN_COMPARE.value:
            await handle_run_compare(session, job, problem)
        elif job.kind == JobKind.STRESS.value:
            await handle_stress(session, job, problem)
        elif job.kind == JobKind.INTERACTIVE_RUN.value:
            await handle_interactive(session, job, problem)
        elif job.kind == JobKind.POLYGON_EXPORT.value:
            await handle_polygon_export(session, job, problem)
        elif job.kind == JobKind.CRAWL_IMPORT.value:
            await handle_crawl_import(session, job, problem)
        else:
            job.status = JobStatus.FAILED.value
            job.result_json = {"error": f"unknown_kind_{job.kind}"}
    except Exception as e:
        job.status = JobStatus.FAILED.value
        job.result_json = {"error": str(e)}
        job.log_text = str(e)
        await emit_event(
            session,
            problem_id=problem.id,
            type="runner.job.failed",
            message=str(e),
            source="runner",
            job_id=job.id,
            level="ERROR",
        )


async def poll_and_run(session: AsyncSession) -> int:
    result = await session.execute(
        select(RunnerJob).where(RunnerJob.status == JobStatus.QUEUED.value).limit(5)
    )
    jobs = list(result.scalars().all())
    for job in jobs:
        await process_job(session, job.id)
    await session.commit()
    return len(jobs)
