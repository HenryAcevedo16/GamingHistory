from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlmodel import Session

from app.core.db import get_session
from app.core.errors import InvalidOperation
from app.editing.adapter import EditorOperation, execute_operation
from app.editing.converters import UnsupportedElement
from app.editing.drafts import DraftResult, list_drafts
from app.editing.notes import NoteText, sanitize_note
from app.editing.persistence import ProjectRepository
from app.editing.registry import default_registry
from app.editing.timeline import Asset, Project, StrictModel, TimelinePayload

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    metadata: dict[str, object] = Field(default_factory=dict)


class ProjectSummary(BaseModel):
    id: str
    name: str
    created_at: datetime
    updated_at: datetime
    assets: int
    scenes: int
    tracks: int


class ProjectListResponse(BaseModel):
    items: list[ProjectSummary]
    total: int


def _repository(session: Session = Depends(get_session)) -> ProjectRepository:
    return ProjectRepository(session)


def _summary(project: Project) -> ProjectSummary:
    return ProjectSummary(
        id=project.id,
        name=project.name,
        created_at=project.created_at,
        updated_at=project.updated_at,
        assets=len(project.assets),
        scenes=len(project.scenes),
        tracks=len(project.tracks),
    )


@router.get("", response_model=ProjectListResponse)
def list_projects(repository: ProjectRepository = Depends(_repository)) -> ProjectListResponse:
    items = [_summary(project) for project in repository.list()]
    return ProjectListResponse(items=items, total=len(items))


@router.post("", response_model=Project, status_code=201)
def create_project(
    payload: ProjectCreateRequest,
    repository: ProjectRepository = Depends(_repository),
) -> Project:
    project = Project(name=payload.name, metadata=payload.metadata)
    return repository.save(project)


@router.get("/{project_id}", response_model=Project)
def get_project(
    project_id: str,
    repository: ProjectRepository = Depends(_repository),
) -> Project:
    return repository.get(project_id)


@router.put("/{project_id}", response_model=Project)
def replace_project(
    project_id: str,
    payload: Project,
    repository: ProjectRepository = Depends(_repository),
) -> Project:
    repository.begin_write()
    repository.get_record(project_id)
    project = Project.model_validate({**payload.model_dump(), "id": project_id})
    return repository.save(project)


class ScriptPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=60000)


class AssetNoteRequest(StrictModel):
    note: NoteText | None = Field(repr=False)


@router.put("/{project_id}/assets/{asset_id}/note", response_model=Asset)
def update_asset_note(project_id: str, asset_id: str, payload: AssetNoteRequest,
                      repository: ProjectRepository = Depends(_repository)) -> Asset:
    repository.begin_write()
    project = repository.get(project_id)
    asset = next((entry for entry in project.assets if entry.id == asset_id), None)
    if asset is None:
        raise InvalidOperation("El recurso no pertenece al proyecto.", code="ASSET_NOT_FOUND", status_code=404)
    asset.note = (sanitize_note(payload.note) or None) if payload.note is not None else None
    repository.save(project)
    return asset


@router.put("/{project_id}/script-plan", response_model=ScriptPlanRequest)
def save_script_plan(project_id: str, payload: ScriptPlanRequest,
                      repository: ProjectRepository = Depends(_repository)) -> ScriptPlanRequest:
    repository.begin_write()
    project = repository.get(project_id)
    project.metadata["script_plan"] = payload.text
    repository.save(project)
    return payload


@router.get("/{project_id}/timeline", response_model=TimelinePayload)
def get_timeline(
    project_id: str,
    repository: ProjectRepository = Depends(_repository),
) -> TimelinePayload:
    return repository.get(project_id).timeline()


@router.put("/{project_id}/timeline", response_model=Project)
def replace_timeline(
    project_id: str,
    payload: TimelinePayload,
    repository: ProjectRepository = Depends(_repository),
) -> Project:
    repository.begin_write()
    project = repository.get(project_id)
    return repository.save(_validated_timeline(project, payload))


def _validated_timeline(project: Project, payload: TimelinePayload) -> Project:
    proposed = {track.id: track for track in payload.tracks}
    if any(track.locked and proposed.get(track.id) != track for track in project.tracks):
        raise InvalidOperation("No se puede modificar ni quitar una pista bloqueada.", code="TRACK_LOCKED")
    try:
        return project.with_timeline(payload)
    except ValidationError as exc:
        raise InvalidOperation("; ".join(error["msg"] for error in exc.errors())) from None


@router.post("/{project_id}/timeline/validate", response_model=TimelinePayload)
def validate_timeline(
    project_id: str, payload: TimelinePayload, repository: ProjectRepository = Depends(_repository),
) -> TimelinePayload:
    return _validated_timeline(repository.get(project_id), payload).timeline()


class DraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    width: int = Field(default=1920, strict=True, ge=16, le=7680)
    height: int = Field(default=1080, strict=True, ge=16, le=7680)
    revision: str | None = None


class DraftExport(BaseModel):
    draft: DraftResult
    exported: list[str]
    unsupported: list[UnsupportedElement]


class DraftDeployRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm_copy: Literal[True]


def _export_draft(project_id: str, target: str, **options: object):
    return execute_operation(default_registry.create("vectcut-capcut"), EditorOperation.EXPORT_PROJECT,
                             {"timeline_id": project_id, "target": target, **options})


@router.post("/{project_id}/drafts", response_model=DraftExport, status_code=201)
def generate_capcut_draft(project_id: str, payload: DraftRequest) -> DraftExport:
    return _export_draft(project_id, "capcut", **payload.model_dump())


@router.get("/{project_id}/drafts", response_model=list[DraftResult])
def project_drafts(project_id: str, session: Session = Depends(get_session)) -> list[DraftResult]:
    ProjectRepository(session).get_record(project_id)
    return list_drafts(session, project_id)


@router.post("/{project_id}/drafts/{draft_id}/deploy", status_code=201)
def deploy_capcut_draft(project_id: str, draft_id: str, payload: DraftDeployRequest) -> dict[str, str]:
    return _export_draft(project_id, "capcut-desktop", draft_id=draft_id)
