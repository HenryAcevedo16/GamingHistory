"""Persisted render jobs. Execution state is never inferred from a request."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlmodel import Field, Session, SQLModel, select


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RenderJob(SQLModel, table=True):
    __tablename__ = "render_job"

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    project_id: str = Field(index=True)
    plugin_id: str = Field(default="ffmpeg", index=True)
    kind: str = Field(index=True)
    status: str = Field(default="queued", index=True)
    progress: int = Field(default=0, ge=0, le=100)
    output_path: str
    log: str = ""
    error: str | None = None
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    started_at: datetime | None = None
    completed_at: datetime | None = None


class JobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, *, project_id: str, kind: str, output_path: str) -> RenderJob:
        job = RenderJob(project_id=project_id, kind=kind, output_path=output_path)
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        return job

    def get(self, job_id: str) -> RenderJob | None:
        return self.session.get(RenderJob, job_id)

    def list(self, project_id: str | None = None) -> list[RenderJob]:
        statement = select(RenderJob).order_by(RenderJob.created_at.desc())
        if project_id:
            statement = statement.where(RenderJob.project_id == project_id)
        return list(self.session.exec(statement).all())

    def update(self, job: RenderJob, **changes: object) -> RenderJob:
        for key, value in changes.items():
            setattr(job, key, value)
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        return job
