from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_manager
from app.plugins.manager import PluginManager
from app.plugins.schemas import (
    ActionResponse,
    AuditResponse,
    CapabilityListResponse,
    DiagnosticResponse,
    InstallRequest,
    PluginListResponse,
    PluginView,
    RequirementReport,
    ToolListResponse,
)

router = APIRouter(prefix="/plugins", tags=["plugins"])


@router.get("", response_model=PluginListResponse)
def list_plugins(manager: PluginManager = Depends(get_manager)) -> PluginListResponse:
    views = manager.list_views()
    return PluginListResponse(
        items=views,
        total=len(views),
        counts=manager.counts(views),
        manifest_errors=[
            {"path": issue.path, "error": issue.error} for issue in manager.snapshot.issues
        ],
        generated_at=datetime.now(timezone.utc),
    )


@router.get("/{plugin_id}", response_model=PluginView)
def get_plugin(plugin_id: str, manager: PluginManager = Depends(get_manager)) -> PluginView:
    return manager.get_view(plugin_id)


@router.post("/{plugin_id}/install", response_model=ActionResponse)
def install_plugin(
    plugin_id: str,
    payload: InstallRequest | None = None,
    manager: PluginManager = Depends(get_manager),
) -> ActionResponse:
    confirm = payload.confirm_permissions if payload else False
    view, message = manager.install(plugin_id, confirm_permissions=confirm)
    return ActionResponse(success=True, message=message, plugin=view)


@router.post("/{plugin_id}/connect", response_model=ActionResponse)
def connect_plugin(plugin_id: str, manager: PluginManager = Depends(get_manager)) -> ActionResponse:
    view, message = manager.connect(plugin_id)
    return ActionResponse(success=True, message=message, plugin=view)


@router.post("/{plugin_id}/disconnect", response_model=ActionResponse)
def disconnect_plugin(
    plugin_id: str, manager: PluginManager = Depends(get_manager)
) -> ActionResponse:
    view, message = manager.disconnect(plugin_id)
    return ActionResponse(success=True, message=message, plugin=view)


@router.post("/{plugin_id}/enable", response_model=ActionResponse)
def enable_plugin(plugin_id: str, manager: PluginManager = Depends(get_manager)) -> ActionResponse:
    view, message = manager.set_enabled(plugin_id, enabled=True)
    return ActionResponse(success=True, message=message, plugin=view)


@router.post("/{plugin_id}/disable", response_model=ActionResponse)
def disable_plugin(plugin_id: str, manager: PluginManager = Depends(get_manager)) -> ActionResponse:
    view, message = manager.set_enabled(plugin_id, enabled=False)
    return ActionResponse(success=True, message=message, plugin=view)


@router.get("/{plugin_id}/tools", response_model=ToolListResponse)
def list_tools(plugin_id: str, manager: PluginManager = Depends(get_manager)) -> ToolListResponse:
    return manager.get_tools(plugin_id)


@router.get("/{plugin_id}/capabilities", response_model=CapabilityListResponse)
def list_capabilities(
    plugin_id: str, manager: PluginManager = Depends(get_manager)
) -> CapabilityListResponse:
    return manager.get_capabilities(plugin_id)


@router.post("/{plugin_id}/verify-requirements", response_model=RequirementReport)
def verify_requirements(
    plugin_id: str, manager: PluginManager = Depends(get_manager)
) -> RequirementReport:
    return manager.verify_requirements(plugin_id)


@router.post("/{plugin_id}/diagnose", response_model=DiagnosticResponse)
def diagnose_plugin(
    plugin_id: str, manager: PluginManager = Depends(get_manager)
) -> DiagnosticResponse:
    report = manager.diagnose(plugin_id)
    return DiagnosticResponse(
        **report.model_dump(),
        plugin_state=manager.get_view(plugin_id),
    )


@router.get("/{plugin_id}/audit", response_model=AuditResponse)
def plugin_audit(
    plugin_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    manager: PluginManager = Depends(get_manager),
) -> AuditResponse:
    return AuditResponse(plugin_id=plugin_id, entries=manager.audit_entries(plugin_id, limit))
