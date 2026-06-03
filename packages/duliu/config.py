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


settings = Settings()
