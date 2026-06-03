import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class StageStatus(str, enum.Enum):
    PENDING = "PENDING"
    AGENT_WORKING = "AGENT_WORKING"
    AWAITING_HUMAN = "AWAITING_HUMAN"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobKind(str, enum.Enum):
    RUN_SINGLE = "run_single"
    COMPILE = "compile"
    STRESS = "stress"
    RUN_COMPARE = "run_compare"
    INTERACTIVE_RUN = "interactive_run"
    POLYGON_EXPORT = "polygon_export"


# M1 stage chain (ORIGINAL, skip IDEA for bootstrap)
M1_STAGE_ORDER = ["SPEC", "STATEMENT", "SOLUTION", "GENERATOR", "STRESS"]
# M2 adds S6 adversarial review after STRESS
M2_STAGE_ORDER = M1_STAGE_ORDER + ["ADVERSARIAL_REVIEW"]
# M3 adds S7 PACKAGE + S8 EDITORIAL
M3_STAGE_ORDER = M2_STAGE_ORDER + ["PACKAGE", "EDITORIAL"]


def stage_order_for(contest_style: str) -> list[str]:
    """M3 full stage chain; OI/ICPC differ in workflow YAML checks only."""
    return list(M3_STAGE_ORDER)


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    config_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    contest_sets: Mapped[list["ContestSet"]] = relationship(back_populates="workspace")
    problems: Mapped[list["Problem"]] = relationship(back_populates="workspace")


class ContestSet(Base):
    __tablename__ = "contest_sets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    name: Mapped[str] = mapped_column(String(256))
    contest_style: Mapped[str] = mapped_column(String(16), default="ICPC")
    originality_policy: Mapped[str] = mapped_column(String(32), default="ORIGINAL")
    target_difficulty_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    slot_count: Mapped[int] = mapped_column(Integer, default=13)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    workspace: Mapped["Workspace"] = relationship(back_populates="contest_sets")
    slots: Mapped[list["ContestSlot"]] = relationship(back_populates="contest_set")


class ContestSlot(Base):
    __tablename__ = "contest_slots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contest_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("contest_sets.id"))
    slot_label: Mapped[str] = mapped_column(String(8))
    problem_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("problems.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="EMPTY")

    contest_set: Mapped["ContestSet"] = relationship(back_populates="slots")


class Problem(Base):
    __tablename__ = "problems"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    contest_set_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contest_sets.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(256), default="Untitled")
    originality: Mapped[str] = mapped_column(String(32), default="ORIGINAL")
    problem_type: Mapped[str] = mapped_column(String(32), default="TRADITIONAL")
    contest_style: Mapped[str] = mapped_column(String(16), default="ICPC")
    control_mode: Mapped[str] = mapped_column(String(16), default="HUMAN")
    current_stage: Mapped[str] = mapped_column(String(32), default="SPEC")
    spec_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    workspace: Mapped["Workspace"] = relationship(back_populates="problems")
    artifacts: Mapped[list["Artifact"]] = relationship(back_populates="problem")
    stages: Mapped[list["ProblemStage"]] = relationship(back_populates="problem")
    jobs: Mapped[list["RunnerJob"]] = relationship(back_populates="problem")
    sessions: Mapped[list["Session"]] = relationship(back_populates="problem")


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (UniqueConstraint("problem_id", "kind", "version", name="uq_artifact_version"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    problem_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("problems.id"))
    kind: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)
    content_text: Mapped[str] = mapped_column(Text, default="")
    sha256: Mapped[str] = mapped_column(String(64), default="")
    author: Mapped[str] = mapped_column(String(64), default="human")
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    problem: Mapped["Problem"] = relationship(back_populates="artifacts")


class ProblemStage(Base):
    __tablename__ = "problem_stages"
    __table_args__ = (UniqueConstraint("problem_id", "stage_id", name="uq_problem_stage"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    problem_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("problems.id"))
    stage_id: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default=StageStatus.PENDING.value)
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    problem: Mapped["Problem"] = relationship(back_populates="stages")


class RunnerJob(Base):
    __tablename__ = "runner_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    problem_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("problems.id"))
    kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default=JobStatus.QUEUED.value)
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    result_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    log_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    problem: Mapped["Problem"] = relationship(back_populates="jobs")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    problem_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("problems.id"), nullable=True)
    contest_set_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contest_sets.id"), nullable=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    level: Mapped[str] = mapped_column(String(16), default="INFO")
    source: Mapped[str] = mapped_column(String(32), default="system")
    stage_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    type: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text, default="")
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    problem_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("problems.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(256), default="Session")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    problem: Mapped["Problem | None"] = relationship(back_populates="sessions")
    messages: Mapped[list["SessionMessage"]] = relationship(back_populates="session")


class SessionMessage(Base):
    __tablename__ = "session_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id"))
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text, default="")
    tool_calls_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["Session"] = relationship(back_populates="messages")


class WorkspaceSecret(Base):
    __tablename__ = "workspace_secrets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    key_name: Mapped[str] = mapped_column(String(64))
    value_encrypted: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    __table_args__ = (UniqueConstraint("workspace_id", "key_name", name="uq_workspace_secret"),)
