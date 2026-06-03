import hashlib
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from duliu.api.schemas import (
    ArtifactOut,
    ArtifactSave,
    ChatRequest,
    ChatResponse,
    CompareRunRequest,
    CompileRequest,
    ContestSetCreate,
    ContestSetDetailOut,
    ContestSetOut,
    ContestSlotOut,
    SetEvalApprove,
    SlotBindRequest,
    SlotCreateRequest,
    SlotProblemBrief,
    ControlModeSet,
    DispatchRequest,
    EventOut,
    InteractiveRunRequest,
    JobOut,
    MessageOut,
    ProblemCreate,
    ProblemOut,
    RunRequest,
    SecretSet,
    SecretsOut,
    CrawlerConfigOut,
    CrawlerConfigSet,
    CrawlImportRequest,
    CrawlImportResponse,
    SubmissionConfirmRequest,
    FetchAcStdRequest,
    ArtifactVersionOut,
    ArtifactRestoreRequest,
    SessionCreate,
    SessionOut,
    StageAction,
    StressRequest,
    TreeOut,
    WorkspaceOut,
)
from duliu.config import settings
from duliu.db.bootstrap import (
    create_contest_set,
    ensure_default_workspace,
    ensure_m2_stages,
    ensure_m3_stages,
    seed_communication_demo,
    refresh_interactive_interactor,
    seed_interactive_demo,
    seed_m4_demo_set,
    ensure_m6_import_stages,
    seed_m6_non_original_demo,
    seed_package_ready_problem,
    seed_demo_contest_set,
    seed_demo_problem,
    seed_oi_contest_set,
    seed_adversarial_ready_problem,
    seed_oi_demo_problem,
    seed_spj_demo_problem,
)
from duliu.db.models import (
    M3_STAGE_ORDER,
    Artifact,
    ContestSet,
    ContestSlot,
    Event,
    Problem,
    ProblemStage,
    Session,
    StageStatus,
    Workspace,
    WorkspaceSecret,
)
from duliu.db.session import async_session, get_db, init_db
from duliu.facade.contest import ContestFacade
from duliu.facade.crawl import CrawlFacade
from duliu.facade.import_flow import (
    confirm_submission,
    enqueue_import_check,
    fetch_ac_std_and_save,
)
from duliu.facade.monitor_stream import sse_event_generator, ws_event_loop
from duliu.pipeline.orchestrator import PipelineOrchestrator
from duliu.facade.jobs import JobFacade
from duliu.facade.artifacts import ArtifactFacade
from duliu.facade.secrets_store import get_crawler_config, get_workspace_secret, set_crawler_config
from duliu.facade.pipeline import PipelineFacade
from duliu.facade.session import SessionFacade
from duliu.polygon.export import build_polygon_zip
from duliu.workflow.loader import contest_defaults

WEB_DIR = Path(__file__).resolve().parent.parent / "web" / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with async_session() as session:
        ws = await ensure_default_workspace(session)
        await ensure_m2_stages(session)
        await ensure_m3_stages(session)
        await seed_demo_contest_set(session, ws)
        await seed_oi_contest_set(session, ws)
        await seed_demo_problem(session, ws)
        await seed_oi_demo_problem(session, ws)
        await seed_spj_demo_problem(session, ws)
        await seed_adversarial_ready_problem(session, ws)
        await seed_interactive_demo(session, ws)
        await refresh_interactive_interactor(session, ws)
        await seed_communication_demo(session, ws)
        await seed_package_ready_problem(session, ws)
        await seed_m4_demo_set(session, ws)
        await ensure_m6_import_stages(session)
        await seed_m6_non_original_demo(session, ws)
        from duliu.db.secret_bootstrap import bootstrap_secrets_from_env

        await bootstrap_secrets_from_env(session, ws)
        await session.commit()
    if settings.use_langgraph:
        try:
            from duliu.pipeline.checkpoint_saver import get_checkpointer

            await get_checkpointer()
        except Exception as exc:
            import logging

            logging.getLogger("duliu.api").warning(
                "LangGraph checkpointer init skipped: %s", exc
            )
    yield


