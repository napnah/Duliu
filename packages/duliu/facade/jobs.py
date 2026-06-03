import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from duliu.db.models import Artifact, JobKind, JobStatus, Problem, RunnerJob
from duliu.facade.events import emit_event


class JobFacade:
    @staticmethod
    async def enqueue_run_single(
        session: AsyncSession,
        problem: Problem,
        *,
        program: str,
        input_data: str,
        artifact_version: int | None = None,
        draft: dict | None = None,
        language: str | None = None,
        expected_out: str | None = None,
        use_checker: bool = False,
    ) -> RunnerJob:
        job = RunnerJob(
            problem_id=problem.id,
            kind=JobKind.RUN_SINGLE.value,
            status=JobStatus.QUEUED.value,
            payload_json={
                "program": program,
                "input": input_data,
                "artifact_version": artifact_version,
                "draft": draft,
                "language": language,
                "expected_out": expected_out,
                "use_checker": use_checker,
            },
        )
        session.add(job)
        await session.flush()
        await emit_event(
            session,
            problem_id=problem.id,
            type="runner.run_single.queued",
            message=f"Queued run_single for {program}",
            source="runner",
            job_id=job.id,
        )
        return job

    @staticmethod
    async def enqueue_compile(
        session: AsyncSession,
        problem: Problem,
        *,
        program: str,
        draft: dict | None = None,
        language: str | None = None,
    ) -> RunnerJob:
        job = RunnerJob(
            problem_id=problem.id,
            kind=JobKind.COMPILE.value,
            status=JobStatus.QUEUED.value,
            payload_json={"program": program, "draft": draft, "language": language},
        )
        session.add(job)
        await session.flush()
        await emit_event(
            session,
            problem_id=problem.id,
            type="runner.compile.queued",
            message=f"Queued compile for {program}",
            source="runner",
            job_id=job.id,
        )
        return job

    @staticmethod
    async def enqueue_run_compare(
        session: AsyncSession,
        problem: Problem,
        *,
        input_data: str,
    ) -> RunnerJob:
        job = RunnerJob(
            problem_id=problem.id,
            kind=JobKind.RUN_COMPARE.value,
            status=JobStatus.QUEUED.value,
            payload_json={"input": input_data},
        )
        session.add(job)
        await session.flush()
        await emit_event(
            session,
            problem_id=problem.id,
            type="runner.run_compare.queued",
            message="Queued std+brute compare run",
            source="runner",
            job_id=job.id,
        )
        return job

    @staticmethod
    async def enqueue_stress(
        session: AsyncSession,
        problem: Problem,
        *,
        mode: str = "quick",
    ) -> RunnerJob:
        job = RunnerJob(
            problem_id=problem.id,
            kind=JobKind.STRESS.value,
            status=JobStatus.QUEUED.value,
            payload_json={"mode": mode},
        )
        session.add(job)
        await session.flush()
        await emit_event(
            session,
            problem_id=problem.id,
            type="runner.stress.queued",
            message=f"Queued stress ({mode})",
            source="runner",
            job_id=job.id,
            stage_id="STRESS",
        )
        return job

    @staticmethod
    async def enqueue_interactive_run(
        session: AsyncSession,
        problem: Problem,
        *,
        input_data: str = "",
        draft_std: dict | None = None,
    ) -> RunnerJob:
        job = RunnerJob(
            problem_id=problem.id,
            kind=JobKind.INTERACTIVE_RUN.value,
            status=JobStatus.QUEUED.value,
            payload_json={"input": input_data, "draft_std": draft_std},
        )
        session.add(job)
        await session.flush()
        await emit_event(
            session,
            problem_id=problem.id,
            type="runner.interactive.queued",
            message="Queued interactive run",
            source="runner",
            job_id=job.id,
            stage_id=problem.current_stage,
        )
        return job

    @staticmethod
    async def enqueue_polygon_export(
        session: AsyncSession,
        problem: Problem,
    ) -> RunnerJob:
        job = RunnerJob(
            problem_id=problem.id,
            kind=JobKind.POLYGON_EXPORT.value,
            status=JobStatus.QUEUED.value,
            payload_json={},
        )
        session.add(job)
        await session.flush()
        await emit_event(
            session,
            problem_id=problem.id,
            type="polygon.export.queued",
            message="Queued polygon export",
            source="polygon",
            job_id=job.id,
        )
        return job

    @staticmethod
    async def get_job(session: AsyncSession, job_id: uuid.UUID) -> RunnerJob | None:
        return await session.get(RunnerJob, job_id)

    @staticmethod
    async def latest_artifact(
        session: AsyncSession, problem_id: uuid.UUID, kind: str, version: int | None = None
    ) -> Artifact | None:
        q = select(Artifact).where(Artifact.problem_id == problem_id, Artifact.kind == kind)
        if version is not None:
            q = q.where(Artifact.version == version)
        else:
            q = q.order_by(Artifact.version.desc()).limit(1)
        result = await session.execute(q)
        return result.scalar_one_or_none()
