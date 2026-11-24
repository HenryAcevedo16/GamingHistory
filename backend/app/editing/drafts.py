"""Persistent draft artifacts, separate from the editable Unified timeline."""

from datetime import datetime, timezone

from sqlmodel import Field, Session, SQLModel, select

from app.core.errors import InvalidOperation


class DraftResult(SQLModel, table=True):
    __tablename__ = "draft_result"

    id: str = Field(primary_key=True)
    project_id: str = Field(index=True)
    plugin_id: str
    path: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def list_drafts(session: Session, project_id: str) -> list[DraftResult]:
    return list(session.exec(select(DraftResult).where(
        DraftResult.project_id == project_id
    ).order_by(DraftResult.created_at.desc())).all())


def require_draft(session: Session, project_id: str, draft_id: str, plugin_id: str) -> DraftResult:
    result = session.get(DraftResult, draft_id)
    if result is None or result.project_id != project_id or result.plugin_id != plugin_id:
        raise InvalidOperation("Borrador no registrado para este proyecto.", status_code=404)
    return result
