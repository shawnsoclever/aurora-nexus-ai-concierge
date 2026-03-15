from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[1] / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    google_api_key: str = Field(alias="GOOGLE_API_KEY")
    google_model: str = Field(default="gemini-2.0-flash", alias="GOOGLE_MODEL")

    mcp_server_url: str = Field(default="http://localhost:8080/mcp", alias="MCP_SERVER_URL")

    google_sheets_credentials_file: str = Field(
        default="final-nexus-1029-01234e2a6a89.json",
        alias="GOOGLE_SHEETS_CREDENTIALS_FILE",
    )
    google_sheets_credentials_json_b64: str = Field(
        default="",
        alias="GOOGLE_SHEETS_CREDENTIALS_JSON_B64",
    )
    google_sheets_spreadsheet_id: str = Field(
        default="",
        alias="GOOGLE_SHEETS_SPREADSHEET_ID",
    )

    @model_validator(mode="after")
    def validate_runtime_settings(self) -> "Settings":
        if self.app_env.lower() == "production" and "localhost" in self.mcp_server_url.lower():
            raise ValueError("MCP_SERVER_URL cannot use localhost in production")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    if not settings.google_api_key:
        raise RuntimeError("GOOGLE_API_KEY is required in .env")
    return settings
