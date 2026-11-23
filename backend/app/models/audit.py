from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel

from app.models.plugin import utcnow


class AuditLog(SQLModel, table=True):
    """Append-only record of plugin manager actions."""

    __tablename__ = "audit_log"

    id: int | None = Field(default=None, primary_key=True)
    plugin_id: str = Field(index=True)
    action: str = Field(index=True)
    status: str = Field(default="ok", index=True)
    detail: str = Field(default="")
    created_at: datetime = Field(default_factory=utcnow, index=True)
