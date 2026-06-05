from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class McpSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    duliu_api_base_url: str = "http://localhost:8000"
    duliu_api_timeout_seconds: float = 30.0
    duliu_export_dir: Path = Path("./exports")


settings = McpSettings()