app = FastAPI(title="Duliu API", version="0.9.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if WEB_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")


@app.get("/api/health")
async def health():
    from duliu.pipeline.checkpoint_saver import checkpointer_mode
    from duliu.runner.sandbox import isolate_available, sandbox_mode

    return {
        "status": "ok",
        "milestone": "M12",
        "langgraph": settings.use_langgraph,
        "langgraph_checkpoint": checkpointer_mode(),
        "monitor_transport": "websocket+sse",
        "sse_poll_seconds": settings.sse_poll_seconds,
        "sandbox": sandbox_mode(),
        "isolate_available": isolate_available(),
    }


@app.get("/")
async def index():
    index_path = WEB_DIR / "index.html"
    if index_path.is_file():
        return FileResponse(index_path)
    return {"service": "duliu", "docs": "/docs"}


@app.get("/api/tree", response_model=TreeOut)
async def get_tree(db: AsyncSession = Depends(get_db)):
    ws = await ensure_default_workspace(db)
    cs = (await db.execute(select(ContestSet).where(ContestSet.workspace_id == ws.id))).scalars().all()
    probs = (await db.execute(select(Problem).where(Problem.workspace_id == ws.id))).scalars().all()
    return TreeOut(
        workspace=WorkspaceOut.model_validate(ws),
        contest_sets=[ContestSetOut.model_validate(c) for c in cs],
        problems=[ProblemOut.model_validate(p) for p in probs],
    )


@app.post("/api/contest-sets", response_model=ContestSetOut)
async def post_contest_set(body: ContestSetCreate, db: AsyncSession = Depends(get_db)):
    ws = await ensure_default_workspace(db)
    count = body.slot_count
    if count is None:
        count = 13 if body.contest_style == "ICPC" else contest_defaults("OI").get("problem_count", 4)
    cs = await create_contest_set(db, ws, body.name, body.contest_style, count)
    await db.commit()
    return ContestSetOut.model_validate(cs)


@app.get("/api/contest-sets/{contest_set_id}", response_model=ContestSetDetailOut)
async def get_contest_set(contest_set_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    detail = await ContestFacade.get_detail(db, contest_set_id)
    if not detail:
        raise HTTPException(404, "contest set not found")
    slots = []
    for s in detail["slots"]:
        prob = None
        if s.get("problem"):
            pj = s["problem"]
            prob = SlotProblemBrief(
                id=uuid.UUID(pj["id"]),
                title=pj["title"],
                current_stage=pj["current_stage"],
                problem_type=pj["problem_type"],
                spec_json=pj.get("spec_json") or {},
            )
        slots.append(
            ContestSlotOut(
                id=uuid.UUID(s["id"]),
                slot_label=s["slot_label"],
                status=s["status"],
                problem_id=uuid.UUID(s["problem_id"]) if s.get("problem_id") else None,
                problem=prob,
            )
        )
    cs = await db.get(ContestSet, contest_set_id)
    return ContestSetDetailOut(
        id=contest_set_id,
        name=detail["name"],
        contest_style=detail["contest_style"],
        slot_count=detail["slot_count"],
        status=detail["status"],
        target_difficulty_json=detail["target_difficulty_json"],
        set_eval_json=detail["set_eval_json"] or {},
        slots=slots,
    )


@app.post("/api/contest-sets/{contest_set_id}/slots/{slot_label}/bind")
async def bind_slot(
    contest_set_id: uuid.UUID,
    slot_label: str,
    body: SlotBindRequest,
    db: AsyncSession = Depends(get_db),
):
    cs = await db.get(ContestSet, contest_set_id)
    if not cs:
        raise HTTPException(404, "contest set not found")
    try:
        await ContestFacade.bind_problem_to_slot(db, cs, slot_label, body.problem_id)
        await db.commit()
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True, "slot_label": slot_label, "problem_id": str(body.problem_id)}


