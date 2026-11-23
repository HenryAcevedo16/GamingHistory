from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = PROJECT_ROOT / "backend"


class Settings(BaseSettings):
    """Runtime configuration. Values can be overridden with GHS_* env vars."""

    model_config = SettingsConfigDict(
        env_prefix="GHS_",
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Gaming History Studio API"
    api_prefix: str = "/api"
    plugins_dir: Path = PROJECT_ROOT / "plugins"
    database_url: str = ""
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    command_timeout_seconds: float = 15.0
    workspace_dir: Path = BACKEND_ROOT / "data" / "workspace"
    log_level: str = "INFO"

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        db_path = BACKEND_ROOT / "data" / "studio.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{db_path.as_posix()}"

    @property
    def resolved_plugins_dir(self) -> Path:
        return Path(self.plugins_dir).expanduser().resolve()

    @property
    def resolved_workspace_dir(self) -> Path:
        path = Path(self.workspace_dir).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
