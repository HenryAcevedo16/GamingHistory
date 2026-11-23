"""Local FFmpeg media import and render job API."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from app.core.db import engine, get_session
from app.core.errors import InvalidOperation
from app.editing.adapter import EditorOperation, execute_operation
from app.editing.jobs import JobRepository, RenderJob
from app.editing.persistence import ProjectRepository
from app.editing.registry import default_registry
from app.editing.timeline import Asset, Project
from app.models.audit import AuditLog

router = APIRouter(tags=["ffmpeg", "jobs"])


class ImportMediaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1)


class ImportMediaResponse(BaseModel):
    asset: Asset


class RenderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    output_path: str = Field(min_length=1)
    confirm_overwrite: bool = False


class JobResponse(BaseModel):
    id: str
    project_id: str
    plugin_id: str
    kind: str
    status: str
    progress: int
    output_path: str
    log: str
    error: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class JobListResponse(BaseModel):
    items: list[JobResponse]
    total: int


def _jobs(session: Session = Depends(get_session)) -> JobRepository:
    return JobRepository(session)


def _audit(session: Session, action: str, status: str, detail: str) -> None:
    session.add(AuditLog(plugin_id="ffmpeg", action=action, status=status, detail=detail[:2000]))
    session.commit()


def _job_response(job: RenderJob) -> JobResponse:
    return JobResponse.model_validate(job, from_attributes=True)


@router.post("/projects/{project_id}/media", response_model=ImportMediaResponse, status_code=201)
def import_media(
    project_id: str,
    payload: ImportMediaRequest,
    session: Session = Depends(get_session),
) -> ImportMediaResponse:
    project = ProjectRepository(session).get(project_id)
    adapter = default_registry.create("ffmpeg")
    inspected = execute_operation(adapter, EditorOperation.IMPORT_MEDIA, {"paths": [payload.path]})[0]
    kind = "video" if any(stream.get("codec_type") == "video" for stream in inspected["streams"]) else "audio"
    asset = Asset(
        id=Path(inspected["path"]).stem + "-" + str(len(project.assets) + 1),
        name=Path(inspected["path"]).name,
        path=inspected["path"],
        kind=kind,
        duration_seconds=inspected["duration_seconds"],
        metadata={"streams": inspected["streams"]},
    )
    project = Project.model_validate({**project.model_dump(), "assets": [*project.assets, asset]})
    ProjectRepository(session).save(project)
    _audit(session, "import_media", "ok", f"Proyecto {project_id}: {asset.path}")
    return ImportMediaResponse(asset=asset)


@router.post("/projects/{project_id}/renders/{kind}", response_model=JobResponse, status_code=202)
def start_render(
    project_id: str,
    kind: str,
    payload: RenderRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> JobResponse:
    if kind not in {"preview", "final"}:
        raise InvalidOperation("El tipo de render debe ser 'preview' o 'final'.")
    ProjectRepository(session).get(project_id)
    from app.editing.adapters.ffmpeg import workspace_path

    output = workspace_path(payload.output_path)
    if output.exists() and not payload.confirm_overwrite:
        raise InvalidOperation("La salida ya existe; envía confirm_overwrite=true para reemplazarla.")
    job = JobRepository(session).create(project_id=project_id, kind=kind, output_path=str(output))
    _audit(session, f"render_{kind}", "queued", f"Job {job.id} encolado para {output}")
    background_tasks.add_task(_execute_render, job.id, payload.confirm_overwrite)
    return _job_response(job)


def _execute_render(job_id: str, overwrite: bool) -> None:
    with Session(engine) as session:
        jobs = JobRepository(session)
        job = jobs.get(job_id)
        if job is None:
            return
        jobs.update(job, status="running", progress=10, started_at=datetime.now(timezone.utc))
        _audit(session, f"render_{job.kind}", "running", f"Job {job.id} iniciado.")
        try:
            project = ProjectRepository(session).get(job.project_id)
            adapter = default_registry.create("ffmpeg")
            operation = EditorOperation.RENDER_PREVIEW if job.kind == "preview" else EditorOperation.RENDER_FINAL
            result = execute_operation(adapter, operation, {"timeline_id": job.id, "project": project, "output_path": job.output_path, "overwrite": overwrite})
            jobs.update(job, status="done", progress=100, completed_at=datetime.now(timezone.utc), log=result.payload.get("log", ""))
            _audit(session, f"render_{job.kind}", "ok", f"Job {job.id} completado: {job.output_path}")
        except Exception as exc:
            jobs.update(job, status="failed", progress=100, completed_at=datetime.now(timezone.utc), error=str(exc))
            _audit(session, f"render_{job.kind}", "error", f"Job {job.id}: {exc}")


@router.get("/jobs", response_model=JobListResponse)
def list_jobs(project_id: str | None = None, jobs: JobRepository = Depends(_jobs)) -> JobListResponse:
    items = [_job_response(job) for job in jobs.list(project_id)]
    return JobListResponse(items=items, total=len(items))


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, jobs: JobRepository = Depends(_jobs)) -> JobResponse:
    job = jobs.get(job_id)
    if job is None:
        raise InvalidOperation(f"No existe el trabajo '{job_id}'.")
    return _job_response(job)