@app.post("/api/contest-sets/{contest_set_id}/slots/{slot_label}/create-problem", response_model=ProblemOut)
async def create_problem_in_slot(
    contest_set_id: uuid.UUID,
    slot_label: str,
    body: SlotCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    cs = await db.get(ContestSet, contest_set_id)
    if not cs:
        raise HTTPException(404, "contest set not found")
    try:
        p = await ContestFacade.create_problem_in_slot(
            db, cs, slot_label, title=body.title, problem_type=body.problem_type, rating=body.rating
        )
        await db.commit()
        await db.refresh(p)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return ProblemOut.model_validate(p)


@app.post("/api/contest-sets/{contest_set_id}/evaluate")
async def evaluate_contest_set(contest_set_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    cs = await db.get(ContestSet, contest_set_id)
    if not cs:
        raise HTTPException(404, "contest set not found")
    report = await ContestFacade.evaluate_set(db, cs)
    await db.commit()
    return report


@app.post("/api/contest-sets/{contest_set_id}/approve-eval", response_model=ContestSetOut)
async def approve_contest_eval(
    contest_set_id: uuid.UUID,
    body: SetEvalApprove,
    db: AsyncSession = Depends(get_db),
):
    cs = await db.get(ContestSet, contest_set_id)
    if not cs:
        raise HTTPException(404, "contest set not found")
    try:
        await ContestFacade.approve_set_eval(db, cs, note=body.note)
        await db.commit()
        await db.refresh(cs)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return ContestSetOut.model_validate(cs)


@app.get("/api/monitor/events", response_model=list[EventOut])
async def list_events(
    problem_id: uuid.UUID | None = None,
    contest_set_id: uuid.UUID | None = None,
    run_id: uuid.UUID | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    q = select(Event).order_by(Event.created_at.desc()).limit(min(limit, 500))
    if problem_id:
        q = q.where(Event.problem_id == problem_id)
    if contest_set_id:
        q = q.where(Event.contest_set_id == contest_set_id)
    if run_id:
        q = q.where(Event.run_id == run_id)
    rows = (await db.execute(q)).scalars().all()
    return [EventOut.model_validate(e) for e in rows]


@app.get("/api/monitor/events/stream")
async def stream_events(
    problem_id: uuid.UUID | None = None,
    contest_set_id: uuid.UUID | None = None,
):
    """M10 SSE: poll DB for new events (replaces 3s REST poll on monitor tab)."""
    gen = sse_event_generator(
        async_session,
        problem_id=problem_id,
        contest_set_id=contest_set_id,
        poll_seconds=settings.sse_poll_seconds,
    )
    return StreamingResponse(gen, media_type="text/event-stream")


@app.websocket("/api/monitor/events/ws")
async def websocket_events(
    websocket: WebSocket,
    problem_id: uuid.UUID | None = None,
    contest_set_id: uuid.UUID | None = None,
):
    """M12 WebSocket monitor (same event feed as SSE)."""
    await websocket.accept()

    async def send_json(data: dict) -> None:
        await websocket.send_json(data)

    try:
        await ws_event_loop(
            send_json,
            async_session,
            problem_id=problem_id,
            contest_set_id=contest_set_id,
            poll_seconds=settings.sse_poll_seconds,
        )
    except WebSocketDisconnect:
        return
    except Exception:
        await websocket.close()


@app.get("/api/langgraph/dispatch-graph")
async def langgraph_dispatch_graph():
    from duliu.pipeline.langgraph_runner import dispatch_graph_metadata, langgraph_enabled

    meta = dispatch_graph_metadata()
    return {"enabled": langgraph_enabled(), **meta}


@app.post("/api/problems", response_model=ProblemOut)
async def create_problem(body: ProblemCreate, db: AsyncSession = Depends(get_db)):
    ws = await ensure_default_workspace(db)
    problem = Problem(
        workspace_id=ws.id,
        title=body.title,
        originality=body.originality,
        contest_style=body.contest_style,
        problem_type=body.problem_type,
        control_mode="HUMAN",
        current_stage="SPEC",
        spec_json={
            "limits": {"time_ms": 1000, "memory_mb": 256},
            "samples": [],
            "solution_languages": ["cpp", "python", "java"],
        },
    )
    db.add(problem)
    await db.flush()
    for stage_id in M3_STAGE_ORDER:
        db.add(
            ProblemStage(
                problem_id=problem.id,
                stage_id=stage_id,
                status=StageStatus.AWAITING_HUMAN.value
                if stage_id == "SPEC"
                else StageStatus.PENDING.value,
            )
        )
    await db.commit()
    await db.refresh(problem)
    return ProblemOut.model_validate(problem)


@app.get("/api/problems/{problem_id}", response_model=ProblemOut)
async def get_problem(problem_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    p = await db.get(Problem, problem_id)
    if not p:
        raise HTTPException(404, "problem not found")
    return ProblemOut.model_validate(p)


@app.get("/api/problems/{problem_id}/stages")
async def list_stages(problem_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    p = await db.get(Problem, problem_id)
    if not p:
        raise HTTPException(404, "problem not found")
    from duliu.db.models import stage_order_for

    order = stage_order_for(p.contest_style, p.originality)
    rows = (
        await db.execute(select(ProblemStage).where(ProblemStage.problem_id == problem_id))
    ).scalars().all()
    by_id = {s.stage_id: s for s in rows}
    out = []
    for sid in order:
        s = by_id.get(sid)
        if not s:
            continue
        out.append(
            {
                "stage_id": s.stage_id,
                "status": s.status,
                "approved_by": s.approved_by,
                "note": s.note,
            }
        )
    for s in rows:
        if s.stage_id not in order:
            out.append(
                {
                    "stage_id": s.stage_id,
                    "status": s.status,
                    "approved_by": s.approved_by,
                    "note": s.note,
                }
            )
    return out


@app.get("/api/runner/sandbox-status")
async def sandbox_status():
    from duliu.runner.sandbox import isolate_available, sandbox_mode

    return {
        "mode": sandbox_mode(),
        "isolate_available": isolate_available(),
        "use_isolate": settings.use_isolate,
        "cpp_via_isolate": sandbox_mode() == "isolate",
        "python_java_via_isolate": False,
    }


@app.get("/api/problems/{problem_id}/langgraph/status")
async def langgraph_status(problem_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    from duliu.pipeline.checkpoint_saver import checkpointer_mode

    p = await db.get(Problem, problem_id)
    if not p:
        raise HTTPException(404, "problem not found")
    from duliu.pipeline.langgraph_runner import dispatch_graph_metadata

    return {
        "enabled": settings.use_langgraph,
        "thread_id": (p.spec_json or {}).get("langgraph_thread_id"),
        "checkpointer": checkpointer_mode(),
        "checkpoint_config": settings.langgraph_checkpoint,
        "graph": dispatch_graph_metadata(),
    }


@app.get("/api/problems/{problem_id}/langgraph/history")
async def langgraph_history(problem_id: uuid.UUID, limit: int = 20, db: AsyncSession = Depends(get_db)):
    from duliu.pipeline.langgraph_runner import langgraph_enabled, list_checkpoint_history

    p = await db.get(Problem, problem_id)
    if not p:
        raise HTTPException(404, "problem not found")
    if not langgraph_enabled():
        return {"enabled": False, "history": []}
    thread_id = (p.spec_json or {}).get("langgraph_thread_id") or str(problem_id)
    try:
        history = await list_checkpoint_history(thread_id, limit=min(limit, 50))
    except ImportError:
        return {"enabled": False, "history": [], "error": "langgraph not installed"}
    return {"enabled": True, "thread_id": thread_id, "history": history}


@app.get("/api/problems/{problem_id}/pipeline-graph")
async def pipeline_graph(problem_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    p = await db.get(Problem, problem_id)
    if not p:
        raise HTTPException(404, "problem not found")
    return await PipelineOrchestrator.snapshot(db, p)


@app.post("/api/problems/{problem_id}/import/confirm-submission", response_model=ProblemOut)
async def confirm_import_submission(
    problem_id: uuid.UUID,
    body: SubmissionConfirmRequest,
    db: AsyncSession = Depends(get_db),
):
    p = await db.get(Problem, problem_id)
    if not p:
        raise HTTPException(404, "problem not found")
    try:
        await confirm_submission(
            db,
            p,
            submission_url=body.submission_url,
            handle=body.handle,
        )
        await db.commit()
        await db.refresh(p)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return ProblemOut.model_validate(p)


@app.post("/api/problems/{problem_id}/import/fetch-std")
async def fetch_import_std(
    problem_id: uuid.UUID,
    body: FetchAcStdRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    p = await db.get(Problem, problem_id)
    if not p:
        raise HTTPException(404, "problem not found")
    ws = await ensure_default_workspace(db)
    cfg = await get_crawler_config(db, ws)
    cookie = await get_workspace_secret(db, ws.id, "crawler_cf_cookie")
    try:
        out = await fetch_ac_std_and_save(
            db,
            p,
            cookie=cookie,
            handle=(body.handle if body else None),
        )
        await db.commit()
        await db.refresh(p)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"problem_id": str(problem_id), "fetch": out, "cf_cookie_configured": cfg["cf_cookie_configured"]}


@app.post("/api/problems/{problem_id}/import/check", response_model=JobOut)
async def run_import_check(problem_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    p = await db.get(Problem, problem_id)
    if not p:
        raise HTTPException(404, "problem not found")
    if p.originality != "NON_ORIGINAL":
        raise HTTPException(400, "import_check only for NON_ORIGINAL")
    job = await enqueue_import_check(db, p)
    await db.commit()
    await db.refresh(job)
    return JobOut.model_validate(job)


@app.post("/api/problems/{problem_id}/stages/{stage_id}/approve", response_model=ProblemOut)
async def approve_stage(
    problem_id: uuid.UUID,
    stage_id: str,
    body: StageAction,
    db: AsyncSession = Depends(get_db),
):
    p = await db.get(Problem, problem_id)
    if not p:
        raise HTTPException(404, "problem not found")
    try:
        await PipelineFacade.approve_stage(db, p, stage_id, note=body.note)
        await db.commit()
        await db.refresh(p)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return ProblemOut.model_validate(p)


@app.post("/api/problems/{problem_id}/stages/{stage_id}/reject", response_model=ProblemOut)
async def reject_stage(
    problem_id: uuid.UUID,
    stage_id: str,
    body: StageAction,
    db: AsyncSession = Depends(get_db),
):
    p = await db.get(Problem, problem_id)
    if not p:
        raise HTTPException(404, "problem not found")
    await PipelineFacade.reject_stage(db, p, stage_id, note=body.note or "")
    await db.commit()
    await db.refresh(p)
    return ProblemOut.model_validate(p)


@app.post("/api/problems/{problem_id}/dispatch")
async def dispatch_stage(
    problem_id: uuid.UUID,
    body: DispatchRequest,
    db: AsyncSession = Depends(get_db),
):
    p = await db.get(Problem, problem_id)
    if not p:
        raise HTTPException(404, "problem not found")
    try:
        out = await PipelineFacade.dispatch(db, p, body.stage_id, reason=body.reason)
        await db.commit()
        await db.refresh(p)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"problem": ProblemOut.model_validate(p), "dispatch": out}


@app.post("/api/problems/{problem_id}/control-mode", response_model=ProblemOut)
async def set_control_mode(
    problem_id: uuid.UUID,
    body: ControlModeSet,
    db: AsyncSession = Depends(get_db),
):
    p = await db.get(Problem, problem_id)
    if not p:
        raise HTTPException(404, "problem not found")
    try:
        await SessionFacade.set_control_mode(db, p, body.mode)
        await db.commit()
        await db.refresh(p)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return ProblemOut.model_validate(p)


@app.get("/api/problems/{problem_id}/artifacts")
async def list_artifacts(problem_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(Artifact)
            .where(Artifact.problem_id == problem_id)
            .order_by(Artifact.kind, Artifact.version.desc())
        )
    ).scalars().all()
    latest: dict[str, Artifact] = {}
    for a in rows:
        if a.kind not in latest:
            latest[a.kind] = a
    return {
        "items": [
            {"kind": k, "version": v.version, "language": v.language, "id": str(v.id)}
            for k, v in latest.items()
        ]
    }


@app.get("/api/problems/{problem_id}/artifacts/{kind}", response_model=ArtifactOut)
async def get_artifact(
    problem_id: uuid.UUID,
    kind: str,
    version: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    art = await JobFacade.latest_artifact(db, problem_id, kind, version)
    if not art:
        raise HTTPException(404, "artifact not found")
    return ArtifactOut.model_validate(art)


@app.get("/api/problems/{problem_id}/artifacts/{kind}/versions", response_model=list[ArtifactVersionOut])
async def list_artifact_versions(
    problem_id: uuid.UUID, kind: str, db: AsyncSession = Depends(get_db)
):
    versions = await ArtifactFacade.list_versions(db, problem_id, kind)
    return [ArtifactVersionOut(**v) for v in versions]


@app.post("/api/problems/{problem_id}/artifacts/{kind}/restore", response_model=ArtifactOut)
async def restore_artifact_version(
    problem_id: uuid.UUID,
    kind: str,
    body: ArtifactRestoreRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        art = await ArtifactFacade.restore_version(db, problem_id, kind, body.version)
        await db.commit()
        await db.refresh(art)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return ArtifactOut.model_validate(art)


@app.put("/api/problems/{problem_id}/artifacts/{kind}", response_model=ArtifactOut)
async def put_artifact(
    problem_id: uuid.UUID,
    kind: str,
    body: ArtifactSave,
    db: AsyncSession = Depends(get_db),
):
    latest = await JobFacade.latest_artifact(db, problem_id, kind)
    ver = (latest.version + 1) if latest else 1
    content = body.content_text
    art = Artifact(
        problem_id=problem_id,
        kind=kind,
        version=ver,
        content_text=content,
        sha256=hashlib.sha256(content.encode()).hexdigest(),
        author=body.author,
        language=body.language,
    )
    db.add(art)
    await db.commit()
    await db.refresh(art)
    return ArtifactOut.model_validate(art)


@app.post("/api/problems/{problem_id}/compile", response_model=JobOut)
async def compile_only(
    problem_id: uuid.UUID,
    body: CompileRequest,
    db: AsyncSession = Depends(get_db),
):
    p = await db.get(Problem, problem_id)
    if not p:
        raise HTTPException(404, "problem not found")
    draft = body.draft if body.use_editor_draft else None
    job = await JobFacade.enqueue_compile(
        db, p, program=body.program, draft=draft, language=body.language
    )
    await db.commit()
    await db.refresh(job)
    return JobOut.model_validate(job)


@app.post("/api/problems/{problem_id}/run", response_model=JobOut)
async def run_single(
    problem_id: uuid.UUID,
    body: RunRequest,
    db: AsyncSession = Depends(get_db),
):
    p = await db.get(Problem, problem_id)
    if not p:
        raise HTTPException(404, "problem not found")
    draft = body.draft if body.use_editor_draft else None
    job = await JobFacade.enqueue_run_single(
        db,
        p,
        program=body.program,
        input_data=body.input,
        artifact_version=body.artifact_version,
        draft=draft,
        language=body.language,
        expected_out=body.expected_out,
        use_checker=body.use_checker,
    )
    await db.commit()
    await db.refresh(job)
    return JobOut.model_validate(job)


@app.post("/api/problems/{problem_id}/run/compare", response_model=JobOut)
async def run_compare(
    problem_id: uuid.UUID,
    body: CompareRunRequest,
    db: AsyncSession = Depends(get_db),
):
    p = await db.get(Problem, problem_id)
    if not p:
        raise HTTPException(404, "problem not found")
    job = await JobFacade.enqueue_run_compare(db, p, input_data=body.input)
    await db.commit()
    await db.refresh(job)
    return JobOut.model_validate(job)


@app.post("/api/problems/{problem_id}/stress/run", response_model=JobOut)
async def stress_run(
    problem_id: uuid.UUID,
    body: StressRequest,
    db: AsyncSession = Depends(get_db),
):
    p = await db.get(Problem, problem_id)
    if not p:
        raise HTTPException(404, "problem not found")
    job = await JobFacade.enqueue_stress(db, p, mode=body.mode)
    await db.commit()
    await db.refresh(job)
    return JobOut.model_validate(job)


@app.post("/api/problems/{problem_id}/run/interactive", response_model=JobOut)
async def run_interactive(
    problem_id: uuid.UUID,
    body: InteractiveRunRequest,
    db: AsyncSession = Depends(get_db),
):
    p = await db.get(Problem, problem_id)
    if not p:
        raise HTTPException(404, "problem not found")
    if p.problem_type not in ("INTERACTIVE", "COMMUNICATION"):
        raise HTTPException(400, "problem_type must be INTERACTIVE or COMMUNICATION")
    draft = body.draft_std if body.use_editor_draft else None
    job = await JobFacade.enqueue_interactive_run(db, p, draft_std=draft)
    await db.commit()
    await db.refresh(job)
    return JobOut.model_validate(job)


@app.get("/api/problems/{problem_id}/polygon/export")
async def polygon_export_zip(problem_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    p = await db.get(Problem, problem_id)
    if not p:
        raise HTTPException(404, "problem not found")
    rows = (await db.execute(select(Artifact).where(Artifact.problem_id == problem_id))).scalars().all()
    data = build_polygon_zip(p, list(rows))
    safe = p.title.replace(" ", "_")[:64]
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe}_polygon.zip"'},
    )


@app.post("/api/problems/{problem_id}/polygon/export", response_model=JobOut)
async def polygon_export_job(problem_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    p = await db.get(Problem, problem_id)
    if not p:
        raise HTTPException(404, "problem not found")
    job = await JobFacade.enqueue_polygon_export(db, p)
    await db.commit()
    await db.refresh(job)
    return JobOut.model_validate(job)


@app.get("/api/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    job = await JobFacade.get_job(db, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return JobOut.model_validate(job)


@app.post("/api/sessions", response_model=SessionOut)
async def create_session(body: SessionCreate, db: AsyncSession = Depends(get_db)):
    ws = await ensure_default_workspace(db)
    chat = await SessionFacade.create_session(
        db, ws, problem_id=body.problem_id, title=body.title
    )
    await db.commit()
    await db.refresh(chat)
    return SessionOut.model_validate(chat)


@app.get("/api/sessions/{session_id}/messages", response_model=list[MessageOut])
async def get_session_messages(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    chat = await SessionFacade.get_session(db, session_id)
    if not chat:
        raise HTTPException(404, "session not found")
    msgs = await SessionFacade.list_messages(db, session_id)
    return [MessageOut.model_validate(m) for m in msgs]


@app.post("/api/sessions/{session_id}/chat", response_model=ChatResponse)
async def session_chat(
    session_id: uuid.UUID,
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    chat = await SessionFacade.get_session(db, session_id)
    if not chat:
        raise HTTPException(404, "session not found")
    problem = None
    pid = body.problem_id or chat.problem_id
    if pid:
        problem = await db.get(Problem, pid)
    contest_set = None
    if body.contest_set_id:
        contest_set = await db.get(ContestSet, body.contest_set_id)
    user_msg, asst, tools = await SessionFacade.chat(
        db, chat, body.message, problem=problem, contest_set=contest_set
    )
    await db.commit()
    return ChatResponse(
        user=MessageOut.model_validate(user_msg),
        assistant=MessageOut.model_validate(asst),
        tools_used=tools,
    )


@app.get("/api/workspace/secrets", response_model=SecretsOut)
async def get_secrets(db: AsyncSession = Depends(get_db)):
    ws = await ensure_default_workspace(db)
    row = (
        await db.execute(
            select(WorkspaceSecret).where(
                WorkspaceSecret.workspace_id == ws.id,
                WorkspaceSecret.key_name == "openai_api_key",
            )
        )
    ).scalar_one_or_none()
    if not row or not row.value_encrypted:
        env_key = settings.openai_api_key
        if env_key:
            return SecretsOut(openai_configured=True, openai_masked=_mask(env_key))
        return SecretsOut(openai_configured=False)
    return SecretsOut(openai_configured=True, openai_masked=_mask(row.value_encrypted))


@app.put("/api/workspace/secrets", response_model=SecretsOut)
async def set_secrets(body: SecretSet, db: AsyncSession = Depends(get_db)):
    ws = await ensure_default_workspace(db)
    if body.openai_api_key is not None:
        row = (
            await db.execute(
                select(WorkspaceSecret).where(
                    WorkspaceSecret.workspace_id == ws.id,
                    WorkspaceSecret.key_name == "openai_api_key",
                )
            )
        ).scalar_one_or_none()
        if row:
            row.value_encrypted = body.openai_api_key
        else:
            db.add(
                WorkspaceSecret(
                    workspace_id=ws.id,
                    key_name="openai_api_key",
                    value_encrypted=body.openai_api_key,
                )
            )
        settings.openai_api_key = body.openai_api_key
    await db.commit()
    key = body.openai_api_key or settings.openai_api_key
    return SecretsOut(
        openai_configured=bool(key),
        openai_masked=_mask(key) if key else None,
    )


def _mask(key: str) -> str:
    if len(key) < 8:
        return "****"
    return key[:3] + "..." + key[-4:]


@app.get("/api/workspace/crawler-config", response_model=CrawlerConfigOut)
async def get_crawler_config_route(db: AsyncSession = Depends(get_db)):
    ws = await ensure_default_workspace(db)
    cfg = await get_crawler_config(db, ws)
    return CrawlerConfigOut(**cfg)


@app.put("/api/workspace/crawler-config", response_model=CrawlerConfigOut)
async def set_crawler_config_route(body: CrawlerConfigSet, db: AsyncSession = Depends(get_db)):
    ws = await ensure_default_workspace(db)
    cfg = await set_crawler_config(db, ws, body.model_dump(exclude_unset=True))
    await db.commit()
    return CrawlerConfigOut(**cfg)


@app.post("/api/crawl/import", response_model=CrawlImportResponse)
async def crawl_import(body: CrawlImportRequest, db: AsyncSession = Depends(get_db)):
    ws = await ensure_default_workspace(db)
    try:
        problem = await CrawlFacade.create_import_problem(
            db, ws, url=body.url, title=body.title
        )
        job = await CrawlFacade.enqueue_crawl(db, problem, url=body.url, workspace_id=ws.id)
        await db.commit()
        await db.refresh(problem)
        await db.refresh(job)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return CrawlImportResponse(
        problem=ProblemOut.model_validate(problem),
        job=JobOut.model_validate(job),
    )


@app.post("/api/jobs/{job_id}/retry", response_model=JobOut)
async def retry_job(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    job = await JobFacade.get_job(db, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    try:
        job = await JobFacade.retry_job(db, job)
        await db.commit()
        await db.refresh(job)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return JobOut.model_validate(job)


@app.post("/api/jobs/{job_id}/cancel", response_model=JobOut)
async def cancel_job(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    job = await JobFacade.get_job(db, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    try:
        job = await JobFacade.cancel_job(db, job)
        await db.commit()
        await db.refresh(job)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return JobOut.model_validate(job)


@app.get("/api/monitor/events/export")
async def export_events(
    problem_id: uuid.UUID | None = None,
    contest_set_id: uuid.UUID | None = None,
    limit: int = 500,
    db: AsyncSession = Depends(get_db),
):
    import json

    q = select(Event).order_by(Event.created_at.desc()).limit(min(limit, 2000))
    if problem_id:
        q = q.where(Event.problem_id == problem_id)
    if contest_set_id:
        q = q.where(Event.contest_set_id == contest_set_id)
    rows = (await db.execute(q)).scalars().all()
    payload = [
        {
            "id": str(e.id),
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "source": e.source,
            "type": e.type,
            "message": e.message,
            "problem_id": str(e.problem_id) if e.problem_id else None,
            "run_id": str(e.run_id) if e.run_id else None,
        }
        for e in rows
    ]
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=duliu-events.json"},
    )


def run() -> None:
    import uvicorn

    uvicorn.run("duliu.api.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    run()
