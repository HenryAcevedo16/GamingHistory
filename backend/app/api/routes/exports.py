"""Read-only export preflight and confirmed local Resolve delivery."""
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlmodel import Session

from app.api.deps import get_manager
from app.core.db import get_session
from app.core.errors import InvalidOperation, StudioError
from app.core.exec import resolve_binary
from app.editing.adapter import EditorOperation, execute_operation
from app.editing.adapters.ffmpeg import FFmpegConverter
from app.editing.adapters.resolve import ResolveAdapter, ResolveConverter
from app.editing.adapters.vectcut import VectCutConverter, draft_sources
from app.editing.converters import ConversionResult, UnsupportedElement
from app.editing.persistence import ProjectRepository
from app.editing.registry import default_registry
from app.editing.revision import check_revision, revision
from app.editing.router import EditingRouter
from app.editing.timeline import Project
from app.models.audit import AuditLog
from app.plugins.manager import PluginManager

router = APIRouter(prefix="/projects", tags=["exports"])
ExportTarget = Literal["ffmpeg", "resolve", "capcut"]
_TARGETS = {
    "ffmpeg": ("ffmpeg", "auto_assembly", EditorOperation.RENDER_FINAL, FFmpegConverter),
    "resolve": ("davinci-resolve", "professional_edit", EditorOperation.EXPORT_PROJECT, ResolveConverter),
    "capcut": ("vectcut-capcut", "editable_draft", EditorOperation.EXPORT_PROJECT, VectCutConverter),
}


class ExportPreflight(BaseModel):
    revision: str
    available: bool
    reason: str
    verified_capabilities: list[str]
    unsupported: list[UnsupportedElement]
    warnings: list[str]


def _availability(target: ExportTarget, manager: PluginManager, converted: ConversionResult | None) -> tuple[str | None, list[str]]:
    plugin_id, intent, operation, _ = _TARGETS[target]
    views = manager.list_views()
    view = next((view for view in views if view.id == plugin_id), None)
    if view is None:
        return "Plugin no detectado.", []
    verified = view.verified_capabilities
    decision = EditingRouter(views).decide(intent, manual_plugin_id=plugin_id)
    if not decision.selected or not decision.selected.executable:
        candidate = next((item for item in decision.discarded if item.plugin_id == plugin_id), None)
        return (candidate.reason if candidate else decision.explanation), verified
    adapter = default_registry.create(plugin_id)
    if operation not in adapter.get_capabilities().operations:
        return "El adaptador no implementa esta operación.", verified
    if target == "ffmpeg":
        if not all(resolve_binary(name) for name in ("ffmpeg", "ffprobe")):
            return "FFmpeg o ffprobe no están disponibles en PATH.", verified
    else:
        try:
            if not execute_operation(adapter, EditorOperation.HEALTH_CHECK):
                return adapter.last_health_error or "El servicio local no responde.", verified
            if converted and converted.supported:
                if isinstance(adapter, ResolveAdapter) and adapter.last_health is not None:
                    adapter.export_sources(converted, adapter.last_health)
                elif target == "capcut":
                    draft_sources(converted)
        except StudioError as exc:
            return exc.message, verified
    return None, verified


def _preflight(project: Project, target: ExportTarget, manager: PluginManager) -> ExportPreflight:
    converted = None
    conversion_blocker = None
    unsupported: list[UnsupportedElement] = []
    warnings: list[str] = []
    try:
        converted = _TARGETS[target][3]().convert(project)
        unsupported = converted.unsupported
        warnings = converted.warnings
        if target == "resolve" and not converted.payload["frame_based"]:
            warnings = ["La colocación se ajustará a los fotogramas del preset de la timeline nueva de Resolve."]
        if not converted.supported:
            conversion_blocker = "La timeline no contiene clips exportables para este editor."
    except StudioError as exc:
        conversion_blocker = exc.message
    blocker, verified = _availability(target, manager, converted)
    blocker = blocker or conversion_blocker
    return ExportPreflight(revision=revision(project), available=blocker is None,
                           reason=blocker or "Disponible para envío local.",
                           verified_capabilities=verified, unsupported=unsupported, warnings=warnings)


@router.get("/{project_id}/exports/{target}/preflight", response_model=ExportPreflight)
def preflight(project_id: str, target: ExportTarget, session: Session = Depends(get_session),
              manager: PluginManager = Depends(get_manager)) -> ExportPreflight:
    return _preflight(ProjectRepository(session).get(project_id), target, manager)


class ResolveSendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: str


class ResolveSendResponse(BaseModel):
    name: str
    timeline: str
    clips: int


@router.post("/{project_id}/exports/resolve", response_model=ResolveSendResponse, status_code=201)
def send_resolve(project_id: str, payload: ResolveSendRequest, session: Session = Depends(get_session),
                 manager: PluginManager = Depends(get_manager)) -> ResolveSendResponse:
    project = ProjectRepository(session).get(project_id)
    session.rollback()  # the following adapter operations use their own sessions
    status = "error"
    try:
        check_revision(project, payload.revision)
        review = _preflight(project, "resolve", manager)
        if not review.available:
            status = "denied"
            raise InvalidOperation(review.reason, status_code=409)
        result = execute_operation(default_registry.create("davinci-resolve"), EditorOperation.EXPORT_PROJECT,
                                   {"timeline_id": project_id, "target": "resolve", "project": project})
        status = "ok"
        return ResolveSendResponse.model_validate(result)
    finally:
        session.add(AuditLog(plugin_id="davinci-resolve", action="export_project", status=status,
                             detail=f"Proyecto {project_id}"))
        session.commit()
