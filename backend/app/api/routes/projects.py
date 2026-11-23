from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from app.core.db import get_session
from app.editing.persistence import ProjectRepository
from app.editing.timeline import Project, TimelinePayload

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
    repository.get_record(project_id)
    project = Project.model_validate({**payload.model_dump(), "id": project_id})
    return repository.save(project)


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
    project = repository.get(project_id)
    return repository.save(project.with_timeline(payload))
