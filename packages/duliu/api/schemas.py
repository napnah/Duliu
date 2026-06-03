import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class WorkspaceOut(BaseModel):
    id: uuid.UUID
    name: str

    class Config:
        from_attributes = True


class ContestSetOut(BaseModel):
    id: uuid.UUID
    name: str
    contest_style: str
    slot_count: int
    status: str = "DRAFT"
    target_difficulty_json: dict = Field(default_factory=dict)

    class Config:
        from_attributes = True


class SlotProblemBrief(BaseModel):
    id: uuid.UUID
    title: str
    current_stage: str
    problem_type: str
    spec_json: dict = Field(default_factory=dict)


class ContestSlotOut(BaseModel):
    id: uuid.UUID
    slot_label: str
    status: str
    problem_id: uuid.UUID | None = None
    problem: SlotProblemBrief | None = None


class ContestSetDetailOut(BaseModel):
    id: uuid.UUID
    name: str
    contest_style: str
    slot_count: int
    status: str
    target_difficulty_json: dict
    set_eval_json: dict
    slots: list[ContestSlotOut]


class SlotBindRequest(BaseModel):
    problem_id: uuid.UUID


class SlotCreateRequest(BaseModel):
    title: str
    problem_type: str = "TRADITIONAL"
    rating: int | None = None


class SetEvalApprove(BaseModel):
    note: str | None = None


class ProblemOut(BaseModel):
    id: uuid.UUID
    title: str
    current_stage: str
    control_mode: str
    originality: str
    problem_type: str
    contest_style: str
    spec_json: dict

    class Config:
        from_attributes = True


class ContestSetCreate(BaseModel):
    name: str
    contest_style: str = "ICPC"
    slot_count: int | None = None


class ProblemCreate(BaseModel):
    title: str = "New Problem"
    originality: str = "ORIGINAL"
    contest_style: str = "ICPC"
    problem_type: str = "TRADITIONAL"


class ArtifactOut(BaseModel):
    id: uuid.UUID
    kind: str
    version: int
    content_text: str
    language: str | None
    author: str
    created_at: datetime

    class Config:
        from_attributes = True


class ArtifactSave(BaseModel):
    content_text: str
    language: str | None = None
    author: str = "human"


class InteractiveRunRequest(BaseModel):
    use_editor_draft: bool = False
    draft_std: dict | None = None


class RunRequest(BaseModel):
    program: str = "std"  # std | brute | checker
    input: str = ""
    artifact_version: int | None = None
    use_editor_draft: bool = False
    draft: dict | None = None
    language: str | None = None
    expected_out: str | None = None
    use_checker: bool = False


class StressRequest(BaseModel):
    mode: str = "quick"


class CompileRequest(BaseModel):
    program: str = "std"
    use_editor_draft: bool = False
    draft: dict | None = None
    language: str | None = None


class CompareRunRequest(BaseModel):
    input: str = ""


class StageAction(BaseModel):
    note: str | None = None


class DispatchRequest(BaseModel):
    stage_id: str
    reason: str = ""


class JobOut(BaseModel):
    id: uuid.UUID
    kind: str
    status: str
    result_json: dict | None
    log_text: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class EventOut(BaseModel):
    id: uuid.UUID
    type: str
    message: str
    source: str
    level: str
    stage_id: str | None
    job_id: uuid.UUID | None
    run_id: uuid.UUID | None = None
    payload_json: dict
    created_at: datetime

    class Config:
        from_attributes = True


class TreeOut(BaseModel):
    workspace: WorkspaceOut
    contest_sets: list[ContestSetOut]
    problems: list[ProblemOut]


class ContestTreeNode(BaseModel):
    contest_set: ContestSetOut
    slots: list[ContestSlotOut]


class SessionCreate(BaseModel):
    problem_id: uuid.UUID | None = None
    title: str = "Session"


class SessionOut(BaseModel):
    id: uuid.UUID
    problem_id: uuid.UUID | None
    title: str
    created_at: datetime

    class Config:
        from_attributes = True


class ChatRequest(BaseModel):
    message: str
    problem_id: uuid.UUID | None = None
    contest_set_id: uuid.UUID | None = None


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    tool_calls_json: dict | None
    created_at: datetime

    class Config:
        from_attributes = True


class ChatResponse(BaseModel):
    user: MessageOut
    assistant: MessageOut
    tools_used: list[dict] = Field(default_factory=list)


class SecretSet(BaseModel):
    openai_api_key: str | None = None


class SecretsOut(BaseModel):
    openai_configured: bool
    openai_masked: str | None = None


class ControlModeSet(BaseModel):
    mode: str


class CrawlerConfigOut(BaseModel):
    crawl_sites: list[str] = Field(default_factory=list)
    cf_cookie_configured: bool = False
    cf_cookie_masked: str | None = None
    luogu_cookie_configured: bool = False
    luogu_cookie_masked: str | None = None
    polygon_cookie_configured: bool = False
    polygon_cookie_masked: str | None = None
    whitelist_hosts: list[str] = Field(default_factory=list)


class CrawlerConfigSet(BaseModel):
    crawl_sites: list[str] | None = None
    cf_cookie: str | None = None
    luogu_cookie: str | None = None
    polygon_cookie: str | None = None


class CrawlImportRequest(BaseModel):
    url: str
    title: str | None = None


class CrawlImportResponse(BaseModel):
    problem: ProblemOut
    job: JobOut


class SubmissionConfirmRequest(BaseModel):
    submission_url: str | None = None
    handle: str | None = None
