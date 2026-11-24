"""SQLite persistence for the unified timeline.

The JSON payload is the canonical document; the columns are indexes for
listing. On read the payload is re-validated, so a hand-edited database cannot
sneak an invalid timeline into the app.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column, text
from sqlalchemy.types import JSON
from sqlmodel import Field, Session, SQLModel, select

from app.core.errors import ProjectNotFound
from app.editing.timeline import Project


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProjectRecord(SQLModel, table=True):
    __tablename__ = "project_record"

    id: str = Field(primary_key=True)
    name: str = Field(index=True)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)
    payload: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, default=dict),
    )


class ProjectRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self) -> list[Project]:
        rows = self.session.exec(
            select(ProjectRecord).order_by(ProjectRecord.updated_at.desc())
        ).all()
        return [self._decode(row) for row in rows]

    def get_record(self, project_id: str) -> ProjectRecord:
        record = self.session.get(ProjectRecord, project_id)
        if record is None:
            raise ProjectNotFound(
                f"No existe un proyecto con id '{project_id}'.",
                details={"project_id": project_id},
            )
        return record

    def get(self, project_id: str) -> Project:
        return self._decode(self.get_record(project_id))

    def begin_write(self) -> None:
        # Serialize read/modify/write updates to the canonical JSON document.
        self.session.execute(text("BEGIN IMMEDIATE"))

    def stage(self, project: Project) -> ProjectRecord:
        project.updated_at = _utcnow()
        record = self.session.get(ProjectRecord, project.id)
        if record is None:
            record = ProjectRecord(
                id=project.id,
                name=project.name,
                created_at=project.created_at,
                updated_at=project.updated_at,
                payload=project.model_dump(mode="json"),
            )
        else:
            record.name = project.name
            record.updated_at = project.updated_at
            record.payload = project.model_dump(mode="json")
        self.session.add(record)
        return record

    def save(self, project: Project) -> Project:
        record = self.stage(project)
        self.session.commit()
        self.session.refresh(record)
        return self._decode(record)

    def delete(self, project_id: str) -> None:
        record = self.get_record(project_id)
        self.session.delete(record)
        self.session.commit()

    @staticmethod
    def _decode(record: ProjectRecord) -> Project:
        try:
            return Project.model_validate(record.payload)
        except ValueError as exc:
            raise ProjectNotFound(
                f"El proyecto '{record.id}' guardado no es válido: {exc}",
                details={"project_id": record.id},
            ) from exc
