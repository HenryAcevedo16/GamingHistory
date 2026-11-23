from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PluginState(SQLModel, table=True):
    """Persisted lifecycle state for a plugin. The manifest stays on disk."""

    __tablename__ = "plugin_state"

    plugin_id: str = Field(primary_key=True)
    install_status: str = Field(default="not_installed", index=True)
    enabled: bool = Field(default=True)
    connected: bool = Field(default=False)
    config: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, default=dict),
    )
    last_error: str | None = Field(default=None)
    last_diagnosis_at: datetime | None = Field(default=None)
    last_diagnosis_ok: bool | None = Field(default=None)
    installed_at: datetime | None = Field(default=None)
    connected_at: datetime | None = Field(default=None)
    updated_at: datetime = Field(default_factory=utcnow)
