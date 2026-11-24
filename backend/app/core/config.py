from __future__ import annotations

from pathlib import Path

from pydantic import Field, SecretStr
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
    upload_max_bytes: int = Field(default=2 * 1024**3, gt=0)
    backup_dir: Path | None = None
    backup_max_bytes: int = 20 * 1024**3
    ai_timeout_seconds: float = Field(default=60, gt=0, le=300)
    ai_model: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9._-]{1,100}$")
    opencode_server_url: str = "http://127.0.0.1:4096"
    opencode_server_password: SecretStr | None = None
    opencode_model: str | None = None
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
