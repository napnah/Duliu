from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://duliu:duliu@localhost:5432/duliu"
    runner_work_dir: str = "/tmp/duliu-runner"
    job_poll_seconds: float = 1.0
    max_input_bytes: int = 1_048_576
    max_output_bytes: int = 10_485_760
    default_workspace_name: str = "default"
    cors_origins: str = "*"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    use_langgraph: bool = Field(default=False, validation_alias="DULIU_USE_LANGGRAPH")
    langgraph_checkpoint: str = Field(default="memory", validation_alias="DULIU_LANGGRAPH_CHECKPOINT")
    use_isolate: bool = Field(default=False, validation_alias="DULIU_USE_ISOLATE")
    worker_job_kinds: str = Field(default="", validation_alias="DULIU_WORKER_JOB_KINDS")
    sse_poll_seconds: float = Field(default=2.0, validation_alias="DULIU_SSE_POLL_SECONDS")
    stage_llm_enabled: bool = Field(default=True, validation_alias="DULIU_STAGE_LLM_ENABLED")
    job_ws_poll_seconds: float = Field(default=0.5, validation_alias="DULIU_JOB_WS_POLL_SECONDS")
    session_tools_enabled: bool = Field(default=True, validation_alias="DULIU_SESSION_TOOLS_ENABLED")

    def worker_job_kinds_list(self) -> list[str] | None:
        raw = (self.worker_job_kinds or "").strip()
        if not raw:
            return None
        return [k.strip() for k in raw.split(",") if k.strip()]


settings = Settings()
